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
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QTextEdit, QLabel, QPushButton,
    QDialog, QProgressBar, QComboBox, QLineEdit, QFrame, QSplitter,
    QCheckBox, QMenu, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QAction

from . import icons
from .theme import Theme, get_theme_manager, log_badge_colors, text_color

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
from .constants import TabLabel
from .styles import get_global_stylesheet

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
        
        # 主题管理器
        self._theme_manager = get_theme_manager()
        self._theme_manager.set_theme(self._config.get("ui.theme", Theme.LIGHT.value))
        
        # 当前连接的设备
        self._current_device: Device = None
        self._device_info: dict = {}
        self._download_manager = DownloadManager(max_concurrent=self._config.get("download.concurrent", 2))
        
        # 日志缓存
        self._log_entries = []
        
        # 自动登录相关
        self._auto_login_dialog = None
        self._auto_login_attempted = False
        
        # 自动初始化状态
        self._auto_full_init_queue = []
        self._auto_full_init_running = 0
        self._auto_full_init_scheduled = False
        
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
        footer_label.setObjectName("footerLabel")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_bar.addPermanentWidget(footer_label)
        
        # 应用样式与主题
        self._apply_styles()
        self._theme_manager.apply_to_app(QApplication.instance())

        # 菜单：设置 -> 启动行为
        try:
            menubar = self.menuBar()
            settings_menu = menubar.addMenu("设置")
            startup_action = QAction("启动行为...", self)
            startup_action.triggered.connect(self._open_startup_settings)
            settings_menu.addAction(startup_action)
        except Exception:
            logger.exception("创建菜单失败")
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
    
    def _create_tab_placeholder(self, label: str) -> QWidget:
        """创建空占位标签页，减少启动时组件开销"""
        placeholder = QWidget()
        placeholder.setObjectName("tab_placeholder")
        return placeholder
    
    def _register_lazy_tab(self, attr_name: str, factory, label: str, enabled: bool = True):
        """注册延迟创建标签页"""
        placeholder = self._create_tab_placeholder(label)
        placeholder.setObjectName(f"placeholder_{attr_name}")
        setattr(self, attr_name, None)
        self._lazy_tab_factories[attr_name] = {
            'factory': factory,
            'label': label,
            'enabled': enabled,
            'placeholder': placeholder,
        }
        self._lazy_tab_order.append(attr_name)
        index = self.tab_widget.addTab(placeholder, label)
        self.tab_widget.setTabEnabled(index, enabled)
        tab_icon = icons.create_tab_icon(label)
        if tab_icon is not None:
            self.tab_widget.setTabIcon(index, tab_icon)
    
    def _ensure_tab(self, attr_name: str):
        """确保标签页已创建，如果是占位符则替换为真实页面"""
        tab_info = self._lazy_tab_factories.get(attr_name)
        if tab_info is None:
            return
        existing = getattr(self, attr_name, None)
        if existing is not None:
            return
        index = self._get_lazy_tab_index(attr_name)
        if index < 0:
            return
        widget = tab_info['factory']()
        setattr(self, attr_name, widget)
        if hasattr(widget, 'log_message'):
            widget.log_message.connect(self.log)
        self.tab_widget.removeTab(index)
        self.tab_widget.insertTab(index, widget, tab_info['label'])
        self.tab_widget.setTabEnabled(index, tab_info['enabled'])
    
    def _get_lazy_tab_index(self, attr_name: str) -> int:
        """查找占位符标签页索引"""
        tab_info = self._lazy_tab_factories.get(attr_name)
        if tab_info is None:
            return -1
        placeholder = tab_info.get('placeholder')
        if placeholder is None:
            return -1
        return self.tab_widget.indexOf(placeholder)

    def _add_tabs(self):
        """添加标签页"""
        self._lazy_tab_factories = {}
        self._lazy_tab_order = []

        # 1. 设备搜索
        self.scan_tab = DeviceScanTab()
        self.scan_tab.device_selected.connect(self._on_device_selected)
        idx = self.tab_widget.addTab(self.scan_tab, TabLabel.DEVICE_SCAN)
        scan_icon = icons.create_tab_icon(TabLabel.DEVICE_SCAN)
        if scan_icon is not None:
            self.tab_widget.setTabIcon(idx, scan_icon)

        # 2. 设备连接
        self.connection_tab = ConnectionTab()
        self.connection_tab.connection_changed.connect(self._on_connection_changed)
        self.connection_tab.log_message.connect(self.log)
        idx = self.tab_widget.addTab(self.connection_tab, TabLabel.CONNECTION)
        conn_icon = icons.create_tab_icon(TabLabel.CONNECTION)
        if conn_icon is not None:
            self.tab_widget.setTabIcon(idx, conn_icon)

        # 3. 视频预览 (V2)
        self._register_lazy_tab(
            'preview_tab',
            self._create_preview_tab,
            TabLabel.PREVIEW,
            enabled=False,
        )

        # 4. 批量下载 (V2)
        self._register_lazy_tab(
            'download_tab',
            self._create_download_tab,
            TabLabel.DOWNLOAD,
            enabled=False,
        )

        # 5. 下载管理 (V2)
        self._register_lazy_tab(
            'manager_tab',
            self._create_manager_tab,
            TabLabel.DOWNLOAD_MANAGER,
        )

        # 6. 终端调试
        self._register_lazy_tab(
            'terminal_tab',
            self._create_terminal_tab,
            TabLabel.TERMINAL,
        )

        # 7. 网络质量
        self._register_lazy_tab(
            'network_quality_tab',
            self._create_network_quality_tab,
            TabLabel.NETWORK_QUALITY,
        )

        # 8. 网络测速（原: 宽带测速）
        self._register_lazy_tab(
            'speedtest_tab',
            self._create_speedtest_tab,
            TabLabel.SPEEDTEST,
        )

        # 9. IP冲突检测
        self._register_lazy_tab(
            'ip_conflict_tab',
            self._create_ip_conflict_tab,
            TabLabel.IP_CONFLICT,
        )

        # 10. 流量分析
        self._register_lazy_tab(
            'traffic_analysis_tab',
            self._create_traffic_analysis_tab,
            TabLabel.TRAFFIC_ANALYSIS,
        )

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    def _on_tab_changed(self, index: int):
        """处理标签页切换，必要时创建延迟标签页的真实页面"""
        try:
            # 尝试通过标签文本来解析对应的延迟 tab，避免索引漂移问题
            if index < 0:
                return
            tab_text = self.tab_widget.tabText(index)
            # 匹配已注册的延迟标签的 label 字段
            attr_name = None
            for name, info in self._lazy_tab_factories.items():
                if info.get('label') == tab_text:
                    attr_name = name
                    break
            if attr_name is None:
                return
            self._ensure_tab(attr_name)
            # 如果标签支持 full_init，则在短延时后执行完整初始化（非阻塞）
            try:
                widget = getattr(self, attr_name, None)
                if widget is not None and hasattr(widget, 'full_init'):
                    QTimer.singleShot(50, lambda w=widget: w.full_init(self._current_device, getattr(self, '_device_info', {})))
            except Exception:
                logger.exception('_on_tab_changed 调用 full_init 失败')
        except Exception:
            # 保护性捕获，避免UI崩溃
            logger.exception("_on_tab_changed 处理失败")

    def _open_startup_settings(self):
        """打开启动行为设置对话框"""
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("启动行为")
            layout = QVBoxLayout(dlg)

            chk = QCheckBox("连接设备时自动创建并初始化 视频预览 和 批量下载 标签")
            chk.setChecked(self._config.get("ui.auto_init_tabs_on_connect", False))
            layout.addWidget(chk)

            delay_row = QHBoxLayout()
            delay_label = QLabel("延迟自动完成全初始化（秒）:")
            delay_spin = QSpinBox()
            delay_spin.setRange(0, 60)
            delay_spin.setValue(self._config.get("ui.auto_init_tabs_on_connect_delay", 2))
            delay_row.addWidget(delay_label)
            delay_row.addWidget(delay_spin)
            layout.addLayout(delay_row)

            concurrent_row = QHBoxLayout()
            concurrent_label = QLabel("最大并发初始化标签数:")
            concurrent_spin = QSpinBox()
            concurrent_spin.setRange(1, 4)
            concurrent_spin.setValue(self._config.get("ui.auto_init_tabs_on_connect_max_concurrent", 1))
            concurrent_row.addWidget(concurrent_label)
            concurrent_row.addWidget(concurrent_spin)
            layout.addLayout(concurrent_row)

            btn_row = QHBoxLayout()
            ok_btn = QPushButton("确定")
            cancel_btn = QPushButton("取消")
            btn_row.addStretch()
            btn_row.addWidget(ok_btn)
            btn_row.addWidget(cancel_btn)
            layout.addLayout(btn_row)

            def on_ok():
                self._config.set("ui.auto_init_tabs_on_connect", bool(chk.isChecked()))
                self._config.set("ui.auto_init_tabs_on_connect_delay", int(delay_spin.value()))
                self._config.set("ui.auto_init_tabs_on_connect_max_concurrent", int(concurrent_spin.value()))
                dlg.accept()

            ok_btn.clicked.connect(on_ok)
            cancel_btn.clicked.connect(dlg.reject)

            dlg.exec()
        except Exception:
            logger.exception("打开启动行为设置失败")

    # --- 延迟标签页工厂 -----------------------------------------------------------------
    def _create_preview_tab(self):
        widget = PreviewTabV2()
        try:
            if hasattr(widget, 'log_message'):
                widget.log_message.connect(self.log)
        except Exception:
            pass
        return widget

    def _create_download_tab(self):
        widget = DownloadTabV2(self._download_manager)
        try:
            if hasattr(widget, 'log_message'):
                widget.log_message.connect(self.log)
        except Exception:
            pass
        return widget

    def _schedule_auto_full_init(self):
        if not self._config.get("ui.auto_init_tabs_on_connect", False):
            return

        delay = int(self._config.get("ui.auto_init_tabs_on_connect_delay", 2))
        self._auto_full_init_queue = []
        self._auto_full_init_running = 0
        self._auto_full_init_scheduled = True

        self.log(f"将在 {delay} 秒后自动完成预览/下载标签的完整初始化")
        self.status_bar.showMessage("将在自动初始化完成前保持此状态", min(delay * 1000, 10000))
        QTimer.singleShot(delay * 1000, self._run_auto_full_init)

    def _run_auto_full_init(self):
        if not self._config.get("ui.auto_init_tabs_on_connect", False):
            return

        self._auto_full_init_scheduled = False
        self.log("开始自动完成预览/下载标签的完整初始化")
        self.status_bar.showMessage("开始自动完成标签完整初始化", 5000)
        self._auto_full_init_queue = []
        self._auto_full_init_running = 0

        for attr_name in ('preview_tab', 'download_tab'):
            widget = getattr(self, attr_name, None)
            if widget is not None and hasattr(widget, 'full_init'):
                self._auto_full_init_queue.append(widget)

        if not self._auto_full_init_queue:
            self.log("[提示] 无可自动初始化的标签页")
            return

        self._process_auto_full_init_queue()

    def _process_auto_full_init_queue(self):
        max_concurrent = max(1, int(self._config.get("ui.auto_init_tabs_on_connect_max_concurrent", 1)))
        while self._auto_full_init_running < max_concurrent and self._auto_full_init_queue:
            widget = self._auto_full_init_queue.pop(0)
            self._auto_full_init_running += 1
            QTimer.singleShot(0, lambda w=widget: self._execute_auto_full_init(w))

    def _execute_auto_full_init(self, widget):
        if widget is None:
            self._auto_full_init_running = max(0, self._auto_full_init_running - 1)
            return

        widget_name = widget.__class__.__name__
        try:
            self.log(f"自动初始化 {widget_name}...")
            widget.full_init(self._current_device, self._device_info or {})
            self.log(f"{widget_name} 自动完整初始化完成")
            self.status_bar.showMessage(f"{widget_name} 初始化完成", 3000)
        except Exception:
            logger.exception("自动 full_init 失败")
            self.log(f"[错误] {widget_name} 自动初始化失败")
        finally:
            self._auto_full_init_running = max(0, self._auto_full_init_running - 1)
            QTimer.singleShot(50, self._process_auto_full_init_queue)

    def _create_manager_tab(self):
        widget = DownloadManagerTabV2(self._download_manager)
        try:
            if hasattr(widget, 'log_message'):
                widget.log_message.connect(self.log)
        except Exception:
            pass
        return widget

    def _create_terminal_tab(self):
        widget = TerminalTab()
        try:
            if hasattr(widget, 'log_message'):
                widget.log_message.connect(self.log)
        except Exception:
            pass
        return widget

    def _create_network_quality_tab(self):
        widget = NetworkQualityTab()
        return widget

    def _create_speedtest_tab(self):
        widget = SpeedtestTab()
        return widget

    def _create_ip_conflict_tab(self):
        widget = IPConflictTab()
        return widget

    def _create_traffic_analysis_tab(self):
        widget = TrafficAnalysisTab()
        return widget

    def _create_log_panel(self) -> QWidget:
        """创建日志面板"""
        panel = QWidget()
        panel.setObjectName("logPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # 工具栏
        toolbar = QWidget()
        toolbar.setObjectName("logToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 4, 10, 4)
        toolbar_layout.setSpacing(6)
        
        title_label = QLabel("运行日志")
        title_label.setObjectName("logTitle")
        toolbar_layout.addWidget(title_label)
        toolbar_layout.addStretch()
        
        # 级别过滤
        self.log_level_combo = QComboBox()
        self.log_level_combo.setObjectName("logLevelCombo")
        self.log_level_combo.addItems(["全部", "信息", "警告", "错误"])
        self.log_level_combo.setFixedHeight(22)
        self.log_level_combo.setFixedWidth(70)
        self.log_level_combo.currentTextChanged.connect(self._render_log)
        toolbar_layout.addWidget(self.log_level_combo)
        
        # 搜索框
        self.log_search_input = QLineEdit()
        self.log_search_input.setObjectName("logSearchInput")
        self.log_search_input.setPlaceholderText("搜索...")
        self.log_search_input.setFixedHeight(22)
        self.log_search_input.setFixedWidth(120)
        self.log_search_input.textChanged.connect(self._render_log)
        toolbar_layout.addWidget(self.log_search_input)
        
        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("logToolbarBtn")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(48)
        clear_btn.clicked.connect(self._clear_log)
        icons.set_button_icon(clear_btn, icons.Icon.CLEAR, size=14)
        toolbar_layout.addWidget(clear_btn)

        # 导出按钮
        export_btn = QPushButton("导出")
        export_btn.setObjectName("logToolbarBtn")
        export_btn.setFixedHeight(22)
        export_btn.setFixedWidth(48)
        export_btn.clicked.connect(self._export_log)
        icons.set_button_icon(export_btn, icons.Icon.EXPORT, size=14)
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

            # 根据设置决定是否自动初始化延迟标签页
            auto_init = self._config.get("ui.auto_init_tabs_on_connect", False)

            # 启用占位符标签（始终可见），索引固定为2/3
            try:
                self.tab_widget.setTabEnabled(2, True)  # 视频预览
                self.tab_widget.setTabEnabled(3, True)  # 批量下载
            except Exception:
                pass

            # 如果允许自动初始化，则确保真实页面已创建（使用轻量初始化策略）
            if auto_init:
                self._ensure_tab('preview_tab')
                self._ensure_tab('download_tab')

                # 轻量初始化：优先调用 widget.light_init(device, device_info)，否则仅更新显示信息（set_device_info）
                preview_widget = getattr(self, 'preview_tab', None)
                download_widget = getattr(self, 'download_tab', None)

                self._current_device = self.connection_tab.get_device()

                if preview_widget is not None:
                    try:
                        if hasattr(preview_widget, 'light_init'):
                            # 使用短延时调度，避免阻塞 UI 初始化流程
                            QTimer.singleShot(50, lambda w=preview_widget: w.light_init(self._current_device, device_info))
                        else:
                            if hasattr(preview_widget, 'set_device_info'):
                                preview_widget.set_device_info(device_info)
                    except Exception:
                        logger.exception('preview_tab 轻量初始化失败')

                if download_widget is not None:
                    try:
                        if hasattr(download_widget, 'light_init'):
                            QTimer.singleShot(50, lambda w=download_widget: w.light_init(self._current_device, device_info))
                        else:
                            if hasattr(download_widget, 'set_device_info'):
                                download_widget.set_device_info(device_info)
                    except Exception:
                        logger.exception('download_tab 轻量初始化失败')

                # 根据配置调度自动完成完整初始化
                self._schedule_auto_full_init()

            else:
                # 非自动初始化：只更新占位或已存在的小信息，不做耗时操作
                preview_widget = getattr(self, 'preview_tab', None)
                download_widget = getattr(self, 'download_tab', None)
                self._current_device = self.connection_tab.get_device()
                if preview_widget is not None and hasattr(preview_widget, 'set_device_info'):
                    try:
                        preview_widget.set_device_info(device_info)
                    except Exception:
                        logger.exception('preview_tab set_device_info 失败')
                if download_widget is not None and hasattr(download_widget, 'set_device_info'):
                    try:
                        download_widget.set_device_info(device_info)
                    except Exception:
                        logger.exception('download_tab set_device_info 失败')

            # 更新全局状态
            self._app_state.set_device(self._current_device, device_info)

            # 如果预览页面已存在或刚创建，则切换到预览页
            if getattr(self, 'preview_tab', None) is not None:
                try:
                    self.tab_widget.setCurrentWidget(self.preview_tab)
                except Exception:
                    pass

            # 发射信号和事件总线
            self.device_connected.emit(self._current_device, device_info)
            self._event_bus.emit(EventType.DEVICE_CONNECTED, {
                "device": self._current_device,
                "device_info": device_info
            })
        else:
            self._device_info = {}
            self._current_device = None
            self.log("设备已断开")
            self.status_bar.showMessage("设备未连接")

            # 禁用相关标签页
            try:
                self.tab_widget.setTabEnabled(2, False)
                self.tab_widget.setTabEnabled(3, False)
            except Exception:
                pass

            # 清理已初始化页面的设备引用（若存在）
            preview_widget = getattr(self, 'preview_tab', None)
            download_widget = getattr(self, 'download_tab', None)

            if preview_widget is not None:
                if hasattr(preview_widget, 'set_device'):
                    preview_widget.set_device(None)
                if hasattr(preview_widget, 'set_device_info'):
                    preview_widget.set_device_info({})

            if download_widget is not None:
                if hasattr(download_widget, 'set_device'):
                    download_widget.set_device(None)
                if hasattr(download_widget, 'set_device_info'):
                    download_widget.set_device_info({})

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
        bg, fg = log_badge_colors(entry['level'])
        level_abbr = {'INFO': 'INFO', 'WARN': 'WARN', 'ERROR': 'ERR '}.get(entry['level'], entry['level'])
        return (
            f'<span style="color:{text_color("disabled")};">{entry["time"]}</span>&nbsp;'
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
        self.setStyleSheet(get_global_stylesheet(self._theme_manager.colors()))
    
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
        title.setObjectName("autoLoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel(f"IP地址: {ip}")
        info.setObjectName("autoLoginInfo")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        
        self._auto_login_countdown_label = QLabel("正在连接，请稍候...")
        self._auto_login_countdown_label.setObjectName("autoLoginCountdown")
        self._auto_login_countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._auto_login_countdown_label)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("autoLoginCancel")
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
        if getattr(self, 'preview_tab', None) is not None:
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
        
        # 清理新标签页资源（懒加载标签页可能尚未实例化，需判空）
        terminal_tab = getattr(self, 'terminal_tab', None)
        if terminal_tab is not None:
            terminal_tab.close()
        traffic_analysis_tab = getattr(self, 'traffic_analysis_tab', None)
        if traffic_analysis_tab is not None:
            traffic_analysis_tab.close()
        
        event.accept()
