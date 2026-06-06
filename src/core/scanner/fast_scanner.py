"""
高速扫描器 - 使用 ICMP 和 TCP 快速发现设备

优化策略：
1. 使用原始 socket 发送 ICMP，避免 subprocess 开销
2. TCP SYN 快速探测常见端口
3. 批量异步处理
"""

import socket
import struct
import threading
import time
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional
from dataclasses import dataclass

from .device_info import Device


@dataclass
class ScanResult:
    """扫描结果"""
    ip: str
    is_online: bool
    response_time: float = -1.0
    scan_method: str = ""
    open_ports: List[int] = None
    mac: str = ""
    
    def __post_init__(self):
        if self.open_ports is None:
            self.open_ports = []


class FastScanner:
    """高速扫描器"""
    
    # 常见端口
    COMMON_PORTS = [80, 443, 554, 8000, 8080, 22, 23, 21, 3389, 445, 139, 135]
    
    def __init__(self, timeout: float = 0.5, max_workers: int = 100):
        self.timeout = timeout
        self.max_workers = max_workers
        self._stop_event = threading.Event()
    
    def stop(self):
        """停止扫描"""
        self._stop_event.set()
    
    def is_stopped(self) -> bool:
        """是否已停止"""
        return self._stop_event.is_set()
    
    def reset(self):
        """重置停止标志"""
        self._stop_event.clear()
    
    def scan_batch(self, ip_list: List[str], 
                   use_icmp: bool = True, 
                   use_tcp: bool = True) -> List[ScanResult]:
        """
        批量扫描 IP 列表
        
        Args:
            ip_list: IP 地址列表
            use_icmp: 是否使用 ICMP
            use_tcp: 是否使用 TCP
        
        Returns:
            在线设备列表
        """
        results = []
        found_ips = set()
        
        # 先进行 ICMP 扫描（更快）
        if use_icmp and not self.is_stopped():
            icmp_results = self._icmp_scan_batch(ip_list)
            for result in icmp_results:
                if result.is_online:
                    results.append(result)
                    found_ips.add(result.ip)
        
        # TCP 扫描补充（针对 ICMP 未发现的 IP）
        if use_tcp and not self.is_stopped():
            remaining_ips = [ip for ip in ip_list if ip not in found_ips]
            if remaining_ips:
                tcp_results = self._tcp_scan_batch(remaining_ips)
                for result in tcp_results:
                    if result.is_online:
                        results.append(result)
        
        return results
    
    def _icmp_scan_batch(self, ip_list: List[str]) -> List[ScanResult]:
        """批量 ICMP 扫描"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ip = {
                executor.submit(self._icmp_ping, ip): ip 
                for ip in ip_list if not self.is_stopped()
            }
            
            for future in as_completed(future_to_ip):
                if self.is_stopped():
                    break
                
                ip = future_to_ip[future]
                try:
                    response_time = future.result()
                    if response_time > 0:
                        result = ScanResult(
                            ip=ip,
                            is_online=True,
                            response_time=response_time,
                            scan_method="ICMP"
                        )
                        results.append(result)
                    else:
                        results.append(ScanResult(ip=ip, is_online=False))
                except Exception:
                    results.append(ScanResult(ip=ip, is_online=False))
        
        return results
    
    def _icmp_ping(self, ip: str) -> float:
        """
        发送 ICMP Echo Request
        
        Returns:
            响应时间（毫秒），-1 表示失败
        """
        if self.is_stopped():
            return -1
        
        try:
            # 创建原始 socket（需要管理员权限）
            if platform.system() == "Windows":
                sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, 
                                    socket.IPPROTO_ICMP)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                    socket.IPPROTO_ICMP)
            
            sock.settimeout(self.timeout)
            
            # 构建 ICMP Echo Request
            icmp_id = threading.current_thread().ident % 65535
            icmp_seq = 1
            checksum = 0
            
            # ICMP 头部
            header = struct.pack('!BBHHH', 8, 0, checksum, icmp_id, icmp_seq)
            data = b'FastScanner'
            
            # 计算校验和
            checksum = self._checksum(header + data)
            header = struct.pack('!BBHHH', 8, 0, checksum, icmp_id, icmp_seq)
            
            packet = header + data
            
            # 发送
            start_time = time.time()
            sock.sendto(packet, (ip, 0))
            
            # 接收响应
            try:
                reply, addr = sock.recvfrom(1024)
                elapsed = (time.time() - start_time) * 1000  # 毫秒
                
                # 验证响应
                if addr[0] == ip:
                    sock.close()
                    return elapsed
            except socket.timeout:
                pass
            
            sock.close()
            return -1
            
        except PermissionError:
            # 没有权限，回退到系统 ping
            return self._system_ping(ip)
        except Exception:
            return -1
    
    def _system_ping(self, ip: str) -> float:
        """使用系统 ping 命令（无权限时回退）"""
        import subprocess
        
        try:
            start_time = time.time()
            
            if platform.system() == "Windows":
                cmd = ['ping', '-n', '1', '-w', str(int(self.timeout * 1000)), ip]
                result = subprocess.run(cmd, capture_output=True, 
                                      timeout=self.timeout + 0.5,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                cmd = ['ping', '-c', '1', '-W', str(int(self.timeout)), ip]
                result = subprocess.run(cmd, capture_output=True,
                                      timeout=self.timeout + 0.5)
            
            if result.returncode == 0:
                elapsed = (time.time() - start_time) * 1000
                return elapsed
            return -1
        except Exception:
            return -1
    
    def _tcp_scan_batch(self, ip_list: List[str]) -> List[ScanResult]:
        """批量 TCP SYN 扫描"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ip = {
                executor.submit(self._tcp_syn_scan, ip): ip
                for ip in ip_list if not self.is_stopped()
            }
            
            for future in as_completed(future_to_ip):
                if self.is_stopped():
                    break
                
                ip = future_to_ip[future]
                try:
                    open_ports = future.result()
                    if open_ports:
                        result = ScanResult(
                            ip=ip,
                            is_online=True,
                            scan_method="TCP",
                            open_ports=open_ports
                        )
                        results.append(result)
                    else:
                        results.append(ScanResult(ip=ip, is_online=False))
                except Exception:
                    results.append(ScanResult(ip=ip, is_online=False))
        
        return results
    
    def _tcp_syn_scan(self, ip: str, ports: List[int] = None) -> List[int]:
        """
        TCP SYN 扫描
        
        Returns:
            开放端口列表
        """
        if ports is None:
            # 只扫描前几个常见端口（更快）
            ports = self.COMMON_PORTS[:5]
        
        open_ports = []
        
        for port in ports:
            if self.is_stopped():
                break
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    open_ports.append(port)
                    # 找到一个开放端口即可确认在线
                    break
            except Exception:
                pass
        
        return open_ports
    
    def _checksum(self, data: bytes) -> int:
        """计算 ICMP 校验和"""
        if len(data) % 2:
            data += b'\0'
        
        s = sum(struct.unpack('!%dH' % (len(data) // 2), data))
        s = (s >> 16) + (s & 0xffff)
        s += s >> 16
        return ~s & 0xffff


class OptimizedScannerManager:
    """优化的扫描管理器（与原接口兼容）"""
    
    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal
        
        class Signals(QObject):
            devices_found = pyqtSignal(list)
            progress_update = pyqtSignal(int, int)
            scan_finished = pyqtSignal()
            scan_error = pyqtSignal(str)
        
        self.signals = Signals()
        self._scanner = None
        self._scan_thread = None
        self._is_scanning = False
    
    def start_scan(self, ip_range: str, use_arp: bool = True,
                   use_ping: bool = True, use_tcp: bool = True,
                   timeout: float = 0.5):
        """开始扫描"""
        if self._is_scanning:
            self.signals.scan_error.emit("扫描正在进行中")
            return
        
        from .network_utils import parse_ip_range, get_ip_count
        
        ip_list = list(parse_ip_range(ip_range))
        if not ip_list:
            self.signals.scan_error.emit("无效的IP范围")
            return
        
        if len(ip_list) > 65536:
            self.signals.scan_error.emit("IP范围过大")
            return
        
        self._is_scanning = True
        self._scanner = FastScanner(timeout=timeout, max_workers=200)
        
        # 在后台线程中运行扫描
        import threading
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(ip_list, use_ping, use_tcp)
        )
        self._scan_thread.start()
    
    def _scan_worker(self, ip_list: List[str], use_icmp: bool, use_tcp: bool):
        """扫描工作线程"""
        total = len(ip_list)
        processed = 0
        batch_size = 100
        all_devices = []
        
        # 分批扫描
        for i in range(0, total, batch_size):
            if self._scanner.is_stopped():
                break
            
            batch = ip_list[i:i + batch_size]
            results = self._scanner.scan_batch(batch, use_icmp, use_tcp)
            
            # 转换为 Device 对象
            devices = []
            for result in results:
                processed += 1
                if result.is_online:
                    device = Device(result.ip)
                    device.is_online = True
                    device.response_time = result.response_time
                    device.scan_method = result.scan_method
                    device.open_ports = result.open_ports
                    devices.append(device)
                    all_devices.append(device)
            
            # 发送进度和结果
            if devices:
                self.signals.devices_found.emit(devices)
            self.signals.progress_update.emit(min(processed, total), total)
            
            # 小延迟避免 CPU 占用过高
            time.sleep(0.01)
        
        self._is_scanning = False
        self.signals.scan_finished.emit()
    
    def stop_scan(self):
        """停止扫描"""
        if self._scanner:
            self._scanner.stop()
        self._is_scanning = False
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_thread.join(timeout=2)
        self.signals.scan_finished.emit()
    
    def is_scanning(self) -> bool:
        """是否正在扫描"""
        return self._is_scanning
    
    def should_stop(self) -> bool:
        """是否应该停止"""
        return self._scanner and self._scanner.is_stopped()
    
    def get_auto_range(self) -> str:
        """获取自动网段"""
        from .network_utils import get_local_networks
        networks = get_local_networks()
        if networks:
            return networks[0]["cidr"]
        return ""
