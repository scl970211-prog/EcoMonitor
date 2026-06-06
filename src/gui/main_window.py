"""
主窗口 - EcoMonitor 生态监控平台 (PyQt6 整合版 V2)

整合功能：
1. 设备搜索 - 局域网设备扫描
2. 设备连接 - 连接视频设备
3. 视频预览 - 多通道实时预览（V2 硬件解码）
4. 批量下载 - 录像下载（V2 检索与下载）
5. 下载管理 - 下载任务管理（V2 段级管理）
6. 终端调试 - SSH/Telnet 通用设备调试
7. 网络质量 - Ping/MTU/吞吐量测试
8. 宽带测速 - 网速测试
9. IP冲突检测 - 私接设备排查
10. 流量分析 - DSCP 检测与轻量抓包
11. 抓包分析 - Wireshark/tshark 快捷入口
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QTextEdit, QLabel, QPushButton,
    QDialog, QProgressBar, QComboBox, QLineEdit, QFrame, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from ..core import SDKLoader, Device, DownloadManager
from ..core.app_state import get_app_state
from ..core.event_bus import get_event_bus, EventType
from ..utils.config import get_config
from .tabs.device_scan_tab import DeviceScanTab
from .tabs.connection_tab import ConnectionTab
from .tabs.preview_tab_v2 import PreviewTabV2
from .tabs.download_tab_v2 import DownloadTabV2
from .tabs.download_manager_tab_v2 import DownloadManagerTabV2
from .tabs.terminal_tab import TerminalTab
from .tabs.network_quality_tab import NetworkQualityTab
from .tabs.speedtest_tab import SpeedtestTab
from .tabs.ip_conflict_tab import IPConflictTab
from .tabs.traffic_analysis_tab import TrafficAnalysisTab
from .tabs.packet_capture_tab import PacketCaptureTab
from .styles import MAIN_WINDOW, LOG_TOOLBAR_BTN

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """EcoMonitor 生态监控平台主窗口"""
    
    WINDOW_TITLE = "EcoMonitor 生态监控平台"
    FOOTER_TEXT = "软件开发：中国水利水电科学研究院（技术人员：孙成龙）"
    
    # 信号
    log_message = pyqtSignal(str)
    device_connected = pyqtSignal(object, dict)  # Device, info_dict
    device_disconnected = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(1400, 900)
        
        # 全局状态与事件总线
        self._app_state = get_app_state()
        self._event_bus = get_event_bus()
        self._event_bus.start()
        
        # 配置
        self._config = get_config()
        
        # 当前连接的设备
        self._current_device: Device = None
        self._device_info: dict = {}
        self._download_manager = DownloadManager(max_concurrent=self._config.get("download.concurrent", 2))
        
        # 日志缓存
        self._log_entries = []
        
        # 自动登录相关
        self._auto_login_dialog = None
        self._auto_login_attempted = False
        
        # 初始化组件
        self._init_ui()
        self._connect_signals()
        
        # 检查 SDK
        self._check_sdk()
        
        # 尝试自动登录（延迟执行，等待UI完全加载）
        QTimer.singleShot(500, self._attempt_auto_login)
    
    def _init_ui(self):
        """初始化界面"""
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 使用分割器分割主内容和日志面板
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.main_splitter)
        
        # 上半部分：标签页
        self.tab_widget = QTabWidget()
        self._add_tabs()
        self.main_splitter.addWidget(self.tab_widget)
        
        # 下半部分：日志面板
        log_panel = self._create_log_panel()
        self.main_splitter.addWidget(log_panel)
        
        # 设置分割比例（标签页占80%，日志占20%）
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        
        # 设置日志面板最小高度
        log_panel.setMinimumHeight(100)
        
        # 从配置恢复分割器位置
        self._restore_splitter_state()
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        footer_label = QLabel(self.FOOTER_TEXT)
        footer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer_label.setStyleSheet("color: #666666; font-size: 9pt;")
        self.status_bar.addPermanentWidget(footer_label)
        
        # 应用样式
        self._apply_styles()
    
    def _restore_splitter_state(self):
        """从配置恢复分割器状态"""
        splitter_state = self._config.get("ui.main_splitter_state", None)
        if splitter_state:
            try:
                self.main_splitter.restoreState(bytes.fromhex(splitter_state))
            except Exception:
                self.main_splitter.setSizes([700, 150])
        else:
            self.main_splitter.setSizes([700, 150])
    
    def _save_splitter_state(self):
        """保存分割器状态到配置"""
        try:
            state = self.main_splitter.saveState().tohex()
            self._config.set("ui.main_splitter_state", state)
        except Exception:
            pass
    
    def _add_tabs(self):
        """添加标签页"""
        # 1. 设备搜索
        self.scan_tab = DeviceScanTab()
        self.scan_tab.device_selected.connect(self._on_device_selected)
        self.tab_widget.addTab(self.scan_tab, "🔍 设备搜索")
        
        # 2. 设备连接
        self.connection_tab = ConnectionTab()
        self.connection_tab.connection_changed.connect(self._on_connection_changed)
        self.connection_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.connection_tab, "🔗 设备连接")
        
        # 3. 视频预览 (V2)
        self.preview_tab = PreviewTabV2()
        self.preview_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.preview_tab, "📹 视频预览")
        self.tab_widget.setTabEnabled(2, False)  # 初始禁用
        
        # 4. 批量下载 (V2)
        self.download_tab = DownloadTabV2(self._download_manager)
        self.download_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.download_tab, "⬇️ 批量下载")
        self.tab_widget.setTabEnabled(3, False)
        
        # 5. 下载管理 (V2)
        self.manager_tab = DownloadManagerTabV2(self._download_manager)
        self.tab_widget.addTab(self.manager_tab, "📂 下载管理")
        
        # 6. 终端调试
        self.terminal_tab = TerminalTab()
        self.terminal_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.terminal_tab, "🔧 终端调试")
        
        # 7. 网络质量
        self.network_quality_tab = NetworkQualityTab()
        self.network_quality_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.network_quality_tab, "⚡ 网络质量")
        
        # 8. 宽带测速
        self.speedtest_tab = SpeedtestTab()
        self.speedtest_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.speedtest_tab, "🌐 宽带测速")
        
        # 9. IP冲突检测
        self.ip_conflict_tab = IPConflictTab()
        self.ip_conflict_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.ip_conflict_tab, "📡 IP冲突检测")
        
        # 10. 流量分析
        self.traffic_analysis_tab = TrafficAnalysisTab()
        self.traffic_analysis_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.traffic_analysis_tab, "📊 流量分析")
        
        # 11. 抓包分析
        self.packet_capture_tab = PacketCaptureTab()
        self.packet_capture_tab.log_message.connect(self.log)
        self.tab_widget.addTab(self.packet_capture_tab, "🦈 抓包分析")
    
    def _create_log_panel(self) -> QWidget:
        """创建日志面板"""
        panel = QWidget()
        panel.setStyleSheet("background:#fff; border-top: 1px solid #e0e0e0;")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # 工具栏
        toolbar = QWidget()
        toolbar.setStyleSheet("background:#f9f9f9; border-bottom: 1px solid #e0e0e0;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 4, 10, 4)
        toolbar_layout.setSpacing(6)
        
        title_label = QLabel("运行日志")
        title_label.setStyleSheet("font-weight:600; font-size:8pt; color:#333;")
        toolbar_layout.addWidget(title_label)
        toolbar_layout.addStretch()
        
        # 级别过滤
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["全部", "信息", "警告", "错误"])
        self.log_level_combo.setFixedHeight(22)
        self.log_level_combo.setFixedWidth(70)
        self.log_level_combo.setStyleSheet(
            "QComboBox{border:1px solid #ccc;border-radius:4px;font-size:8pt;padding:0 4px;background:#fff;}"
        )
        self.log_level_combo.currentTextChanged.connect(self._render_log)
        toolbar_layout.addWidget(self.log_level_combo)
        
        # 搜索框
        self.log_search_input = QLineEdit()
        self.log_search_input.setPlaceholderText("搜索...")
        self.log_search_input.setFixedHeight(22)
        self.log_search_input.setFixedWidth(120)
        self.log_search_input.setStyleSheet(
            "QLineEdit{border:1px solid #ccc;border-radius:4px;font-size:8pt;padding:0 6px;background:#fff;}"
        )
        self.log_search_input.textChanged.connect(self._render_log)
        toolbar_layout.addWidget(self.log_search_input)
        
        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(48)
        clear_btn.setStyleSheet(LOG_TOOLBAR_BTN)
        clear_btn.clicked.connect(self._clear_log)
        toolbar_layout.addWidget(clear_btn)
        
        # 导出按钮
        export_btn = QPushButton("导出")
        export_btn.setFixedHeight(22)
        export_btn.setFixedWidth(48)
        export_btn.setStyleSheet(LOG_TOOLBAR_BTN)
        export_btn.clicked.connect(self._export_log)
        toolbar_layout.addWidget(export_btn)
        
        panel_layout.addWidget(toolbar)
        
        # 日志文本区
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(80)
        panel_layout.addWidget(self.log_text)
        
        return panel
    
    def _connect_signals(self):
        """连接信号"""
        self.log_message.connect(self._append_log)
        self._download_manager.task_log.connect(self.log)
    
    def _check_sdk(self):
        """检查 SDK"""
        from ..core.path_resolver import check_sdk_exists
        
        exists, msg = check_sdk_exists()
        if not exists:
            self.log(f"[警告] SDK 未就绪: {msg}")
            self.status_bar.showMessage("SDK 未就绪")
        else:
            self.log("SDK 检查通过")
    
    def _on_device_selected(self, device_info: dict):
        """设备搜索页选中设备"""
        ip = device_info.get("ip", "")
        action = device_info.get("action", "")
        vendor = device_info.get("vendor", "")
        
        if not ip:
            return
        
        self.log(f"从设备搜索选择: {ip} ({vendor})")
        
        # 切换到连接页
        self.tab_widget.setCurrentWidget(self.connection_tab)
        
        # 判断端口
        if "hikvision" in vendor.lower():
            port = 8000
        elif "dahua" in vendor.lower():
            port = 37777
        else:
            port = 8000
        
        # 设置IP和端口
        self.connection_tab.set_ip(ip, port)
        
        if action == "connect_sdk":
            self.log(f"准备SDK连接设备: {ip}:{port}")
            self.status_bar.showMessage("请确认连接信息后点击连接按钮", 5000)
        else:
            self.log(f"已填入IP: {ip}")
    
    def _on_connection_changed(self, connected: bool, device_info: dict = None):
        """设备连接状态变化"""
        if connected and device_info:
            self._device_info = device_info
            self.log(f"设备已连接: {device_info.get('ip', '')}")
            self.status_bar.showMessage(f"已连接到: {device_info.get('ip', '')}")
            
            # 启用相关标签页
            self.tab_widget.setTabEnabled(2, True)  # 视频预览
            self.tab_widget.setTabEnabled(3, True)  # 批量下载
            
            # 传递设备信息
            self.preview_tab.set_device_info(device_info)
            self.download_tab.set_device_info(device_info)
            self._current_device = self.connection_tab.get_device()
            self.preview_tab.set_device(self._current_device)
            self.download_tab.set_device(self._current_device)
            
            # 更新全局状态
            self._app_state.set_device(self._current_device, device_info)
            
            # 切换到预览页
            self.tab_widget.setCurrentWidget(self.preview_tab)
            
            # 发射信号
            self.device_connected.emit(self._current_device, device_info)
            
            # 发布事件总线
            self._event_bus.emit(EventType.DEVICE_CONNECTED, {
                "device": self._current_device,
                "device_info": device_info
            })
        else:
            self._device_info = {}
            self.log("设备已断开")
            self.status_bar.showMessage("设备未连接")
            
            # 禁用相关标签页
            self.tab_widget.setTabEnabled(2, False)
            self.tab_widget.setTabEnabled(3, False)
            
            self.preview_tab.set_device(None)
            self.preview_tab.set_device_info({})
            self.download_tab.set_device(None)
            self.download_tab.set_device_info({})
            
            # 更新全局状态
            self._app_state.set_device(None)
            
            self.device_disconnected.emit()
            self._event_bus.emit(EventType.DEVICE_DISCONNECTED, {})
    
    def _append_log(self, message: str):
        """添加日志（增量渲染）"""
        now = datetime.now().strftime('%H:%M:%S')
        
        level = 'INFO'
        if '[ERROR]' in message or '错误' in message or '失败' in message:
            level = 'ERROR'
        elif '[WARN]' in message or '警告' in message:
            level = 'WARN'
        
        entry = {'level': level, 'text': message, 'time': now}
        self._log_entries.append(entry)
        
        if len(self._log_entries) > 2000:
            self._log_entries = self._log_entries[-2000:]
            self._render_log()
            return
        
        # 增量插入
        filter_level = self._get_current_filter_level()
        search = self.log_search_input.text().strip().lower()
        
        if filter_level != 'ALL' and level != filter_level:
            return
        if search and search not in message.lower():
            return
        
        line = self._format_log_line(entry)
        self.log_text.append(line)
    
    def _format_log_line(self, entry: dict) -> str:
        """格式化单条日志为 HTML"""
        level_colors = {
            'INFO': ('#e6f2ff', '#0078d4'),
            'WARN': ('#fff4e0', '#d67f00'),
            'ERROR': ('#fde7e9', '#c42b1c'),
        }
        bg, fg = level_colors.get(entry['level'], ('#f3f3f3', '#555'))
        level_abbr = {'INFO': 'INFO', 'WARN': 'WARN', 'ERROR': 'ERR '}.get(entry['level'], entry['level'])
        return (
            f'<span style="color:#888;">{entry["time"]}</span>&nbsp;'
            f'<span style="background:{bg};color:{fg};padding:0 3px;border-radius:2px;font-size:8pt;">{level_abbr}</span>&nbsp;'
            f'<span>{entry["text"]}</span>'
        )
    
    def _get_current_filter_level(self) -> str:
        """获取当前日志过滤级别"""
        level_map = {'全部': 'ALL', '信息': 'INFO', '警告': 'WARN', '错误': 'ERROR'}
        return level_map.get(self.log_level_combo.currentText(), 'ALL')
    
    def _render_log(self):
        """渲染日志（全量重绘，仅在过滤条件变化或截断时调用）"""
        filter_level = self._get_current_filter_level()
        search = self.log_search_input.text().strip().lower()
        
        html_parts = []
        for entry in self._log_entries:
            if filter_level != 'ALL' and entry['level'] != filter_level:
                continue
            if search and search not in entry['text'].lower():
                continue
            html_parts.append(self._format_log_line(entry))
        
        self.log_text.setHtml('<br>'.join(html_parts))
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _clear_log(self):
        """清空日志"""
        self._log_entries.clear()
        self.log_text.clear()
    
    def _export_log(self):
        """导出日志"""
        from PyQt6.QtWidgets import QFileDialog
        
        default_name = f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", default_name, "文本文件 (*.txt)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                for entry in self._log_entries:
                    f.write(f"{entry['time']} [{entry['level']}] {entry['text']}\n")
            self.log(f"日志已导出: {path}")
    
    def log(self, message: str):
        """外部调用的日志方法"""
        self.log_message.emit(message)
    
    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(MAIN_WINDOW)
    
    def _attempt_auto_login(self):
        """尝试自动登录上次连接的设备"""
        if self._auto_login_attempted:
            return
        self._auto_login_attempted = True
        
        if not self._config.get("connection.auto_connect", False):
            return
        
        ip = self._config.get("device.ip", "")
        username = self._config.get("device.username", "")
        password = self._config.get("device.password", "")
        if not ip or not username or not password:
            self.log("[提示] 已启用自动连接，但连接参数不完整，请手动输入")
            return
        
        self._show_auto_login_dialog()
        QTimer.singleShot(0, self._perform_auto_login)
    
    def _show_auto_login_dialog(self):
        """显示自动登录对话框"""
        device_config = self._config.get("device", {})
        ip = device_config.get("ip", "")
        
        dialog = QDialog(self)
        dialog.setWindowTitle("自动登录")
        dialog.setFixedSize(400, 180)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("正在自动登录上次连接的设备...")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel(f"IP地址: {ip}")
        info.setStyleSheet("font-size: 12px; color: #666;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        
        self._auto_login_countdown_label = QLabel("正在连接，请稍候...")
        self._auto_login_countdown_label.setStyleSheet("font-size: 11px; color: #999;")
        self._auto_login_countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._auto_login_countdown_label)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(lambda: self._cancel_auto_login(dialog))
        btn_layout.addWidget(cancel_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        self._auto_login_dialog = dialog
        dialog.show()
    
    def _cancel_auto_login(self, dialog):
        """取消自动登录"""
        self._auto_login_canceled = True
        dialog.close()
        dialog.deleteLater()
        self._auto_login_dialog = None
        self.log("已取消自动登录")
    
    def _close_auto_login_dialog(self):
        """关闭自动登录对话框"""
        if self._auto_login_dialog is not None:
            self._auto_login_dialog.close()
            self._auto_login_dialog.deleteLater()
            self._auto_login_dialog = None
    
    def _perform_auto_login(self):
        """执行自动登录"""
        if getattr(self, '_auto_login_canceled', False):
            return
        
        try:
            ip = self._config.get("device.ip", "")
            port = self._config.get("device.port", 8000)
            http_port = self._config.get("device.http_port", 80)
            username = self._config.get("device.username", "admin")
            password = self._config.get("device.password", "")
            if not ip or not password:
                return

            self.log(f"正在自动登录设备: {ip}...")
            self.tab_widget.setCurrentWidget(self.connection_tab)
            self.connection_tab.set_ip(ip, port, http_port)
            success = self.connection_tab.auto_connect_saved_device()
            if success and self.connection_tab.is_connected():
                self.log(f"自动登录成功: {ip}")
            else:
                self.log(f"[警告] 自动登录未连接成功: {ip}")
        except Exception as e:
            self.log(f"[错误] 自动登录失败: {e}")
        finally:
            self._close_auto_login_dialog()
    
    def closeEvent(self, event):
        """关闭事件"""
        # 保存分割器状态
        self._save_splitter_state()
        
        # 停止所有预览
        if hasattr(self, 'preview_tab'):
            self.preview_tab.cleanup()
        
        # 停止所有下载
        self._download_manager.shutdown()
        
        # 断开设备连接
        if self.connection_tab.is_connected():
            self.connection_tab.disconnect()
        
        # 停止事件总线
        self._event_bus.stop()
        
        # 重置全局状态
        self._app_state.reset()
        
        # 清理 SDK
        SDKLoader().cleanup()
        
        # 清理新标签页资源
        if hasattr(self, 'terminal_tab'):
            self.terminal_tab.close()
        if hasattr(self, 'traffic_analysis_tab'):
            self.traffic_analysis_tab.close()
        
        event.accept()
