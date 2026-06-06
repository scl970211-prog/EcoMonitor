"""设备连接标签页。"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QGroupBox,
    QMessageBox, QFormLayout, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...core import Device, SDKLoader
from ...utils.config import get_config


class ConnectionTab(QWidget):
    """设备连接标签页"""
    
    # 信号: 连接状态变化(bool), 设备信息(dict)
    connection_changed = pyqtSignal(bool, dict)
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._device: Device = None
        self._config = get_config()
        self._init_ui()
    
    def _init_ui(self):
        device_config = self._config.get("device", {})
        default_ip = str(device_config.get("ip", "") or "")
        default_port = int(device_config.get("port", 8000) or 8000)
        default_http_port = int(device_config.get("http_port", 80) or 80)
        default_username = str(device_config.get("username", "admin") or "admin")
        default_password = str(device_config.get("password", "") or "")

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 连接参数组
        conn_group = QGroupBox("连接参数")
        form_layout = QFormLayout(conn_group)
        
        # IP 地址
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("例如: 192.168.1.64")
        self.ip_input.setText(default_ip)
        form_layout.addRow("IP 地址:", self.ip_input)
        
        # SDK 端口（设备连接端口）
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(default_port)
        self.port_input.setToolTip("设备 SDK 连接端口，默认 8000")
        form_layout.addRow("SDK 端口:", self.port_input)
        
        # HTTP 端口（ISAPI 端口）
        self.http_port_input = QSpinBox()
        self.http_port_input.setRange(1, 65535)
        self.http_port_input.setValue(default_http_port)
        self.http_port_input.setToolTip("ISAPI/HTTP 端口，用于获取通道名称和状态，默认 80")
        form_layout.addRow("HTTP 端口:", self.http_port_input)
        
        # 用户名
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("例如: admin")
        self.username_input.setText(default_username)
        form_layout.addRow("用户名:", self.username_input)
        
        # 密码
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setText(default_password)
        form_layout.addRow("密码:", self.password_input)
        
        # 自动连接设置
        self.auto_connect_checkbox = QCheckBox("启动后自动连接")
        self.auto_connect_checkbox.setChecked(
            self._config.get('connection.auto_connect', False)
        )
        self.auto_connect_checkbox.setToolTip("程序启动后自动使用保存的参数连接设备")
        self.auto_connect_checkbox.stateChanged.connect(self._on_auto_connect_changed)
        form_layout.addRow("自动连接:", self.auto_connect_checkbox)
        
        # 自动播放设置
        self.auto_play_checkbox = QCheckBox("连接成功后自动播放所有通道")
        self.auto_play_checkbox.setChecked(
            self._config.get('preview.auto_play_all', False)
        )
        self.auto_play_checkbox.setToolTip("连接成功后自动将所有通道按顺序加入播放")
        self.auto_play_checkbox.stateChanged.connect(self._on_auto_play_changed)
        form_layout.addRow("自动播放:", self.auto_play_checkbox)
        
        layout.addWidget(conn_group)
        
        # 按钮组
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.setStyleSheet("font-size: 14px; padding: 10px 30px;")
        self.connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setObjectName("danger")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        btn_layout.addWidget(self.disconnect_btn)

        # 内联连接状态标签
        self.conn_status_label = QLabel("未连接")
        self.conn_status_label.setStyleSheet("color: #999; font-size: 8pt;")
        btn_layout.addWidget(self.conn_status_label)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # 状态显示组
        status_group = QGroupBox("设备信息")
        status_layout = QFormLayout(status_group)

        self.device_info_placeholder = QLabel("连接设备后显示详情")
        self.device_info_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_info_placeholder.setStyleSheet("color: #bbb; font-size: 9pt;")
        status_layout.addRow(self.device_info_placeholder)

        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addRow("连接状态:", self.status_label)
        
        self.device_type_label = QLabel("-")
        status_layout.addRow("设备型号:", self.device_type_label)
        
        self.serial_label = QLabel("-")
        status_layout.addRow("序列号:", self.serial_label)
        
        self.channel_label = QLabel("-")
        status_layout.addRow("通道数量:", self.channel_label)
        
        layout.addWidget(status_group)
        layout.addStretch()
    
    def _on_connect(self):
        """连接按钮点击"""
        self.connect_current_inputs(show_error_dialog=True)

    def set_ip(self, ip: str, port: int = 8000, http_port: int = 80):
        """设置设备地址，供设备搜索页调用。"""
        self.ip_input.setText(ip)
        self.port_input.setValue(port)
        self.http_port_input.setValue(http_port)
        self.ip_input.setFocus()
        self.log_message.emit(f"已填充IP: {ip}:{port} (HTTP:{http_port})")

    def perform_auto_login(self, ip: str, port: int, username: str, password: str, http_port: int = 80):
        """执行自动登录，兼容主窗口现有调用。"""
        self.ip_input.setText(ip)
        self.port_input.setValue(port)
        self.http_port_input.setValue(http_port)
        self.username_input.setText(username)
        self.password_input.setText(password)
        return self.connect_device(
            ip=ip,
            port=port,
            http_port=http_port,
            username=username,
            password=password,
            show_error_dialog=False,
            auto=True,
        )

    def connect_current_inputs(self, show_error_dialog: bool = True) -> bool:
        """使用当前输入框参数连接设备。"""
        return self.connect_device(
            ip=self.ip_input.text().strip(),
            port=self.port_input.value(),
            http_port=self.http_port_input.value(),
            username=self.username_input.text().strip(),
            password=self.password_input.text(),
            show_error_dialog=show_error_dialog,
            auto=False,
        )

    def auto_connect_saved_device(self) -> bool:
        """自动连接上次成功连接的设备。"""
        ip = self.ip_input.text().strip()
        username = self.username_input.text().strip()
        if not ip or not username:
            return False

        return self.connect_device(
            ip=ip,
            port=self.port_input.value(),
            http_port=self.http_port_input.value(),
            username=username,
            password=self.password_input.text(),
            show_error_dialog=False,
            auto=True,
        )

    def connect_device(
        self,
        ip: str,
        port: int,
        http_port: int,
        username: str,
        password: str,
        show_error_dialog: bool = True,
        auto: bool = False,
    ) -> bool:
        """执行一次实际连接，支持手动和自动连接共用。"""
        if not ip:
            if show_error_dialog:
                QMessageBox.warning(self, "提示", "请输入 IP 地址")
            return False

        if not username:
            if show_error_dialog:
                QMessageBox.warning(self, "提示", "请输入用户名")
            return False

        if not password:
            if show_error_dialog:
                QMessageBox.warning(self, "提示", "请输入密码")
            return False

        try:
            if not SDKLoader().load():
                raise RuntimeError("SDK 加载失败")
        except Exception as e:
            if show_error_dialog:
                QMessageBox.critical(self, "错误", f"SDK 加载失败: {e}")
            else:
                self.status_label.setText("自动连接失败，请检测连接参数。")
                self.status_label.setStyleSheet("color: #c42b1c; font-weight: bold;")
            return False

        self._device = Device(ip, port, username, password, http_port)

        try:
            self.connect_btn.setEnabled(False)
            self.connect_btn.setText("连接中...")

            if self._device.login():
                self._save_connection_settings(ip, port, http_port, username, password)
                self._update_ui_connected()
                self.conn_status_label.setText(f"已连接 {ip}:{port}")
                self.conn_status_label.setStyleSheet("color: #107c10; font-size: 8pt; font-weight: bold;")
                info = self._get_device_info()
                self.connection_changed.emit(True, info)
                self.log_message.emit(f"设备连接成功: {ip}")
                return True

            if show_error_dialog:
                QMessageBox.critical(self, "错误", "登录失败")
            self._set_connect_failed_state(auto=auto)
            return False
        except Exception as e:
            if show_error_dialog:
                QMessageBox.critical(self, "错误", f"连接失败: {e}")
            self._set_connect_failed_state(auto=auto)
            return False
        finally:
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("连接设备")

    def _set_connect_failed_state(self, auto: bool = False):
        """设置连接失败后的界面状态。"""
        self._device = None
        self._update_ui_disconnected()
        self.connection_changed.emit(False, {})
        self.log_message.emit("设备已断开")
        if auto:
            self.status_label.setText("自动连接失败，请检测连接参数。")
            self.status_label.setStyleSheet("color: #c42b1c; font-weight: bold;")
            self.conn_status_label.setText("自动连接失败")
            self.conn_status_label.setStyleSheet("color: #c42b1c; font-size: 8pt;")
        else:
            self.conn_status_label.setText("连接失败")
            self.conn_status_label.setStyleSheet("color: #c42b1c; font-size: 8pt;")
    
    def _on_disconnect(self):
        """断开连接"""
        if self._device:
            self._device.logout()
            self._device = None
        
        self._update_ui_disconnected()
        self.connection_changed.emit(False, {})
    
    def _update_ui_connected(self):
        """更新 UI 为已连接状态"""
        self.device_info_placeholder.hide()
        self.status_label.setText("已连接")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        
        self.ip_input.setEnabled(False)
        self.port_input.setEnabled(False)
        self.http_port_input.setEnabled(False)
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        
        # 更新设备信息
        if self._device and self._device.device_info:
            info = self._device.device_info
            
            # 序列号
            serial = bytes(info.sSerialNumber).decode('utf-8', errors='ignore').strip('\x00')
            self.serial_label.setText(serial)
            
            # 通道数
            analog_channels = int(info.byChanNum)
            ip_channels = self._device.get_ip_channel_count()
            channel_count = analog_channels + ip_channels
            self.channel_label.setText(f"{channel_count} (模拟:{analog_channels}, IP:{ip_channels})")
            
            # 设备类型
            device_types = {
                1: "DVR", 2: "DVS", 3: "IPC", 4: "NVR",
                5: "NVR", 6: "NVR", 7: "NVR", 8: "NVR",
                9: "NVR", 10: "NVR", 90: "NVR"
            }
            device_type = device_types.get(info.byDVRType, f"未知({info.byDVRType})")
            self.device_type_label.setText(device_type)
    
    def _update_ui_disconnected(self):
        """更新 UI 为未连接状态"""
        self.device_info_placeholder.show()
        self.conn_status_label.setText("未连接")
        self.conn_status_label.setStyleSheet("color: #999; font-size: 8pt;")
        self.status_label.setText("未连接")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        
        self.ip_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self.http_port_input.setEnabled(True)
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)
        
        self.device_type_label.setText("-")
        self.serial_label.setText("-")
        self.channel_label.setText("-")
    
    def _on_auto_connect_changed(self, state):
        """自动连接设置改变"""
        enabled = state == Qt.CheckState.Checked.value
        self._config.set('connection.auto_connect', enabled)
    
    def _on_auto_play_changed(self, state):
        """自动播放设置改变"""
        enabled = state == Qt.CheckState.Checked.value
        self._config.set('preview.auto_play_all', enabled)
        if enabled:
            # 如果启用自动播放，禁用恢复布局（互斥）
            self._config.set('preview.restore_on_connect', False)

    def _save_connection_settings(self, ip: str, port: int, http_port: int, username: str, password: str):
        """保存最近成功的连接参数。"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            self._config.set("device.ip", ip)
            self._config.set("device.port", port)
            self._config.set("device.http_port", http_port)
            self._config.set("device.username", username)
            self._config.set("device.password", password)
        except Exception as e:
            logger.error(f"保存连接参数失败: {e}")
    
    def _get_device_info(self) -> dict:
        """获取设备信息字典"""
        if not self._device:
            return {}
        
        info = self._device.device_info
        if not info:
            return {}
        
        return {
            'ip': self._device.ip,
            'port': self._device.port,
            'username': self._device.username,
            'password': self._device.password,
            'serial': bytes(info.sSerialNumber).decode('utf-8', errors='ignore').strip('\x00'),
            'channel_count': self._device.get_channel_count(),
            'analog_channels': int(info.byChanNum),
            'ip_channels': self._device.get_ip_channel_count(),
            'device_type': info.byDVRType,
            'channels': self._device.get_channel_list()
        }
    
    def get_device(self) -> Device:
        """获取当前设备实例"""
        return self._device
    
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._device is not None and self._device.is_connected

    def disconnect(self):
        """供主窗口统一调用的断开接口。"""
        self._on_disconnect()
