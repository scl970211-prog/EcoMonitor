# -*- coding: utf-8 -*-
"""
IP 冲突检测标签页 - 私接设备排查
复用现有扫描器，检测同一 IP 对应多个 MAC、同一 MAC 对应多个 IP
"""

import logging
import threading
from collections import defaultdict
from typing import Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QMessageBox,
    QSplitter, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ...core.scanner.enhanced_scanner import EnhancedScanner
from ...core.scanner.network_utils import get_local_networks, parse_ip_range
from ...utils.config import get_config

logger = logging.getLogger(__name__)


class IPConflictTab(QWidget):
    """IP 冲突检测标签页"""
    
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._scanner = EnhancedScanner()
        self._is_scanning = False
        self._stop_scan = False
        
        self._init_ui()
        self._connect_signals()
    
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
        
        # 扫描范围
        range_group = QGroupBox("扫描范围")
        range_layout = QVBoxLayout(range_group)
        
        self.auto_range_cb = QCheckBox("自动检测网段")
        self.auto_range_cb.setChecked(True)
        self.auto_range_cb.stateChanged.connect(self._on_auto_range_changed)
        range_layout.addWidget(self.auto_range_cb)
        
        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("如: 192.168.1.0/24")
        self.range_input.setEnabled(False)
        range_layout.addWidget(self.range_input)
        
        self.interface_label = QLabel("网卡: 检测中...")
        range_layout.addWidget(self.interface_label)
        
        layout.addWidget(range_group)
        self._load_networks()
        
        # 扫描选项
        options_group = QGroupBox("扫描选项")
        options_layout = QVBoxLayout(options_group)
        
        self.arp_cb = QCheckBox("读取 ARP 缓存")
        self.arp_cb.setChecked(True)
        options_layout.addWidget(self.arp_cb)
        
        self.icmp_cb = QCheckBox("使用 Ping 探测")
        self.icmp_cb.setChecked(True)
        options_layout.addWidget(self.icmp_cb)
        
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("超时:"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(1)
        self.timeout_spin.setSuffix("秒")
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        options_layout.addLayout(timeout_layout)
        
        layout.addWidget(options_group)
        
        # 按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setMinimumHeight(36)
        self.scan_btn.clicked.connect(self._on_start_scan)
        btn_layout.addWidget(self.scan_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_scan)
        btn_layout.addWidget(self.stop_btn)
        
        layout.addLayout(btn_layout)
        
        # 统计
        self.stats_label = QLabel("就绪")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # IP 冲突表格
        conflict_group = QGroupBox("IP 冲突 (同一 IP 对应多个 MAC)")
        conflict_layout = QVBoxLayout(conflict_group)
        
        self.conflict_table = QTableWidget()
        self.conflict_table.setColumnCount(4)
        self.conflict_table.setHorizontalHeaderLabels([
            "IP 地址", "MAC 地址 1", "MAC 地址 2", "风险等级"
        ])
        header = self.conflict_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.conflict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.conflict_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        conflict_layout.addWidget(self.conflict_table)
        
        layout.addWidget(conflict_group)
        
        # 私接设备表格
        rogue_group = QGroupBox("私接设备嫌疑 (未登记/异常设备)")
        rogue_layout = QVBoxLayout(rogue_group)
        
        self.rogue_table = QTableWidget()
        self.rogue_table.setColumnCount(4)
        self.rogue_table.setHorizontalHeaderLabels([
            "IP 地址", "MAC 地址", "厂商", "异常原因"
        ])
        header2 = self.rogue_table.horizontalHeader()
        header2.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rogue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rogue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        rogue_layout.addWidget(self.rogue_table)
        
        layout.addWidget(rogue_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        return panel
    
    def _load_networks(self):
        """加载网络信息"""
        try:
            networks = get_local_networks()
            if networks:
                self.range_input.setText(networks[0]["cidr"])
                self.interface_label.setText(f"网卡: {networks[0]['interface']}")
            else:
                self.interface_label.setText("未检测到网卡")
                self.auto_range_cb.setChecked(False)
        except Exception:
            self.interface_label.setText("网卡检测失败")
    
    def _on_auto_range_changed(self, state):
        """自动范围变化"""
        self.range_input.setEnabled(not self.auto_range_cb.isChecked())
    
    def _on_start_scan(self):
        """开始扫描"""
        if self.auto_range_cb.isChecked():
            ip_range = self.range_input.text().strip()
        else:
            ip_range = self.range_input.text().strip()
        
        if not ip_range:
            QMessageBox.warning(self, "警告", "请输入扫描范围")
            return
        
        self._is_scanning = True
        self._stop_scan = False
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.stats_label.setText("扫描中...")
        self.stats_label.setStyleSheet("color: #2196F3;")
        
        self.conflict_table.setRowCount(0)
        self.rogue_table.setRowCount(0)
        
        # 设置扫描器参数
        self._scanner.use_arp = self.arp_cb.isChecked()
        self._scanner.use_icmp = self.icmp_cb.isChecked()
        self._scanner.use_tcp = False
        self._scanner.use_onvif = False
        self._scanner.use_fingerprint = False
        self._scanner.timeout = self.timeout_spin.value()
        
        self._scanner.start_scan(
            ip_range,
            use_arp=self.arp_cb.isChecked(),
            use_icmp=self.icmp_cb.isChecked(),
            use_tcp=False,
            use_onvif=False,
            timeout=self.timeout_spin.value()
        )
    
    def _on_stop_scan(self):
        """停止扫描"""
        self._stop_scan = True
        self._scanner.stop_scan()
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.stats_label.setText("已停止")
        self.stats_label.setStyleSheet("color: #999;")
    
    def _on_scan_finished(self):
        """扫描完成"""
        self._is_scanning = False
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.stats_label.setText("扫描完成")
        self.stats_label.setStyleSheet("color: #4CAF50;")
        
        self._analyze_conflicts()
    
    def _analyze_conflicts(self):
        """分析冲突"""
        # 收集所有发现的设备
        ip_to_macs: Dict[str, List[str]] = defaultdict(list)
        mac_to_ips: Dict[str, List[str]] = defaultdict(list)
        all_devices = []
        
        # 从扫描器获取结果（通过信号接收的）
        # 但由于设备是通过信号分批接收的，我们需要从表格重新收集
        # 这里简化处理：使用 ARP 缓存直接做冲突检测
        
        try:
            from ...core.scanner.enhanced_scanner import ARPScanner
            arp_scanner = ARPScanner()
            arp_cache = arp_scanner.get_all_cached_devices()
            
            for ip, mac in arp_cache.items():
                normalized_mac = mac.lower().replace('-', ':')
                ip_to_macs[ip].append(normalized_mac)
                mac_to_ips[normalized_mac].append(ip)
            
            # 检测 IP 冲突（同一 IP 多个 MAC）
            conflict_count = 0
            for ip, macs in ip_to_macs.items():
                unique_macs = list(set(macs))
                if len(unique_macs) > 1:
                    conflict_count += 1
                    row = self.conflict_table.rowCount()
                    self.conflict_table.insertRow(row)
                    self.conflict_table.setItem(row, 0, QTableWidgetItem(ip))
                    self.conflict_table.setItem(row, 1, QTableWidgetItem(unique_macs[0]))
                    self.conflict_table.setItem(row, 2, QTableWidgetItem(unique_macs[1]))
                    
                    risk_item = QTableWidgetItem("⚠️ 高")
                    risk_item.setForeground(Qt.GlobalColor.red)
                    self.conflict_table.setItem(row, 3, risk_item)
            
            # 检测私接设备嫌疑
            # 1. 同一 MAC 多个 IP（可能是 IP 欺骗或环路）
            for mac, ips in mac_to_ips.items():
                if len(ips) > 1:
                    row = self.rogue_table.rowCount()
                    self.rogue_table.insertRow(row)
                    self.rogue_table.setItem(row, 0, QTableWidgetItem(", ".join(ips)))
                    self.rogue_table.setItem(row, 1, QTableWidgetItem(mac))
                    self.rogue_table.setItem(row, 2, QTableWidgetItem("--"))
                    
                    reason = QTableWidgetItem("同一 MAC 多个 IP")
                    reason.setForeground(Qt.GlobalColor.red)
                    self.rogue_table.setItem(row, 3, reason)
            
            # 2. 未知厂商设备（可能的私接）
            from ...core.scanner.device_info import get_resolver
            resolver = get_resolver()
            
            for ip, mac in arp_cache.items():
                vendor = resolver.get_vendor(mac)
                if not vendor or vendor == "Unknown":
                    row = self.rogue_table.rowCount()
                    self.rogue_table.insertRow(row)
                    self.rogue_table.setItem(row, 0, QTableWidgetItem(ip))
                    self.rogue_table.setItem(row, 1, QTableWidgetItem(mac))
                    self.rogue_table.setItem(row, 2, QTableWidgetItem("未知厂商"))
                    
                    reason = QTableWidgetItem("未知厂商设备")
                    reason.setForeground(Qt.GlobalColor.darkYellow)
                    self.rogue_table.setItem(row, 3, reason)
            
            self.stats_label.setText(
                f"扫描完成: 发现 {conflict_count} 个 IP 冲突, "
                f"{self.rogue_table.rowCount()} 个异常设备"
            )
            
        except Exception as e:
            logger.error(f"冲突分析失败: {e}")
            self.stats_label.setText("分析失败")
    
    def _on_devices_found(self, devices: list):
        """发现设备（占位，实际冲突分析在扫描完成后进行）"""
        pass
    
    def _on_progress_update(self, current: int, total: int):
        """进度更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
    
    def _on_scan_error(self, error_msg: str):
        """扫描错误"""
        QMessageBox.critical(self, "扫描错误", error_msg)
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
    
    def _connect_signals(self):
        """连接信号"""
        self._scanner.scan_finished.connect(self._on_scan_finished)
        self._scanner.progress_update.connect(self._on_progress_update)
        self._scanner.scan_error.connect(self._on_scan_error)
