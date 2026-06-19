# -*- coding: utf-8 -*-
"""
抓包分析标签页 - 调用 Wireshark / tshark
替代 Wireshark 原生功能，提供快捷入口和轻量分析
"""

import logging
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QFileDialog,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ..theme import set_status_style
from ...core.constants import DSCP_NAMES

logger = logging.getLogger(__name__)


class PacketCaptureTab(QWidget):
    """抓包分析标签页"""
    
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._wireshark_path = None
        self._tshark_path = None
        self._init_ui()
        self._detect_tools()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 工具检测状态
        status_group = QGroupBox("工具状态检测")
        status_layout = QHBoxLayout(status_group)
        
        self.wireshark_status = QLabel("Wireshark: 检测中...")
        status_layout.addWidget(self.wireshark_status)
        
        self.tshark_status = QLabel("tshark: 检测中...")
        status_layout.addWidget(self.tshark_status)
        
        self.npcap_status = QLabel("Npcap: 检测中...")
        status_layout.addWidget(self.npcap_status)
        
        status_layout.addStretch()
        
        self.refresh_btn = QPushButton("重新检测")
        self.refresh_btn.clicked.connect(self._detect_tools)
        status_layout.addWidget(self.refresh_btn)
        
        layout.addWidget(status_group)
        
        # 快速启动 Wireshark
        wireshark_group = QGroupBox("启动 Wireshark")
        wireshark_layout = QVBoxLayout(wireshark_group)
        
        # 网卡选择
        iface_layout = QHBoxLayout()
        iface_layout.addWidget(QLabel("网卡过滤:"))
        self.iface_input = QLineEdit()
        self.iface_input.setPlaceholderText("如: eth0 (留空使用默认)")
        iface_layout.addWidget(self.iface_input)
        wireshark_layout.addLayout(iface_layout)
        
        # 捕获过滤
        capture_filter_layout = QHBoxLayout()
        capture_filter_layout.addWidget(QLabel("捕获过滤:"))
        self.capture_filter = QLineEdit()
        self.capture_filter.setPlaceholderText("如: host 192.168.1.1 (BPF语法，可选)")
        capture_filter_layout.addWidget(self.capture_filter)
        wireshark_layout.addLayout(capture_filter_layout)
        
        btn_layout = QHBoxLayout()
        
        self.start_wireshark_btn = QPushButton("启动 Wireshark")
        self.start_wireshark_btn.setMinimumHeight(36)
        self.start_wireshark_btn.clicked.connect(self._on_start_wireshark)
        btn_layout.addWidget(self.start_wireshark_btn)
        
        self.start_tshark_btn = QPushButton("启动 tshark (命令行)")
        self.start_tshark_btn.setMinimumHeight(36)
        self.start_tshark_btn.clicked.connect(self._on_start_tshark)
        btn_layout.addWidget(self.start_tshark_btn)
        
        wireshark_layout.addLayout(btn_layout)
        layout.addWidget(wireshark_group)
        
        # tshark 轻量分析
        tshark_group = QGroupBox("tshark 轻量分析")
        tshark_layout = QVBoxLayout(tshark_group)
        
        # pcap 文件选择
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("PCAP 文件:"))
        self.pcap_path = QLineEdit()
        self.pcap_path.setPlaceholderText("选择或输入 pcap 文件路径...")
        file_layout.addWidget(self.pcap_path)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._on_browse_pcap)
        file_layout.addWidget(self.browse_btn)
        tshark_layout.addLayout(file_layout)
        
        # 分析按钮
        analyze_layout = QHBoxLayout()
        
        self.protocol_stats_btn = QPushButton("协议统计")
        self.protocol_stats_btn.clicked.connect(self._on_protocol_stats)
        analyze_layout.addWidget(self.protocol_stats_btn)
        
        self.dscp_stats_btn = QPushButton("DSCP 统计")
        self.dscp_stats_btn.clicked.connect(self._on_dscp_stats)
        analyze_layout.addWidget(self.dscp_stats_btn)
        
        self.conversation_btn = QPushButton("会话列表")
        self.conversation_btn.clicked.connect(self._on_conversation_list)
        analyze_layout.addWidget(self.conversation_btn)
        
        tshark_layout.addLayout(analyze_layout)
        
        # 分析结果表格
        self.analyze_table = QTableWidget()
        self.analyze_table.setColumnCount(3)
        self.analyze_table.setHorizontalHeaderLabels(["项目", "数值", "说明"])
        header = self.analyze_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.analyze_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tshark_layout.addWidget(self.analyze_table)
        
        layout.addWidget(tshark_group)
        
        # 日志
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        layout.addWidget(self.log_text)
        
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)
        layout.setStretch(3, 0)
    
    def _detect_tools(self):
        """检测工具安装状态"""
        system = platform.system()
        
        # 检测 Wireshark
        self._wireshark_path = self._find_wireshark()
        if self._wireshark_path:
            self.wireshark_status.setText(f"Wireshark: 已找到 ({self._wireshark_path})")
            set_status_style(self.wireshark_status, "success")
            self.start_wireshark_btn.setEnabled(True)
        else:
            self.wireshark_status.setText("Wireshark: 未安装")
            set_status_style(self.wireshark_status, "error")
            self.start_wireshark_btn.setEnabled(False)
        
        # 检测 tshark
        self._tshark_path = self._find_tshark()
        if self._tshark_path:
            self.tshark_status.setText(f"tshark: 已找到 ({self._tshark_path})")
            set_status_style(self.tshark_status, "success")
            self.start_tshark_btn.setEnabled(True)
            self.protocol_stats_btn.setEnabled(True)
            self.dscp_stats_btn.setEnabled(True)
            self.conversation_btn.setEnabled(True)
        else:
            self.tshark_status.setText("tshark: 未安装")
            set_status_style(self.tshark_status, "error")
            self.start_tshark_btn.setEnabled(False)
            self.protocol_stats_btn.setEnabled(False)
            self.dscp_stats_btn.setEnabled(False)
            self.conversation_btn.setEnabled(False)
        
        # 检测 Npcap
        if self._check_npcap():
            self.npcap_status.setText("Npcap: 已安装")
            set_status_style(self.npcap_status, "success")
        else:
            self.npcap_status.setText("Npcap: 未安装 (抓包需要)")
            set_status_style(self.npcap_status, "error")
    
    def _find_wireshark(self) -> str:
        """查找 Wireshark 安装路径"""
        system = platform.system()
        
        if system == "Windows":
            # 常见安装路径
            paths = [
                r"C:\Program Files\Wireshark\Wireshark.exe",
                r"C:\Program Files (x86)\Wireshark\Wireshark.exe",
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
            
            # 从 PATH 查找
            try:
                result = subprocess.run(
                    ["where", "wireshark"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    return result.stdout.strip().splitlines()[0]
            except Exception:
                pass
        else:
            # Linux/macOS
            try:
                result = subprocess.run(
                    ["which", "wireshark"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        
        return None
    
    def _find_tshark(self) -> str:
        """查找 tshark 安装路径"""
        system = platform.system()
        
        if system == "Windows":
            paths = [
                r"C:\Program Files\Wireshark\tshark.exe",
                r"C:\Program Files (x86)\Wireshark\tshark.exe",
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
            
            try:
                result = subprocess.run(
                    ["where", "tshark"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    return result.stdout.strip().splitlines()[0]
            except Exception:
                pass
        else:
            try:
                result = subprocess.run(
                    ["which", "tshark"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        
        return None
    
    def _check_npcap(self) -> bool:
        """检测 Npcap 是否安装

        WinPcap 已停止维护并被官方弃用，因此仅检测 Npcap。
        参考：https://npcap.com/
        """
        system = platform.system()
        if system != "Windows":
            return True  # Linux/macOS 使用 libpcap，通常已安装

        try:
            import winreg

            # 检查 Npcap 注册表项
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Npcap")
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                pass

            # 检查常见路径下的 Npcap DLL
            dll_paths = [
                r"C:\Windows\System32\Npcap\wpcap.dll",
                r"C:\Windows\SysWOW64\Npcap\wpcap.dll",
                r"C:\Windows\System32\wpcap.dll",
            ]
            for p in dll_paths:
                if os.path.exists(p):
                    return True

        except Exception:
            pass

        return False
    
    def _on_start_wireshark(self):
        """启动 Wireshark"""
        if not self._wireshark_path:
            QMessageBox.warning(self, "错误", "未找到 Wireshark")
            return
        
        args = [self._wireshark_path]
        
        iface = self.iface_input.text().strip()
        if iface:
            args.extend(["-i", iface])
        
        cap_filter = self.capture_filter.text().strip()
        if cap_filter:
            args.extend(["-f", cap_filter])
        
        try:
            subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
            self._log("Wireshark 已启动")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"无法启动 Wireshark:\n{e}")
    
    def _on_start_tshark(self):
        """启动 tshark"""
        if not self._tshark_path:
            QMessageBox.warning(self, "错误", "未找到 tshark")
            return
        
        # 打开命令行窗口运行 tshark
        args = [self._tshark_path, "-i"]
        
        iface = self.iface_input.text().strip()
        args.append(iface if iface else "1")
        
        cap_filter = self.capture_filter.text().strip()
        if cap_filter:
            args.extend(["-f", cap_filter])
        
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["cmd", "/k"] + args)
            else:
                subprocess.Popen(args)
            self._log("tshark 已启动")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"无法启动 tshark:\n{e}")
    
    def _on_browse_pcap(self):
        """浏览 PCAP 文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PCAP 文件", "",
            "PCAP 文件 (*.pcap *.pcapng *.cap);;所有文件 (*.*)"
        )
        if path:
            self.pcap_path.setText(path)
    
    def _run_tshark_command(self, args: list) -> str:
        """运行 tshark 命令并返回输出"""
        if not self._tshark_path:
            QMessageBox.warning(self, "错误", "未找到 tshark")
            return ""
        
        pcap = self.pcap_path.text().strip()
        if not pcap:
            QMessageBox.warning(self, "错误", "请先选择 PCAP 文件")
            return ""
        
        if not os.path.exists(pcap):
            QMessageBox.warning(self, "错误", f"文件不存在:\n{pcap}")
            return ""
        
        cmd = [self._tshark_path, "-r", pcap] + args
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            return result.stdout
        except Exception as e:
            QMessageBox.critical(self, "分析失败", f"tshark 运行失败:\n{e}")
            return ""
    
    def _on_protocol_stats(self):
        """协议统计"""
        output = self._run_tshark_command(["-q", "-z", "io,phs"])
        if not output:
            return
        
        self.analyze_table.setRowCount(0)
        self.analyze_table.setHorizontalHeaderLabels(["协议", "包数", "字节数"])
        
        # 解析输出
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("==") or line.startswith("Protocol"):
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                row = self.analyze_table.rowCount()
                self.analyze_table.insertRow(row)
                self.analyze_table.setItem(row, 0, QTableWidgetItem(parts[0]))
                self.analyze_table.setItem(row, 1, QTableWidgetItem(parts[1]))
                self.analyze_table.setItem(row, 2, QTableWidgetItem(parts[2]))
        
        self._log("协议统计完成")
    
    def _on_dscp_stats(self):
        """DSCP 统计"""
        output = self._run_tshark_command([
            "-q", "-z", "conv,ip",
            "-Y", "ip.dsfield.dscp"
        ])
        
        # 更直接的 DSCP 统计
        output2 = self._run_tshark_command([
            "-T", "fields", "-e", "ip.dsfield.dscp",
            "-Y", "ip.dsfield.dscp"
        ])
        
        if not output2:
            return
        
        from collections import Counter
        dscp_values = [line.strip() for line in output2.splitlines() if line.strip()]
        counts = Counter(dscp_values)
        
        self.analyze_table.setRowCount(0)
        self.analyze_table.setHorizontalHeaderLabels(["DSCP 值", "包数", "说明"])
        
        for dscp, count in sorted(counts.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            row = self.analyze_table.rowCount()
            self.analyze_table.insertRow(row)
            
            self.analyze_table.setItem(row, 0, QTableWidgetItem(str(dscp)))
            self.analyze_table.setItem(row, 1, QTableWidgetItem(str(count)))
            
            dscp_int = int(dscp) if dscp.isdigit() else -1
            name = DSCP_NAMES.get(dscp_int, "未知")
            self.analyze_table.setItem(row, 2, QTableWidgetItem(name))
        
        self._log("DSCP 统计完成")
    
    def _on_conversation_list(self):
        """会话列表"""
        output = self._run_tshark_command(["-q", "-z", "conv,ip"])
        if not output:
            return
        
        self.analyze_table.setRowCount(0)
        self.analyze_table.setHorizontalHeaderLabels(["地址 A", "地址 B", "包数/字节"])
        
        lines = output.splitlines()
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("<->"):
                in_table = True
                continue
            if not in_table or not line or line.startswith("=="):
                continue
            
            parts = line.split()
            if len(parts) >= 4:
                row = self.analyze_table.rowCount()
                self.analyze_table.insertRow(row)
                self.analyze_table.setItem(row, 0, QTableWidgetItem(parts[0]))
                self.analyze_table.setItem(row, 1, QTableWidgetItem(parts[2]))
                self.analyze_table.setItem(row, 2, QTableWidgetItem(f"{parts[3]} / {parts[4] if len(parts) > 4 else 'N/A'}"))
        
        self._log("会话列表完成")
    
    def _log(self, text: str):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {text}")
