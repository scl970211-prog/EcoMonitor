"""
扫描管理器 - 协调各种扫描方法 (PyQt6 适配版)
"""

import threading
import time
from typing import List

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .network_utils import parse_ip_range, get_ip_count, get_local_networks
from .device_info import Device, get_resolver


class ScanSignals(QObject):
    """扫描信号定义"""
    devices_found = pyqtSignal(list)       # 批量发现设备列表
    progress_update = pyqtSignal(int, int) # 当前进度, 总数
    scan_finished = pyqtSignal()           # 扫描完成
    scan_error = pyqtSignal(str)           # 错误信息


class BatchScanTask(QRunnable):
    """批量IP扫描任务"""
    
    def __init__(self, ip_batch: List[str], timeout: float, manager: "ScannerManager"):
        super().__init__()
        self.ip_batch = ip_batch
        self.timeout = timeout
        self.manager = manager
    
    def run(self):
        """执行批量扫描任务"""
        if self.manager.should_stop():
            self.manager.task_completed(len(self.ip_batch))
            return
        
        found_devices = []
        
        # ICMP 扫描
        try:
            import subprocess
            import platform
            
            for ip in self.ip_batch:
                if self.manager.should_stop():
                    break
                
                try:
                    # Ping 检测
                    param = '-n' if platform.system().lower() == 'windows' else '-c'
                    cmd = ['ping', param, '1', '-w', str(int(self.timeout * 1000)), ip]
                    
                    if platform.system() == "Windows":
                        result = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
                    else:
                        result = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
                    
                    if result.returncode == 0:
                        device = Device(ip)
                        device.is_online = True
                        device.scan_method = "ICMP"
                        found_devices.append(device)
                except Exception:
                    pass
        except Exception:
            pass
        
        # 发射结果
        if not self.manager.should_stop() and found_devices:
            self.manager.signals.devices_found.emit(found_devices)
        
        # 通知任务完成
        self.manager.task_completed(len(self.ip_batch))


class ScannerManager(QObject):
    """扫描管理器"""
    
    BATCH_SIZE = 50
    
    def __init__(self):
        super().__init__()
        self.signals = ScanSignals()
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(20)
        
        self._lock = threading.Lock()
        self._is_scanning = False
        self._should_stop = False
        self._completed_count = 0
        self._total_count = 0
    
    def start_scan(self, ip_range: str, use_arp: bool = True, 
                   use_ping: bool = True, use_tcp: bool = True, 
                   timeout: float = 1.0):
        """开始扫描"""
        with self._lock:
            if self._is_scanning:
                self.signals.scan_error.emit("扫描正在进行中")
                return
        
        ip_count = get_ip_count(ip_range)
        if ip_count == 0:
            self.signals.scan_error.emit("无效的IP范围")
            return
        
        if ip_count > 65536:
            self.signals.scan_error.emit("IP范围过大（超过65536个地址）")
            return
        
        # 初始化状态
        with self._lock:
            self._is_scanning = True
            self._should_stop = False
            self._completed_count = 0
            self._total_count = ip_count
        
        self.signals.progress_update.emit(0, self._total_count)
        
        # 分批提交任务
        self._submit_tasks(parse_ip_range(ip_range), timeout)
    
    def _submit_tasks(self, ip_iterator, timeout: float):
        """提交批量扫描任务"""
        batch = []
        for ip in ip_iterator:
            with self._lock:
                if self._should_stop:
                    break
            
            batch.append(ip)
            if len(batch) >= self.BATCH_SIZE:
                task = BatchScanTask(batch, timeout, self)
                self.threadpool.start(task)
                batch = []
        
        # 提交剩余IP
        if batch:
            with self._lock:
                if not self._should_stop:
                    task = BatchScanTask(batch, timeout, self)
                    self.threadpool.start(task)
    
    def task_completed(self, count: int = 1):
        """任务完成回调"""
        with self._lock:
            self._completed_count += count
            current = min(self._completed_count, self._total_count)
            total = self._total_count
            is_finished = (current >= total) and self._is_scanning
        
        self.signals.progress_update.emit(current, total)
        
        if is_finished:
            with self._lock:
                self._is_scanning = False
            self.signals.scan_finished.emit()
    
    def stop_scan(self):
        """停止扫描"""
        with self._lock:
            self._should_stop = True
            total = self._total_count
        
        self.threadpool.clear()
        self.threadpool.waitForDone(3000)
        
        with self._lock:
            self._is_scanning = False
            if self._completed_count < total:
                self._completed_count = total
        
        self.signals.progress_update.emit(total, total)
        self.signals.scan_finished.emit()
    
    def is_scanning(self) -> bool:
        """是否正在扫描"""
        with self._lock:
            return self._is_scanning
    
    def should_stop(self) -> bool:
        """是否应该停止"""
        with self._lock:
            return self._should_stop
    
    def get_auto_range(self) -> str:
        """获取自动检测的网段范围"""
        networks = get_local_networks()
        if networks:
            return networks[0]["cidr"]
        return ""
