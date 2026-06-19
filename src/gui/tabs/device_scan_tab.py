# -*- coding: utf-8 -*-
"""
设备搜索标签页 - 局域网设备扫描

表格列宽特性：
- 所有列总宽度始终等于视口宽度
- 拖动列宽时，相邻列自动调整保持总宽不变
- 列宽自动保存/恢复
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QCheckBox,
    QSpinBox, QAbstractSpinBox, QMessageBox, QMenu, QApplication, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QUrl
from PyQt6.QtGui import QDesktopServices

from ...core.scanner.enhanced_scanner import EnhancedScanner
from ...core.scanner.network_utils import get_local_networks
from ...utils.config import get_config

logger = logging.getLogger(__name__)


class DeviceScanTab(QWidget):
    """设备搜索标签页"""
    
    device_selected = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._scanner = EnhancedScanner()
        self._found_devices = []
        self._resize_timer = None
        self._column_widths = []  # 当前列宽比例
        
        self._init_ui()
        self._connect_signals()
        self.installEventFilter(self)
        
        # 延迟恢复列宽（等待表格渲染完成）
        QTimer.singleShot(100, self._restore_column_widths)
    
    def resizeEvent(self, event):
        """窗口大小变化时，重新调整列宽填满视口"""
        super().resizeEvent(event)
        if self.result_table.columnCount() > 0:
            self._distribute_column_widths()
    
    def eventFilter(self, obj, event):
        """事件过滤器"""
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self._copy_selected_rows()
                return True
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        """关闭事件 - 保存所有设置"""
        self._save_all_settings()
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """隐藏事件 - 保存所有设置"""
        self._save_all_settings()
        super().hideEvent(event)
    
    def _save_all_settings(self):
        """保存所有界面设置"""
        self._save_splitter_state()
        self._save_column_widths()
    
    def _copy_selected_rows(self):
        """复制选中的行"""
        selected_rows = set()
        for item in self.result_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        all_rows_text = []
        for row in sorted(selected_rows):
            texts = []
            for col in range(self.result_table.columnCount()):
                item = self.result_table.item(row, col)
                texts.append(item.text() if item else "")
            all_rows_text.append("\t".join(texts))
        
        QApplication.clipboard().setText("\n".join(all_rows_text))
        self.log_message.emit(f"已复制 {len(selected_rows)} 行")
    
    def _init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)
        
        left_panel = self._create_left_panel()
        self.splitter.addWidget(left_panel)
        
        right_panel = self._create_right_panel()
        self.splitter.addWidget(right_panel)
        
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        
        self._restore_splitter_state()
    
    def _restore_splitter_state(self):
        """恢复分割器状态"""
        try:
            state = self._config.get("ui.device_scan_splitter_state", None)
            if state:
                self.splitter.restoreState(bytes.fromhex(state))
            else:
                self.splitter.setSizes([320, 1000])
        except Exception:
            self.splitter.setSizes([320, 1000])
    
    def _save_splitter_state(self):
        """保存分割器状态"""
        try:
            state = self.splitter.saveState().tohex()
            self._config.set("ui.device_scan_splitter_state", state)
        except Exception:
            pass
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 扫描范围
        range_group = QGroupBox("扫描范围")
        range_layout = QVBoxLayout(range_group)
        
        self.auto_range_cb = QCheckBox("自动检测网段")
        self.auto_range_cb.setChecked(True)
        self.auto_range_cb.stateChanged.connect(self._on_auto_range_changed)
        range_layout.addWidget(self.auto_range_cb)
        
        self.cidr_combo = QLineEdit()
        self.cidr_combo.setPlaceholderText("如: 192.168.1.0/24")
        self.cidr_combo.setEnabled(False)
        range_layout.addWidget(self.cidr_combo)
        
        range_layout.addWidget(QLabel("或指定范围:"))
        self.manual_range = QLineEdit()
        self.manual_range.setPlaceholderText("如: 192.168.1.1-192.168.1.100")
        self.manual_range.setEnabled(False)
        range_layout.addWidget(self.manual_range)
        
        self.interface_label = QLabel("网卡: 检测中...")
        range_layout.addWidget(self.interface_label)
        
        layout.addWidget(range_group)
        self._load_networks()
        
        # 扫描选项
        options_group = QGroupBox("扫描选项")
        options_layout = QVBoxLayout(options_group)
        
        self.arp_cb = QCheckBox("使用ARP缓存 (推荐)")
        self.arp_cb.setChecked(True)
        options_layout.addWidget(self.arp_cb)
        
        self.icmp_cb = QCheckBox("使用Ping探测")
        self.icmp_cb.setChecked(True)
        options_layout.addWidget(self.icmp_cb)
        
        self.tcp_cb = QCheckBox("使用TCP端口探测")
        self.tcp_cb.setChecked(True)
        options_layout.addWidget(self.tcp_cb)
        
        self.onvif_cb = QCheckBox("ONVIF 快速发现 (推荐)")
        self.onvif_cb.setChecked(True)
        self.onvif_cb.setToolTip("优先使用 ONVIF 协议发现设备，速度快且支持跨厂商")
        options_layout.addWidget(self.onvif_cb)
        
        self.fingerprint_cb = QCheckBox("设备指纹识别 (慢)")
        self.fingerprint_cb.setChecked(False)
        self.fingerprint_cb.setToolTip("开启后会尝试识别设备类型和厂商，会显著增加扫描时间")
        options_layout.addWidget(self.fingerprint_cb)
        
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("超时:"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(1)
        self.timeout_spin.setSuffix("秒")
        self.timeout_spin.setMinimumWidth(110)
        self.timeout_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        options_layout.addLayout(timeout_layout)
        
        layout.addWidget(options_group)
        
        # 扫描按钮 - 垂直排列在扫描选项下方
        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)
        
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setMinimumHeight(36)
        self.scan_btn.clicked.connect(self._on_start_scan)
        button_layout.addWidget(self.scan_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_scan)
        button_layout.addWidget(self.stop_btn)
        
        layout.addLayout(button_layout)
        
        self.stats_label = QLabel("准备就绪")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 搜索过滤
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("输入IP、MAC或厂商过滤...")
        self.filter_input.textChanged.connect(self._filter_results)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)
        
        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(["IP地址", "MAC地址", "厂商", "设备类型", "主机名", "状态"])
        
        # 表头设置 - 使用自定义resize模式
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)  # 所有列固定宽度，由代码控制
        header.setMinimumSectionSize(50)
        header.setStretchLastSection(False)
        
        # 连接列宽拖动信号
        header.sectionResized.connect(self._on_user_resized_column)
        
        # 表格其他设置
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        
        self.result_table.itemDoubleClicked.connect(self._on_table_double_click)

        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._on_table_context_menu)
        
        layout.addWidget(self.result_table)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("扫描进度: %v/%m (%p%)")
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        return panel
    
    def _distribute_column_widths(self):
        """根据当前比例分配列宽，填满视口"""
        try:
            viewport_width = self.result_table.viewport().width()
            if viewport_width <= 0:
                return
            
            header = self.result_table.horizontalHeader()
            
            # 如果没有保存的比例，使用默认比例
            if not self._column_widths or len(self._column_widths) != 6:
                # 默认比例: IP:15%, MAC:20%, 厂商:25%, 设备类型:12%, 主机名:18%, 状态:10%
                self._column_widths = [0.15, 0.20, 0.25, 0.12, 0.18, 0.10]
            
            # 计算各列宽度（确保最小宽度50）
            total_width = viewport_width
            min_width = 50
            
            # 先计算按比例的宽度
            widths = [int(total_width * ratio) for ratio in self._column_widths]
            
            # 确保每列至少最小宽度
            for i in range(6):
                if widths[i] < min_width:
                    widths[i] = min_width
            
            # 调整使总和等于视口宽度
            current_total = sum(widths)
            if current_total != total_width:
                # 从最后一列开始调整
                diff = total_width - current_total
                widths[5] += diff
                if widths[5] < min_width:
                    widths[5] = min_width
            
            # 应用宽度（暂时断开信号避免递归）
            header.sectionResized.disconnect(self._on_user_resized_column)
            for i in range(6):
                header.resizeSection(i, widths[i])
            header.sectionResized.connect(self._on_user_resized_column)
            
        except Exception as e:
            logger.debug(f"Distribute column widths error: {e}")
    
    def _on_user_resized_column(self, logical_index, old_size, new_size):
        """用户拖动列宽时，调整相邻列保持总宽不变"""
        try:
            header = self.result_table.horizontalHeader()
            viewport_width = self.result_table.viewport().width()
            
            # 计算宽度变化
            delta = new_size - old_size
            
            if delta == 0:
                return
            
            # 找到要调整的相邻列
            # 如果是向右拖动（增大当前列），则减小下一列
            # 如果是向左拖动（减小当前列），则增大下一列
            next_col = logical_index + 1
            
            if next_col < 6:
                next_width = header.sectionSize(next_col)
                new_next_width = next_width - delta
                
                # 确保下一列不小于最小宽度
                if new_next_width >= 50:
                    # 临时断开信号避免递归
                    header.sectionResized.disconnect(self._on_user_resized_column)
                    header.resizeSection(next_col, new_next_width)
                    header.sectionResized.connect(self._on_user_resized_column)
                else:
                    # 如果下一列不能更小，限制当前列
                    max_current = old_size + (next_width - 50)
                    if max_current > 50:
                        header.sectionResized.disconnect(self._on_user_resized_column)
                        header.resizeSection(logical_index, max_current)
                        header.sectionResized.connect(self._on_user_resized_column)
            
            # 更新比例并保存
            self._update_column_ratios()
            self._save_column_widths_delayed()
            
        except Exception as e:
            logger.debug(f"User resize column error: {e}")
    
    def _update_column_ratios(self):
        """更新列宽比例"""
        try:
            header = self.result_table.horizontalHeader()
            viewport_width = self.result_table.viewport().width()
            
            if viewport_width > 0:
                self._column_widths = [
                    header.sectionSize(i) / viewport_width 
                    for i in range(6)
                ]
        except Exception:
            pass
    
    def _save_column_widths_delayed(self):
        """延迟保存列宽"""
        if self._resize_timer:
            self._resize_timer.stop()
        else:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._save_column_widths)
        self._resize_timer.start(500)
    
    def _save_column_widths(self):
        """保存列宽比例"""
        try:
            self._config.set("ui.device_scan_column_widths", self._column_widths)
            logger.debug(f"Saved column width ratios: {self._column_widths}")
        except Exception as e:
            logger.debug(f"Save column widths error: {e}")
    
    def _restore_column_widths(self):
        """恢复列宽比例"""
        try:
            saved = self._config.get("ui.device_scan_column_widths", [])
            if saved and len(saved) == 6:
                self._column_widths = saved
                logger.debug(f"Restored column width ratios: {saved}")
            else:
                # 默认比例
                self._column_widths = [0.15, 0.20, 0.25, 0.12, 0.18, 0.10]
            
            # 应用列宽
            self._distribute_column_widths()
            
        except Exception as e:
            logger.debug(f"Restore column widths error: {e}")
            self._column_widths = [0.15, 0.20, 0.25, 0.12, 0.18, 0.10]
            self._distribute_column_widths()
    
    def _load_networks(self):
        """加载可用网络"""
        try:
            networks = get_local_networks()
            if networks:
                self.cidr_combo.setText(networks[0]["cidr"])
                self.interface_label.setText(f"网卡: {networks[0]['interface']}")
            else:
                self.interface_label.setText("未检测到网卡")
                self.auto_range_cb.setChecked(False)
        except Exception:
            self.interface_label.setText("网卡检测失败")
    
    def _on_auto_range_changed(self, state):
        """自动范围选项变化"""
        enabled = not self.auto_range_cb.isChecked()
        self.cidr_combo.setEnabled(enabled)
        self.manual_range.setEnabled(enabled)
    
    def _on_start_scan(self):
        """开始扫描"""
        if self.auto_range_cb.isChecked():
            ip_range = self.cidr_combo.text().strip()
        else:
            ip_range = self.manual_range.text().strip()
        
        if not ip_range:
            QMessageBox.warning(self, "警告", "请输入扫描范围")
            return
        
        self.result_table.setRowCount(0)
        self._found_devices = []
        self.filter_input.clear()
        
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.stats_label.setText("扫描中...")
        
        self._scanner.use_arp = self.arp_cb.isChecked()
        self._scanner.use_icmp = self.icmp_cb.isChecked()
        self._scanner.use_tcp = self.tcp_cb.isChecked()
        self._scanner.use_onvif = self.onvif_cb.isChecked()
        self._scanner.use_fingerprint = self.fingerprint_cb.isChecked()
        self._scanner.timeout = self.timeout_spin.value()
        
        self._scanner.start_scan(
            ip_range,
            use_arp=self.arp_cb.isChecked(),
            use_icmp=self.icmp_cb.isChecked(),
            use_tcp=self.tcp_cb.isChecked(),
            use_onvif=self.onvif_cb.isChecked(),
            timeout=self.timeout_spin.value()
        )
    
    def _on_stop_scan(self):
        """停止扫描"""
        self._scanner.stop_scan()
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stats_label.setText("已停止")
    
    def _on_devices_found(self, devices: list):
        """发现设备"""
        for device in devices:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            
            self.result_table.setItem(row, 0, QTableWidgetItem(device.ip))
            self.result_table.setItem(row, 1, QTableWidgetItem(device.mac))
            
            display_vendor = device.get_display_vendor()
            vendor_item = QTableWidgetItem(display_vendor)
            if '(?)' in display_vendor:
                vendor_item.setForeground(Qt.GlobalColor.gray)
            self.result_table.setItem(row, 2, vendor_item)
            
            device_type = device.get_display_type()
            self.result_table.setItem(row, 3, QTableWidgetItem(device_type))
            self.result_table.setItem(row, 4, QTableWidgetItem(device.hostname))
            
            status_text = "在线"
            if device.fingerprint_methods:
                status_text += f" ({'/'.join(device.fingerprint_methods)})"
            self.result_table.setItem(row, 5, QTableWidgetItem(status_text))
            
            self._found_devices.append(device)
        
        self.stats_label.setText(f"发现 {len(self._found_devices)} 台设备")
    
    def _on_progress_update(self, current: int, total: int):
        """进度更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
    
    def _on_scan_finished(self):
        """扫描完成"""
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.stats_label.setText(f"扫描完成，共发现 {len(self._found_devices)} 台设备")
    
    def _on_scan_error(self, error_msg: str):
        """扫描错误"""
        QMessageBox.critical(self, "扫描错误", error_msg)
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
    
    def _filter_results(self, text: str):
        """过滤结果"""
        filter_text = text.lower()
        for row in range(self.result_table.rowCount()):
            show = False
            for col in range(self.result_table.columnCount()):
                item = self.result_table.item(row, col)
                if item and filter_text in item.text().lower():
                    show = True
                    break
            self.result_table.setRowHidden(row, not show)
    
    def _on_table_context_menu(self, position):
        """右键菜单"""
        item = self.result_table.itemAt(position)
        if not item:
            return
        
        row = item.row()
        if row < 0 or row >= len(self._found_devices):
            return
        
        device = self._found_devices[row]
        menu = QMenu()
        
        # 复制菜单 - 始终显示
        copy_menu = menu.addMenu("复制")
        copy_menu.addAction("复制IP", lambda: self._copy_cell(row, 0))
        copy_menu.addAction("复制MAC", lambda: self._copy_cell(row, 1))
        copy_menu.addAction("复制整行", lambda: self._copy_row(row))
        
        # 登录设备 - 仅对监控设备显示
        if self._is_camera_device(device):
            menu.addSeparator()
            menu.addAction("登录设备", lambda: self._login_in_connection_tab(device))
        
        menu.exec(self.result_table.viewport().mapToGlobal(position))
    
    def _copy_cell(self, row: int, col: int):
        """复制单元格"""
        item = self.result_table.item(row, col)
        if item:
            QApplication.clipboard().setText(item.text())
    
    def _copy_row(self, row: int):
        """复制整行"""
        texts = []
        for col in range(self.result_table.columnCount()):
            item = self.result_table.item(row, col)
            texts.append(item.text() if item else "")
        QApplication.clipboard().setText("\t".join(texts))
    
    def _on_table_double_click(self, item):
        """双击 - 打开Web登录界面"""
        row = item.row()
        if 0 <= row < len(self._found_devices):
            device = self._found_devices[row]
            self._open_web_interface(device.ip)
    
    def _is_camera_device(self, device) -> bool:
        """判断是否为监控设备（主流厂商）"""
        vendor = device.get_display_vendor().lower()
        device_type = device.get_display_type().lower()
        
        # 知名监控设备厂商关键词
        camera_vendors = ['hikvision', 'dahua', 'uniview', 'tiandy', 'jovision', 
                         '海康', '大华', '宇视', '天地伟业', '中维']
        
        # 检查厂商名
        for keyword in camera_vendors:
            if keyword in vendor:
                return True
        
        # 检查设备类型
        if 'camera' in device_type or 'nvr' in device_type or 'dvr' in device_type:
            return True
        
        # 检查开放端口（监控设备特征端口）
        camera_ports = [554, 8000, 8080, 37777]  # RTSP, SDK, 大华
        if hasattr(device, 'open_ports') and device.open_ports:
            for port in camera_ports:
                if port in device.open_ports:
                    return True
        
        return False
    
    def _open_web_interface(self, ip: str, port: int = 80):
        """打开设备Web管理界面"""
        url = f"http://{ip}:{port}"
        try:
            QDesktopServices.openUrl(QUrl(url))
            self.log_message.emit(f"正在打开设备Web界面: {url}")
        except Exception as e:
            logger.error(f"打开Web界面失败: {e}")
            QMessageBox.warning(self, "打开失败", f"无法打开设备Web界面:\n{url}\n\n错误: {e}")
    
    def _login_in_connection_tab(self, device):
        """在设备连接界面登录该设备"""
        self.device_selected.emit({
            'ip': device.ip,
            'mac': device.mac,
            'vendor': device.get_display_vendor(),
            'hostname': device.hostname
        })
        self.log_message.emit(f"已切换到连接界面: {device.ip}")
    
    def _connect_signals(self):
        """连接信号"""
        self._scanner.devices_found.connect(self._on_devices_found)
        self._scanner.progress_update.connect(self._on_progress_update)
        self._scanner.scan_finished.connect(self._on_scan_finished)
        self._scanner.scan_error.connect(self._on_scan_error)
