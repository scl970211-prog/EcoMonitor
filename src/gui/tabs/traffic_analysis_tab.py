# -*- coding: utf-8 -*-
"""
流量分析标签页 - DSCP 检测 / 轻量抓包
替代 DSCP 检测工具功能
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QTextEdit, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject

from ...utils.config import get_config
from ..theme import set_text_style
from ...core.constants import DSCP_NAMES

logger = logging.getLogger(__name__)

# 抑制 scapy 在未安装 Npcap 时反复打印的 WinPcap 弃用警告
# （项目已迁移到 Npcap，该警告对用户无意义）
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)


class _Signaler(QObject):
    log = pyqtSignal(str)
    add_packet = pyqtSignal(str, str, str, str, int, int)
    update_stats = pyqtSignal()
    capture_stopped = pyqtSignal()
    show_error = pyqtSignal(str, str)


class TrafficAnalysisTab(QWidget):
    """流量分析标签页"""
    
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._is_capturing = False
        self._stop_capture = False
        self._capture_thread = None
        self._dscp_stats: Dict[int, int] = defaultdict(int)
        self._total_packets = 0
        self._scapy_available = False
        
        self._signaler = _Signaler()
        self._signaler.log.connect(self._on_log)
        self._signaler.add_packet.connect(self._on_add_packet)
        self._signaler.update_stats.connect(self._update_stats_ui)
        self._signaler.capture_stopped.connect(self._on_capture_stopped)
        self._signaler.show_error.connect(self._on_show_error)
        
        self._check_scapy()
        self._init_ui()
    
    def _check_scapy(self):
        """检查 scapy 是否可用"""
        try:
            import scapy.all as scapy
            self._scapy_available = True
        except ImportError:
            self._scapy_available = False
            logger.warning("scapy 未安装，流量分析功能受限")
    
    def _init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 如果 scapy 不可用，显示提示
        if not self._scapy_available:
            self._show_scapy_warning(layout)
            return
        
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
        splitter.setSizes([300, 900])
    
    def _show_scapy_warning(self, layout):
        """显示 scapy 未安装提示"""
        vlayout = QVBoxLayout()
        vlayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        warning_label = QLabel(
            "流量分析功能需要 scapy 库\n\n"
            "请安装以下依赖:\n"
            "  pip install scapy\n\n"
            "Windows 用户还需安装 Npcap:\n"
            "  https://npcap.com/#download"
        )
        set_text_style(warning_label, "secondary", size="14px")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vlayout.addWidget(warning_label)
        
        # 提供一个手动安装按钮
        install_btn = QPushButton("复制安装命令到剪贴板")
        install_btn.clicked.connect(self._copy_install_cmd)
        vlayout.addWidget(install_btn)
        
        layout.addLayout(vlayout)
    
    def _copy_install_cmd(self):
        """复制安装命令"""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("pip install scapy")
        QMessageBox.information(self, "已复制", "安装命令已复制到剪贴板")
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # 抓包控制组
        capture_group = QGroupBox("抓包控制")
        capture_layout = QVBoxLayout(capture_group)
        
        # 网卡选择
        iface_layout = QHBoxLayout()
        iface_layout.addWidget(QLabel("网卡:"))
        self.iface_combo = QComboBox()
        self._load_interfaces()
        iface_layout.addWidget(self.iface_combo)
        capture_layout.addLayout(iface_layout)
        
        # 过滤器
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("过滤:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("ip (可选)")
        filter_layout.addWidget(self.filter_input)
        capture_layout.addLayout(filter_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始抓包")
        self.start_btn.setMinimumHeight(32)
        self.start_btn.clicked.connect(self._on_start_capture)
        btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_capture)
        btn_layout.addWidget(self.stop_btn)
        capture_layout.addLayout(btn_layout)
        
        layout.addWidget(capture_group)
        
        # 统计组
        stats_group = QGroupBox("实时统计")
        stats_layout = QVBoxLayout(stats_group)
        
        self.total_label = QLabel("总包数: 0")
        stats_layout.addWidget(self.total_label)
        
        self.rate_label = QLabel("速率: 0 pps")
        stats_layout.addWidget(self.rate_label)
        
        layout.addWidget(stats_group)
        
        # DSCP 说明
        info_group = QGroupBox("DSCP 值参考")
        info_layout = QVBoxLayout(info_group)
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(200)
        info_text.setPlainText(
            "EF(46): 语音/实时视频\n"
            "AF41-43(34-38): 流媒体\n"
            "AF31-33(26-30): 信令\n"
            "AF21-23(18-22): 事务数据\n"
            "AF11-13(10-14): 批量数据\n"
            "CS0(0): 尽力而为\n\n"
            "异常: 非标准DSCP值可能来自私接设备"
        )
        info_layout.addWidget(info_text)
        layout.addWidget(info_group)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # DSCP 统计表格
        dscp_group = QGroupBox("DSCP 分布统计")
        dscp_layout = QVBoxLayout(dscp_group)
        
        self.dscp_table = QTableWidget()
        self.dscp_table.setColumnCount(5)
        self.dscp_table.setHorizontalHeaderLabels([
            "DSCP 值", "DSCP 名称", "包数", "占比", "风险标记"
        ])
        header = self.dscp_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.dscp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        dscp_layout.addWidget(self.dscp_table)
        
        layout.addWidget(dscp_group)
        
        # 包列表
        packet_group = QGroupBox("最近捕获的包 (Top 100)")
        packet_layout = QVBoxLayout(packet_group)
        
        self.packet_table = QTableWidget()
        self.packet_table.setColumnCount(6)
        self.packet_table.setHorizontalHeaderLabels([
            "时间", "源IP", "目标IP", "协议", "DSCP", "长度"
        ])
        header2 = self.packet_table.horizontalHeader()
        header2.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.packet_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.packet_table.setMaximumHeight(250)
        packet_layout.addWidget(self.packet_table)
        
        layout.addWidget(packet_group)
        
        # 日志
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setPlaceholderText("抓包日志...")
        layout.addWidget(self.log_text)
        
        return panel
    
    def _load_interfaces(self):
        """加载网卡接口"""
        self.iface_combo.clear()
        self.iface_combo.addItem("默认")
        
        try:
            import scapy.all as scapy
            from scapy.arch.windows import get_windows_if_list
            
            ifaces = get_windows_if_list()
            for iface in ifaces:
                name = iface.get("name", "")
                desc = iface.get("description", "")
                if name and desc:
                    display = f"{desc} ({name})"
                    self.iface_combo.addItem(display, name)
                elif name:
                    self.iface_combo.addItem(name, name)
        except Exception as e:
            logger.debug(f"加载网卡失败: {e}")
    
    def _on_start_capture(self):
        """开始抓包"""
        self._is_capturing = True
        self._stop_capture = False
        self._dscp_stats.clear()
        self._total_packets = 0
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.dscp_table.setRowCount(0)
        self.packet_table.setRowCount(0)
        
        iface_data = self.iface_combo.currentData()
        iface = iface_data if iface_data else None
        bpf_filter = self.filter_input.text().strip() or "ip"
        
        self._log(f"开始抓包: 网卡={iface or '默认'}, 过滤={bpf_filter}")
        
        self._capture_thread = threading.Thread(
            target=self._capture_worker,
            args=(iface, bpf_filter),
            daemon=True
        )
        self._capture_thread.start()
        
        # 启动定时更新UI
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_stats_ui)
        self._update_timer.start(1000)  # 每秒更新一次
    
    def _capture_worker(self, iface: str, bpf_filter: str):
        """抓包工作线程"""
        try:
            import scapy.all as scapy
            
            def packet_handler(pkt):
                if self._stop_capture:
                    return
                
                try:
                    if not pkt.haslayer(scapy.IP):
                        return
                    
                    ip_layer = pkt[scapy.IP]
                    tos = ip_layer.tos
                    dscp = tos >> 2  # DSCP 是 ToS 的高6位
                    
                    self._dscp_stats[dscp] += 1
                    self._total_packets += 1
                    
                    # 记录最近的包
                    src_ip = ip_layer.src
                    dst_ip = ip_layer.dst
                    proto = "TCP" if pkt.haslayer(scapy.TCP) else (
                        "UDP" if pkt.haslayer(scapy.UDP) else str(ip_layer.proto)
                    )
                    length = len(pkt)
                    
                    self._add_packet_record(
                        time.strftime("%H:%M:%S"), src_ip, dst_ip,
                        proto, dscp, length
                    )
                    
                except Exception:
                    pass
            
            scapy.sniff(
                iface=iface,
                filter=bpf_filter,
                prn=packet_handler,
                stop_filter=lambda x: self._stop_capture,
                store=False
            )
            
        except Exception as e:
            self._log(f"抓包错误: {e}")
            self._signaler.show_error.emit("抓包失败", str(e))
        
        finally:
            self._signaler.capture_stopped.emit()
    
    def _add_packet_record(self, ts: str, src: str, dst: str, proto: str, dscp: int, length: int):
        """添加包记录（线程安全）"""
        self._signaler.add_packet.emit(ts, src, dst, proto, dscp, length)
    
    def _update_stats_ui(self):
        """更新统计 UI"""
        if not self._is_capturing:
            return
        
        self.total_label.setText(f"总包数: {self._total_packets}")
        
        # 更新 DSCP 表格
        self.dscp_table.setRowCount(0)
        
        if self._total_packets == 0:
            return
        
        # 按包数排序
        sorted_dscp = sorted(self._dscp_stats.items(), key=lambda x: x[1], reverse=True)
        
        for dscp, count in sorted_dscp:
            row = self.dscp_table.rowCount()
            self.dscp_table.insertRow(row)
            
            self.dscp_table.setItem(row, 0, QTableWidgetItem(str(dscp)))
            
            name = DSCP_NAMES.get(dscp, "非标准/自定义")
            name_item = QTableWidgetItem(name)
            if dscp not in DSCP_NAMES:
                name_item.setForeground(Qt.GlobalColor.red)
            self.dscp_table.setItem(row, 1, name_item)
            
            self.dscp_table.setItem(row, 2, QTableWidgetItem(str(count)))
            
            percent = round(count / self._total_packets * 100, 1)
            self.dscp_table.setItem(row, 3, QTableWidgetItem(f"{percent}%"))
            
            # 风险标记
            if dscp not in DSCP_NAMES:
                risk = QTableWidgetItem("非标准DSCP")
                risk.setForeground(Qt.GlobalColor.red)
            elif dscp == 46:
                risk = QTableWidgetItem("语音优先")
                risk.setForeground(Qt.GlobalColor.darkGreen)
            elif dscp >= 40:
                risk = QTableWidgetItem("高优先级")
                risk.setForeground(Qt.GlobalColor.blue)
            else:
                risk = QTableWidgetItem("普通")
            self.dscp_table.setItem(row, 4, risk)
    
    def _on_stop_capture(self):
        """停止抓包"""
        self._stop_capture = True
        self._is_capturing = False
        
        if hasattr(self, '_update_timer'):
            self._update_timer.stop()
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log("抓包已停止")
    
    def _on_capture_stopped(self):
        """抓包已停止"""
        self._on_stop_capture()
    
    def _log(self, text: str):
        """记录日志"""
        self._signaler.log.emit(text)
    
    def _on_log(self, text: str):
        self.log_text.append(text)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_add_packet(self, ts: str, src: str, dst: str, proto: str, dscp: int, length: int):
        # 限制行数
        if self.packet_table.rowCount() >= 100:
            self.packet_table.removeRow(0)
        
        row = self.packet_table.rowCount()
        self.packet_table.insertRow(row)
        self.packet_table.setItem(row, 0, QTableWidgetItem(ts))
        self.packet_table.setItem(row, 1, QTableWidgetItem(src))
        self.packet_table.setItem(row, 2, QTableWidgetItem(dst))
        self.packet_table.setItem(row, 3, QTableWidgetItem(proto))
        
        dscp_item = QTableWidgetItem(str(dscp))
        if dscp not in [0, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 44, 46, 48, 56]:
            dscp_item.setForeground(Qt.GlobalColor.red)
        self.packet_table.setItem(row, 4, dscp_item)
        
        self.packet_table.setItem(row, 5, QTableWidgetItem(str(length)))
        
        # 滚动到底部
        self.packet_table.scrollToBottom()
    
    def _on_show_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)
    
    def closeEvent(self, event):
        """关闭事件"""
        self._on_stop_capture()
        super().closeEvent(event)
