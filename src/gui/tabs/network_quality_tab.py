# -*- coding: utf-8 -*-
"""
网络质量检测标签页 - Ping / MTU / 吞吐量测试
替代 HP 网络质量检测器功能
"""

import logging
import platform
import re
import socket
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSpinBox, QProgressBar,
    QMessageBox, QSplitter, QTextEdit, QComboBox
)
from PyQt6.QtWidgets import QAbstractSpinBox
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject

from ...utils.config import get_config
from ..theme import set_status_style

logger = logging.getLogger(__name__)


@dataclass
class PingResult:
    """Ping 测试结果"""
    host: str
    ip: str = ""
    sent: int = 0
    received: int = 0
    lost: int = 0
    loss_rate: float = 0.0
    min_time: float = -1.0
    max_time: float = -1.0
    avg_time: float = -1.0
    times: List[float] = field(default_factory=list)
    status: str = "未知"


class _Signaler(QObject):
    """用于跨线程信号传递"""
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    test_finished = pyqtSignal()
    mtu_result = pyqtSignal(str)
    add_ping_result = pyqtSignal(object)


class NetworkQualityTab(QWidget):
    """网络质量检测标签页"""
    
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._is_testing = False
        self._stop_test = False
        
        self._signaler = _Signaler()
        self._signaler.log.connect(self._on_log)
        self._signaler.status.connect(self._on_status)
        self._signaler.progress.connect(self._on_progress_update)
        self._signaler.test_finished.connect(self._on_test_finished)
        self._signaler.mtu_result.connect(self._on_mtu_result)
        self._signaler.add_ping_result.connect(self._on_add_ping_result)
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # 左侧面板
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 右侧面板
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Ping 测试组
        ping_group = QGroupBox("Ping 测试")
        ping_layout = QVBoxLayout(ping_group)
        
        ping_layout.addWidget(QLabel("目标地址 (每行一个):"))
        self.ping_targets = QTextEdit()
        self.ping_targets.setPlaceholderText(
            "例如:\n192.168.1.1\n8.8.8.8\nwww.baidu.com"
        )
        self.ping_targets.setMaximumHeight(120)
        ping_layout.addWidget(self.ping_targets)
        
        # 快速预设
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("快速添加:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "-- 选择 --", "本机网关", "百度", "腾讯", "阿里",
            "Google DNS", "Cloudflare"
        ])
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.preset_combo)
        ping_layout.addLayout(preset_layout)
        
        # 参数
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("次数:"))
        self.ping_count = QSpinBox()
        self.ping_count.setRange(1, 100)
        self.ping_count.setValue(10)
        self.ping_count.setMinimumWidth(110)
        self.ping_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        param_layout.addWidget(self.ping_count)
        
        param_layout.addWidget(QLabel("超时:"))
        self.ping_timeout = QSpinBox()
        self.ping_timeout.setRange(1, 10)
        self.ping_timeout.setValue(3)
        self.ping_timeout.setSuffix("秒")
        self.ping_timeout.setMinimumWidth(110)
        self.ping_timeout.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        param_layout.addWidget(self.ping_timeout)
        param_layout.addStretch()
        ping_layout.addLayout(param_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.ping_btn = QPushButton("开始 Ping")
        self.ping_btn.setMinimumHeight(32)
        self.ping_btn.clicked.connect(self._on_start_ping)
        btn_layout.addWidget(self.ping_btn)
        
        self.stop_ping_btn = QPushButton("停止")
        self.stop_ping_btn.setEnabled(False)
        self.stop_ping_btn.clicked.connect(self._on_stop_test)
        btn_layout.addWidget(self.stop_ping_btn)
        ping_layout.addLayout(btn_layout)
        
        layout.addWidget(ping_group)
        
        # MTU 测试组
        mtu_group = QGroupBox("MTU 测试")
        mtu_layout = QVBoxLayout(mtu_group)
        
        mtu_host_layout = QHBoxLayout()
        mtu_host_layout.addWidget(QLabel("目标:"))
        self.mtu_target = QLineEdit()
        self.mtu_target.setPlaceholderText("8.8.8.8")
        mtu_host_layout.addWidget(self.mtu_target)
        mtu_layout.addLayout(mtu_host_layout)
        
        self.mtu_btn = QPushButton("测试路径 MTU")
        self.mtu_btn.setMinimumHeight(32)
        self.mtu_btn.clicked.connect(self._on_test_mtu)
        mtu_layout.addWidget(self.mtu_btn)
        
        self.mtu_result_label = QLabel("MTU 结果: 未测试")
        self.mtu_result_label.setWordWrap(True)
        mtu_layout.addWidget(self.mtu_result_label)
        
        layout.addWidget(mtu_group)
        
        # 状态
        self.status_label = QLabel("就绪")
        set_status_style(self.status_label, "offline")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(7)
        self.result_table.setHorizontalHeaderLabels([
            "目标地址", "解析IP", "发送", "接收", "丢包率", "平均延迟", "状态"
        ])
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.result_table)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        return panel
    
    def _on_preset_selected(self, text: str):
        """快速预设选择"""
        presets = {
            "本机网关": self._get_default_gateway(),
            "百度": "www.baidu.com",
            "腾讯": "www.qq.com",
            "阿里": "www.aliyun.com",
            "Google DNS": "8.8.8.8",
            "Cloudflare": "1.1.1.1",
        }
        host = presets.get(text, "")
        if host:
            current = self.ping_targets.toPlainText().strip()
            if current:
                self.ping_targets.setPlainText(current + "\n" + host)
            else:
                self.ping_targets.setPlainText(host)
            self.preset_combo.setCurrentIndex(0)
    
    def _get_default_gateway(self) -> str:
        """获取默认网关"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="ignore", timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                for line in result.stdout.split("\n"):
                    if "0.0.0.0" in line and "Gateway" not in line:
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] != "On-link":
                            return parts[2]
            else:
                result = subprocess.run(
                    ["ip", "route"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "default" in line:
                        m = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if m:
                            return m.group(1)
        except Exception as e:
            logger.debug(f"获取网关失败: {e}")
        return "192.168.1.1"
    
    def _on_start_ping(self):
        """开始 Ping 测试"""
        targets_text = self.ping_targets.toPlainText().strip()
        if not targets_text:
            QMessageBox.warning(self, "警告", "请输入至少一个目标地址")
            return
        
        targets = [t.strip() for t in targets_text.splitlines() if t.strip()]
        if not targets:
            return
        
        self._is_testing = True
        self._stop_test = False
        self.ping_btn.setEnabled(False)
        self.stop_ping_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(targets))
        self.progress_bar.setValue(0)
        self.status_label.setText("测试中...")
        set_status_style(self.status_label, "info")
        
        self.result_table.setRowCount(0)
        
        thread = threading.Thread(
            target=self._ping_worker,
            args=(targets, self.ping_count.value(), self.ping_timeout.value()),
            daemon=True
        )
        thread.start()
    
    def _ping_worker(self, targets: List[str], count: int, timeout: int):
        """Ping 工作线程"""
        total = len(targets)
        for i, host in enumerate(targets):
            if self._stop_test:
                break
            
            result = self._do_ping(host, count, timeout)
            self._signaler.add_ping_result.emit(result)
            self._signaler.progress.emit(i + 1, total)
        
        self._signaler.test_finished.emit()
    
    def _do_ping(self, host: str, count: int, timeout: int) -> PingResult:
        """执行一次 Ping 测试"""
        result = PingResult(host=host)
        
        system = platform.system()
        
        try:
            # 先解析IP
            try:
                result.ip = socket.getaddrinfo(host, None)[0][4][0]
            except Exception:
                result.ip = host
            
            if system == "Windows":
                cmd = [
                    "ping", "-n", str(count), "-w", str(timeout * 1000), host
                ]
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                cmd = [
                    "ping", "-c", str(count), "-W", str(timeout), host
                ]
                creationflags = 0
            
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=timeout * count + 10,
                creationflags=creationflags
            )
            
            output = proc.stdout
            
            # 解析结果
            if system == "Windows":
                result = self._parse_windows_ping(output, host, result.ip, count)
            else:
                result = self._parse_unix_ping(output, host, result.ip, count)
            
            if proc.returncode == 0:
                result.status = "正常"
            else:
                result.status = "不可达"
                
        except subprocess.TimeoutExpired:
            result.status = "超时"
        except Exception as e:
            result.status = f"错误: {e}"
        
        return result
    
    def _parse_windows_ping(self, output: str, host: str, ip: str, count: int) -> PingResult:
        """解析 Windows ping 输出"""
        result = PingResult(host=host, ip=ip)
        
        # 统计发送/接收
        sent_match = re.search(r'发送\s*=\s*(\d+)', output)
        recv_match = re.search(r'接收\s*=\s*(\d+)', output)
        lost_match = re.search(r'丢失\s*=\s*(\d+)', output)
        
        if sent_match:
            result.sent = int(sent_match.group(1))
        if recv_match:
            result.received = int(recv_match.group(1))
        if lost_match:
            result.lost = int(lost_match.group(1))
        
        # 丢包率
        loss_match = re.search(r'丢失率.*?\((\d+)%', output)
        if loss_match:
            result.loss_rate = int(loss_match.group(1))
        elif result.sent > 0:
            result.loss_rate = round((result.sent - result.received) / result.sent * 100, 1)
        
        # 延迟统计
        times = re.findall(r'时间[<=]?(\d+)ms', output)
        if times:
            result.times = [int(t) for t in times]
        else:
            # 英文版 Windows
            times = re.findall(r'time[<=]?(\d+)ms', output)
            result.times = [int(t) for t in times]
        
        # 最小/最大/平均
        stat_match = re.search(r'最短\s*=\s*(\d+)ms.*?最长\s*=\s*(\d+)ms.*?平均\s*=\s*(\d+)ms', output)
        if stat_match:
            result.min_time = int(stat_match.group(1))
            result.max_time = int(stat_match.group(2))
            result.avg_time = int(stat_match.group(3))
        else:
            # 英文版
            stat_match = re.search(r'Minimum\s*=\s*(\d+)ms.*?Maximum\s*=\s*(\d+)ms.*?Average\s*=\s*(\d+)ms', output)
            if stat_match:
                result.min_time = int(stat_match.group(1))
                result.max_time = int(stat_match.group(2))
                result.avg_time = int(stat_match.group(3))
            elif result.times:
                result.min_time = min(result.times)
                result.max_time = max(result.times)
                result.avg_time = round(statistics.mean(result.times), 1)
        
        return result
    
    def _parse_unix_ping(self, output: str, host: str, ip: str, count: int) -> PingResult:
        """解析 Unix ping 输出"""
        result = PingResult(host=host, ip=ip)
        
        # 发送包数
        trans_match = re.search(r'(\d+) packets transmitted', output)
        recv_match = re.search(r'(\d+) received', output)
        
        if trans_match:
            result.sent = int(trans_match.group(1))
        if recv_match:
            result.received = int(recv_match.group(1))
        
        result.lost = result.sent - result.received
        if result.sent > 0:
            result.loss_rate = round(result.lost / result.sent * 100, 1)
        
        # 提取每个包的延迟
        times = re.findall(r'time=(\d+\.?\d*)', output)
        result.times = [float(t) for t in times]
        
        # rtt min/avg/max
        rtt_match = re.search(r'rtt min/avg/max.*=\s*([\d.]+)/([\d.]+)/([\d.]+)', output)
        if rtt_match:
            result.min_time = float(rtt_match.group(1))
            result.avg_time = round(float(rtt_match.group(2)), 1)
            result.max_time = float(rtt_match.group(3))
        elif result.times:
            result.min_time = round(min(result.times), 1)
            result.max_time = round(max(result.times), 1)
            result.avg_time = round(statistics.mean(result.times), 1)
        
        return result
    
    def _update_result_table(self, result: PingResult, row_index: int):
        """更新结果表格"""
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        
        self.result_table.setItem(row, 0, QTableWidgetItem(result.host))
        self.result_table.setItem(row, 1, QTableWidgetItem(result.ip))
        self.result_table.setItem(row, 2, QTableWidgetItem(str(result.sent)))
        self.result_table.setItem(row, 3, QTableWidgetItem(str(result.received)))
        
        loss_text = f"{result.loss_rate}%"
        loss_item = QTableWidgetItem(loss_text)
        if result.loss_rate > 0:
            loss_item.setForeground(Qt.GlobalColor.red)
        self.result_table.setItem(row, 4, loss_item)
        
        avg_text = f"{result.avg_time} ms" if result.avg_time >= 0 else "N/A"
        self.result_table.setItem(row, 5, QTableWidgetItem(avg_text))
        
        status_item = QTableWidgetItem(result.status)
        if result.status == "正常":
            status_item.setForeground(Qt.GlobalColor.darkGreen)
        elif "不可达" in result.status or "错误" in result.status:
            status_item.setForeground(Qt.GlobalColor.red)
        self.result_table.setItem(row, 6, status_item)
    
    def _on_add_ping_result(self, result: PingResult):
        """槽函数：添加 Ping 结果到表格"""
        self._update_result_table(result, 0)
    
    def _on_progress_update(self, current: int, total: int):
        """槽函数：更新进度条"""
        self.progress_bar.setValue(current)
    
    def _on_log(self, message: str):
        """槽函数：处理日志信号"""
        logger.info(message)
    
    def _on_status(self, text: str):
        """槽函数：更新状态标签"""
        self.status_label.setText(text)
    
    def _on_test_mtu(self):
        """测试 MTU"""
        host = self.mtu_target.text().strip()
        if not host:
            host = "8.8.8.8"
        
        self.mtu_btn.setEnabled(False)
        self.mtu_result_label.setText("MTU 测试中...")
        set_status_style(self.mtu_result_label, "info")
        
        thread = threading.Thread(target=self._mtu_worker, args=(host,), daemon=True)
        thread.start()
    
    def _mtu_worker(self, host: str):
        """MTU 测试工作线程"""
        result = self._do_mtu_test(host)
        self._signaler.mtu_result.emit(result)
    
    def _on_mtu_result(self, result: str):
        """槽函数：显示 MTU 测试结果"""
        self.mtu_result_label.setText(result)
        self.mtu_result_label.setStyleSheet("")
        self.mtu_btn.setEnabled(True)
    
    def _do_mtu_test(self, host: str) -> str:
        """执行 MTU 测试（二分法）"""
        system = platform.system()
        
        # ICMP 头部 8 字节 + IP 头部 20 字节 = 28 字节开销
        overhead = 28
        
        low = 0
        high = 1500 - overhead  # 最大测试 1472
        
        best = 0
        
        try:
            # 先测试一个肯定能通的大小
            if system == "Windows":
                cmd = ["ping", "-n", "1", "-f", "-l", str(32), host]
                flags = subprocess.CREATE_NO_WINDOW
            else:
                cmd = ["ping", "-c", "1", "-M", "do", "-s", str(32), host]
                flags = 0
            
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=10,
                creationflags=flags
            )
            if result.returncode != 0 and "frag" not in result.stdout.lower():
                return f"无法连接到 {host}，请检查网络连接"
        except Exception:
            return f"无法连接到 {host}"
        
        # 二分法查找最大 MTU
        while low <= high:
            mid = (low + high) // 2
            if mid < 1:
                break
            
            try:
                if system == "Windows":
                    cmd = ["ping", "-n", "1", "-f", "-l", str(mid), host]
                    flags = subprocess.CREATE_NO_WINDOW
                else:
                    cmd = ["ping", "-c", "1", "-M", "do", "-s", str(mid), host]
                    flags = 0
                
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="ignore", timeout=10,
                    creationflags=flags
                )
                
                success = result.returncode == 0
                if success and system == "Windows":
                    # Windows 下即使 returncode 为 0，输出中包含分段提示也说明包被拆分/不可达
                    output_lower = result.stdout.lower()
                    if (
                        "fragment" in output_lower
                        or "需要分段" in output_lower
                        or "packet needs to be fragmented" in output_lower
                    ):
                        success = False
                
                if success:
                    best = mid
                    low = mid + 1
                else:
                    high = mid - 1
                    
            except Exception:
                high = mid - 1
        
        mtu = best + overhead
        
        if best == 0:
            return f"无法确定到 {host} 的路径 MTU，可能被防火墙阻止"
        
        # 常见 MTU 值参考
        mtu_type = "未知"
        if mtu >= 1500:
            mtu_type = "标准以太网 (1500)"
        elif mtu >= 1492:
            mtu_type = "PPPoE (1492)"
        elif mtu >= 1480:
            mtu_type = "IPv6 over IPv4 隧道 (1480)"
        elif mtu >= 1400:
            mtu_type = "VPN/隧道"
        elif mtu >= 1280:
            mtu_type = "IPv6 最小 (1280)"
        
        return f"到 {host} 的路径 MTU: {mtu} 字节\n(IP载荷最大: {best} 字节)\n类型推测: {mtu_type}"
    
    def _on_stop_test(self):
        """停止测试"""
        self._stop_test = True
        self.status_label.setText("已停止")
        set_status_style(self.status_label, "offline")
    
    def _on_test_finished(self):
        """测试完成"""
        self._is_testing = False
        self.ping_btn.setEnabled(True)
        self.stop_ping_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("测试完成")
        set_status_style(self.status_label, "success")
