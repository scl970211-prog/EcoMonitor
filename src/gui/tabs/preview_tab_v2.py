"""
视频预览标签页
- 支持1/2/3/4/8分屏
- 通道列表显示（支持拖拽和双击）
- 设备状态监控
- 布局记忆和恢复
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QListWidgetItem, QLabel, QPushButton,
    QComboBox, QGroupBox, QSplitter, QMessageBox, QLineEdit,
    QMenu, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from typing import Optional, Dict, List

from ...core import Device, DeviceStatus, ChannelStatus
from ..widgets.video_grid_v2 import VideoGridV2 as VideoGrid
from ..widgets.draggable_channel_list import DraggableChannelList
from ...utils.config import get_config
from ...utils.logger import get_logger
from ..theme import set_text_style


class PreviewTabV2(QWidget):
    """
    视频预览标签页
    - 分屏切换 (1/2/3/4/8)
    - 通道列表管理
    - 拖拽播放
    - 状态显示
    """
    
    # 信号
    log_message = pyqtSignal(str)  # 日志消息
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger = get_logger("hikvision_preview.preview_tab")
        
        self._device: Optional[Device] = None
        self._device_info: Dict = {}
        self._channels: List[Dict] = []
        self._channel_items: Dict[int, QListWidgetItem] = {}  # channel_id -> item
        
        # 当前布局类型
        self._current_layout = 4
        
        # 记住的布局和通道绑定
        self._saved_layout = 4
        self._saved_bindings: List[tuple] = []  # (window_index, channel_id, channel_name)
        self._last_device_status: Optional[str] = None
        self._is_fullscreen = False
        self._fullscreen_previous_layout = 4
        self._fullscreen_previous_bindings: List[tuple] = []
        
        # 正在拖拽的通道
        self._dragging_channel = None
        self._restoring_layout = False
        
        self._init_ui()
        self._load_saved_layout()
    
    def _init_ui(self):
        """初始化界面"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # ===== 左侧：通道列表 =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # 设备信息组
        device_group = QGroupBox("设备信息")
        device_layout = QVBoxLayout(device_group)
        
        self.device_status_label = QLabel("状态: 未连接")
        set_text_style(self.device_status_label, "secondary")
        device_layout.addWidget(self.device_status_label)

        self.device_info_label = QLabel("IP: --")
        set_text_style(self.device_info_label, "secondary", size="11px")
        device_layout.addWidget(self.device_info_label)
        
        left_layout.addWidget(device_group)
        
        # 通道列表组
        channel_group = QGroupBox("通道列表")
        channel_layout = QVBoxLayout(channel_group)
        
        # 通道列表工具栏
        channel_toolbar = QHBoxLayout()
        
        # 刷新按钮 - 固定宽度
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("刷新通道列表")
        self.refresh_btn.clicked.connect(self._load_channels)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setFixedWidth(60)
        channel_toolbar.addWidget(self.refresh_btn)
        
        channel_toolbar.addStretch()  # 添加弹性空间
        
        # 播放控制按钮 - 固定宽度
        self.play_btn = QPushButton("播放")
        self.play_btn.setToolTip("播放选中通道")
        self.play_btn.clicked.connect(self._on_play_clicked)
        self.play_btn.setEnabled(False)
        self.play_btn.setFixedWidth(50)
        channel_toolbar.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setToolTip("停止选中通道")
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedWidth(50)
        channel_toolbar.addWidget(self.stop_btn)
        
        channel_layout.addLayout(channel_toolbar)
        
        # 通道列表控件
        self.channel_list = DraggableChannelList()
        self.channel_list.setToolTip("拖拽通道到视频窗口，或双击自动播放")
        self.channel_list.itemDoubleClicked.connect(self._on_channel_double_clicked)
        self.channel_list.channel_dragged.connect(self._on_channel_dragged)
        self.channel_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.channel_list.customContextMenuRequested.connect(self._on_channel_context_menu)
        channel_layout.addWidget(self.channel_list)
        
        # 通道数量标签
        self.channel_count_label = QLabel("通道: 0")
        set_text_style(self.channel_count_label, "secondary", size="11px")
        channel_layout.addWidget(self.channel_count_label)
        
        left_layout.addWidget(channel_group)
        
        # 添加到分割器
        splitter.addWidget(left_panel)
        left_panel.setMinimumWidth(200)
        left_panel.setMaximumWidth(300)
        
        # ===== 右侧：视频区域 =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        # 布局控制工具栏
        toolbar_layout = QHBoxLayout()
        
        layout_label = QLabel("分屏布局:")
        toolbar_layout.addWidget(layout_label)
        
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["1分屏", "2分屏", "3分屏", "4分屏", "8分屏"])
        self.layout_combo.setCurrentIndex(3)  # 默认4分屏
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        toolbar_layout.addWidget(self.layout_combo)
        
        toolbar_layout.addStretch()
        
        # 全部停止按钮
        self.stop_all_btn = QPushButton("全部停止")
        self.stop_all_btn.setToolTip("停止所有预览")
        self.stop_all_btn.clicked.connect(self._on_stop_all)
        self.stop_all_btn.setEnabled(False)
        toolbar_layout.addWidget(self.stop_all_btn)
        
        # 保存布局按钮
        self.save_layout_btn = QPushButton("保存布局")
        self.save_layout_btn.setToolTip("保存当前布局和通道绑定")
        self.save_layout_btn.clicked.connect(self._save_current_layout)
        self.save_layout_btn.setEnabled(False)
        toolbar_layout.addWidget(self.save_layout_btn)
        
        right_layout.addLayout(toolbar_layout)
        
        # 视频网格
        self.video_grid = VideoGrid()
        self.video_grid.video_clicked.connect(self._on_video_clicked)
        self.video_grid.video_double_clicked.connect(self._on_video_double_clicked)
        
        # 为每个视频窗格连接拖拽接收信号
        self._connect_video_widget_signals()
        
        right_layout.addWidget(self.video_grid, 1)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        set_text_style(self.status_label, "secondary", size="11px")
        right_layout.addWidget(self.status_label)
        
        # 添加到分割器
        splitter.addWidget(right_panel)
        
        # 设置分割器比例
        splitter.setSizes([250, 950])

    def _connect_video_widget_signals(self):
        """连接当前视频窗格的信号。"""
        for widget in self.video_grid.get_all_widgets():
            try:
                widget.channel_dropped.disconnect(self._on_channel_dropped_to_widget)
            except Exception:
                pass
            widget.channel_dropped.connect(self._on_channel_dropped_to_widget)
    
    def set_device(self, device: Optional[Device]):
        """
        设置设备
        
        Args:
            device: Device实例或None
        """
        # 先停止所有预览
        self._stop_all_previews()
        
        # 断开旧设备的信号
        if self._device:
            try:
                self._device.device_status_changed.disconnect(self._on_device_status_changed)
                self._device.channel_status_changed.disconnect(self._on_channel_status_changed)
            except:
                pass
        
        self._device = device
        
        if device:
            # 连接信号
            device.device_status_changed.connect(self._on_device_status_changed)
            device.channel_status_changed.connect(self._on_channel_status_changed)
            
            # 更新设备状态显示
            status, error_msg, _ = device.get_device_status()
            self._last_device_status = status
            self._update_device_status_display(status, error_msg)
            
            # 启用控件
            self.refresh_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.stop_all_btn.setEnabled(True)
            self.save_layout_btn.setEnabled(True)
            
            # 加载通道列表
            self._load_channels()
            
            # 每次连接成功后，根据配置决定自动播放或恢复布局
            config = get_config()
            if config.get('preview.auto_play_all', False):
                self._logger.info("connection_auto_play_all")
                QTimer.singleShot(1000, self._auto_play_all_channels)
            elif config.get('preview.restore_on_connect', True):
                self._logger.info("connection_restoring_layout")
                self._restore_saved_layout()
        else:
            # 清除设备状态显示
            self.device_status_label.setText("状态: 未连接")
            set_text_style(self.device_status_label, "secondary")
            self.device_info_label.setText("IP: --")
            
            # 禁用控件
            self.refresh_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.stop_all_btn.setEnabled(False)
            self.save_layout_btn.setEnabled(False)
            
            # 清空通道列表
            self.channel_list.clear()
            self._channels = []
            self._channel_items = {}
            self.channel_count_label.setText("通道: 0")
            self._is_fullscreen = False
            self._fullscreen_previous_bindings = []
            
            # 清除视频窗格
            self.video_grid.clear_all_channels()
            
            self.status_label.setText("设备未连接")
    
    def set_device_info(self, device_info: Dict):
        """设置设备信息（仅用于显示）"""
        self._device_info = device_info
        if device_info:
            ip = device_info.get('ip', '--')
            self.device_info_label.setText(f"IP: {ip}")
        else:
            self.device_info_label.setText("IP: --")

    def light_init(self, device: Optional[Device], device_info: Dict):
        """轻量初始化：仅更新显示信息，不建立流或检索通道（非阻塞）"""
        try:
            # 保存引用，但不连接设备信号或加载通道
            self._device = device
            self._device_info = device_info or {}
            if self._device_info:
                ip = self._device_info.get('ip', '--')
                self.device_info_label.setText(f"IP: {ip}")
            else:
                self.device_info_label.setText("IP: --")
            # 仅启用刷新按钮，让用户可以主动触发加载
            try:
                self.refresh_btn.setEnabled(bool(device))
            except Exception:
                pass
        except Exception:
            self._logger.exception('light_init 失败')

    def full_init(self, device: Optional[Device], device_info: Dict):
        """完整初始化：执行原来的 set_device 逻辑（建立信号/加载通道等）"""
        try:
            # 当 full_init 被调用时，执行现有的 set_device 行为
            self.set_device(device)
            # 也保证设备信息被设置
            self.set_device_info(device_info or {})
        except Exception:
            self._logger.exception('full_init 失败')
    
    def _load_channels(self):
        """加载通道列表"""
        if not self._device or not self._device.is_connected:
            self.log_message.emit("[警告] 设备未连接，无法加载通道")
            return
        
        self.status_label.setText("正在加载通道列表...")
        self.channel_list.clear()
        self._channel_items = {}
        
        try:
            # 仅显示有设备接入的通道，空通道不展示
            self._channels = self._device.get_channel_list(filter_empty=True)
            
            # 统计通道来源
            isapi_count = sum(1 for c in self._channels if c.get('status_source') == 'isapi')
            fallback_count = sum(1 for c in self._channels if c.get('status_source') == 'sdk-fallback')
            sdk_count = sum(1 for c in self._channels if c.get('status_source') == 'sdk-count')
            
            self._logger.info(
                "channel_list_loaded total=%s isapi=%s fallback=%s sdk=%s",
                len(self._channels), isapi_count, fallback_count, sdk_count,
            )
            
            # 向用户显示通道加载信息
            if isapi_count > 0:
                self.log_message.emit(f"[信息] 通过 ISAPI 获取到 {isapi_count} 个通道")
            elif fallback_count > 0:
                self.log_message.emit(f"[信息] 通过 SDK 获取到 {fallback_count} 个通道 (ISAPI 不可用)")
            elif sdk_count > 0:
                self.log_message.emit(f"[警告] 通过 SDK 计数获取通道 (通道名称和状态可能不准确)")
                self.log_message.emit("[提示] 如需准确通道列表，请检查：1. HTTP端口(80)是否开放 2. 设备ISAPI是否启用")
            
            # 添加到列表控件
            for channel in self._channels:
                channel_id = channel['id']
                display_id = channel.get('display_id', f'CH{channel_id}')
                name = channel.get('name', f'通道{channel_id}')
                enabled = channel.get('enabled', True)
                configured = channel.get('configured', enabled)
                has_camera = channel.get('has_camera')
                online = channel.get('online')
                status_source = channel.get('status_source', 'unknown')
                
                # 创建列表项
                if name and name != f'通道{channel_id}':
                    item_text = f"{display_id} - {name}"
                else:
                    item_text = f"{display_id}"
                
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, channel_id)
                item.setData(Qt.ItemDataRole.UserRole + 1, name)
                item.setData(Qt.ItemDataRole.UserRole + 2, display_id)
                
                # 根据状态设置样式和图标
                if configured and has_camera is True and online is True:
                    item.setToolTip(f"通道 {display_id} - 在线，可拖拽或双击播放")
                    item.setForeground(Qt.GlobalColor.darkGreen)
                    item.setText(f"{item_text} [在线]")
                elif configured and has_camera is True and online is False:
                    item.setForeground(Qt.GlobalColor.gray)
                    item.setToolTip(f"通道 {display_id} - 离线（设备暂时不可达）")
                    item.setText(f"{item_text} [离线]")
                elif not configured or not enabled:
                    item.setForeground(Qt.GlobalColor.gray)
                    item.setToolTip("通道未启用")
                    item.setText(f"{item_text} [未启用]")
                elif configured and has_camera is False:
                    item.setForeground(Qt.GlobalColor.gray)
                    item.setToolTip(f"通道 {display_id} - 未接入摄像头")
                    item.setText(f"{item_text} [未接入]")
                else:
                    item.setForeground(Qt.GlobalColor.black)
                    if status_source in ('sdk-count', 'sdk-fallback'):
                        item.setToolTip(f"通道 {display_id} - SDK 模式，接入状态未校验")
                        item.setText(f"{item_text} [状态未知]")
                    else:
                        item.setToolTip(f"通道 {display_id}")
                
                self.channel_list.addItem(item)
                self._channel_items[channel_id] = item
            
            # 更新通道数量统计
            total = len(self._channels)
            online_count = sum(1 for c in self._channels if c.get('online') is True)
            offline_count = sum(1 for c in self._channels if c.get('online') is False)
            unknown_count = sum(1 for c in self._channels if c.get('online') is None)
            
            self.channel_count_label.setText(f"通道: {online_count}在线/{offline_count}离线/{unknown_count}未知/{total}总计")
            
            # 来源统计
            isapi_count = sum(1 for c in self._channels if c.get('status_source') == 'isapi')
            sdk_count = sum(1 for c in self._channels if c.get('status_source') != 'isapi')
            
            self.status_label.setText(f"已加载 {total} 个通道 (ISAPI:{isapi_count}, SDK:{sdk_count})")
            
            # 显示详细的通道加载信息
            if isapi_count > 0:
                self.log_message.emit(f"[信息] ISAPI 模式：{online_count}在线, {offline_count}离线, 共{total}个通道")
            elif sdk_count > 0:
                self.log_message.emit(f"[信息] SDK 兜底模式：{total}个通道（接入状态未校验）")
                self.log_message.emit("[提示] 如需准确通道状态，请检查 HTTP 端口或 ISAPI 是否启用")
            
        except Exception as e:
            error_msg = f"加载通道列表失败: {str(e)}"
            self._logger.error("channel_list_load_failed error=%s", e)
            self.status_label.setText(error_msg)
            self.log_message.emit(f"[错误] {error_msg}")
    
    def _on_layout_changed(self, index: int):
        """布局切换"""
        if self._restoring_layout:
            return

        layout_map = {0: 1, 1: 2, 2: 3, 3: 4, 4: 8}
        layout_type = layout_map.get(index, 4)
        
        if self._current_layout == layout_type:
            return
        
        # 保存当前绑定
        self._saved_bindings = self.video_grid.get_bound_channels()
        
        # 停止所有预览（因为窗口句柄会改变）
        self._stop_all_previews()
        
        # 切换布局
        self._current_layout = layout_type
        self.video_grid.set_layout(layout_type)
        
        # 重新连接新创建的视频窗格信号
        self._connect_video_widget_signals()
        
        self.status_label.setText(f"已切换为 {layout_type} 分屏")
        self.log_message.emit(f"[信息] 分屏布局切换为 {layout_type}")
        
        # 尝试恢复通道绑定（新布局可能窗口数量不同）
        self._restore_bindings_to_available_windows()
    
    def _restore_bindings_to_available_windows(self):
        """将保存的绑定恢复到可用的窗口"""
        if not self._saved_bindings:
            return
        
        widget_count = self.video_grid.widget_count
        restored = 0
        failed = 0
        
        self._logger.info("restoring_bindings count=%s", len(self._saved_bindings))
        
        for window_index, channel_id, channel_name in self._saved_bindings:
            if window_index >= widget_count:
                self._logger.warning("window_index_out_of_range window=%s count=%s", window_index, widget_count)
                continue
            
            # 检查通道是否在列表中
            channel_exists = any(c['id'] == channel_id for c in self._channels)
            if not channel_exists:
                self._logger.warning("channel_not_in_list channel=%s", channel_id)
                self.log_message.emit(f"[警告] 通道 {channel_id} 不在当前通道列表中，可能已断开连接")
                failed += 1
                continue
            
            # 获取最新的通道名称
            current_name = channel_name
            for ch in self._channels:
                if ch['id'] == channel_id:
                    current_name = ch.get('name', channel_name)
                    break
            
            # 开始预览
            try:
                self._logger.info("restoring_preview window=%s channel=%s name=%s", 
                                window_index, channel_id, current_name)
                self._start_preview(window_index, channel_id, current_name, confirm_replace=False)
                restored += 1
            except Exception as e:
                self._logger.error("restore_preview_failed window=%s channel=%s error=%s", 
                                 window_index, channel_id, e)
                self.log_message.emit(f"[警告] 恢复通道 {current_name}({channel_id}) 预览失败: {e}")
                failed += 1
        
        if restored > 0:
            msg = f"已恢复 {restored} 个通道的预览"
            if failed > 0:
                msg += f"，{failed} 个通道恢复失败"
            self.status_label.setText(msg)
            self.log_message.emit(f"[信息] {msg}")
        elif failed > 0:
            self.status_label.setText(f"{failed} 个通道恢复失败")
            self.log_message.emit("[提示] 上次保存的通道当前不可用，请重新选择通道")
    
    def _on_channel_double_clicked(self, item: QListWidgetItem):
        """通道列表项双击 - 自动分配到第一个空闲窗口"""
        channel_id = item.data(Qt.ItemDataRole.UserRole)
        channel_name = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if channel_id is not None:
            try:
                self._start_preview_for_channel(channel_id, channel_name)
            except Exception as e:
                error_msg = str(e)
                self.log_message.emit(f"[错误] 播放通道失败: {error_msg}")
                # 显示友好的错误提示，但不崩溃
                QMessageBox.warning(self, "播放失败", f"无法播放通道 {channel_name or channel_id}:\n{error_msg}")
    
    def _on_channel_dragged(self, channel_id: int, channel_name: str):
        """处理通道拖拽事件"""
        self._dragging_channel = (channel_id, channel_name)
    
    def _on_channel_dropped_to_widget(self, window_index: int, channel_id: int, channel_name: str):
        """处理通道被拖拽到视频窗口"""
        try:
            self._start_preview(window_index, channel_id, channel_name)
        except Exception as e:
            self.log_message.emit(f"[错误] 播放通道 {channel_id} 失败: {e}")
    
    def _start_preview_for_channel(self, channel_id: int, channel_name: str = None):
        """
        为通道启动预览，自动选择窗口
        
        Args:
            channel_id: 通道ID
            channel_name: 通道名称
        """
        try:
            if channel_name is None:
                # 从列表项获取名称
                item = self._channel_items.get(channel_id)
                if item:
                    channel_name = item.data(Qt.ItemDataRole.UserRole + 1)
            
            # 查找空闲窗口
            window_index = self.video_grid.get_available_window()
            
            if window_index < 0:
                self._show_assign_dialog(channel_id, channel_name)
                return
            
            self._start_preview(window_index, channel_id, channel_name)
        except Exception as e:
            error_msg = str(e)
            self.log_message.emit(f"[错误] 启动预览失败: {error_msg}")
            QMessageBox.warning(self, "播放失败", f"无法播放通道 {channel_name or channel_id}:\n{error_msg}")
    
    def _prepare_window_for_preview(self, window_index: int, channel_id: int, confirm_replace: bool = True) -> bool:
        """在播放前处理窗口占用与旧预览清理。"""
        widget = self.video_grid.get_widget(window_index)
        if not widget:
            raise RuntimeError(f"窗口 {window_index} 不存在")

        existing_channel_id = widget.channel_id
        if existing_channel_id is None:
            return True

        if existing_channel_id == channel_id:
            return True

        if confirm_replace:
            reply = QMessageBox.question(
                self,
                "替换预览",
                f"窗口 {window_index + 1} 正在播放 [{widget.channel_name or existing_channel_id}]，是否替换？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        if self._device:
            self._device.stop_preview(existing_channel_id)
        self.video_grid.unbind_channel(existing_channel_id)
        return True

    def _restore_current_previews_after_reconnect(self):
        """设备重新上线后，恢复当前界面已绑定的预览。"""
        current_bindings = self.video_grid.get_bound_channels()
        if not current_bindings:
            return

        restored = 0
        for window_index, channel_id, channel_name in current_bindings:
            try:
                self._start_preview(window_index, channel_id, channel_name, confirm_replace=False)
                restored += 1
            except Exception as e:
                self.log_message.emit(f"[警告] 重连后恢复通道 {channel_id} 失败: {e}")

        if restored:
            self.status_label.setText(f"重连成功，已恢复 {restored} 个通道")

    def _start_preview(self, window_index: int, channel_id: int, channel_name: str = None, confirm_replace: bool = True):
        """
        在指定窗口开始预览
        
        Args:
            window_index: 视频窗口索引
            channel_id: 通道ID
            channel_name: 通道名称
        """
        if not self._device:
            raise RuntimeError("设备未连接")
        
        # 查找通道信息
        if channel_name is None:
            for ch in self._channels:
                if ch['id'] == channel_id:
                    channel_name = ch.get('name', f'通道{channel_id}')
                    break
            else:
                channel_name = f'通道{channel_id}'
        
        # 获取窗口句柄
        widget = self.video_grid.get_widget(window_index)
        if not widget:
            raise RuntimeError(f"窗口 {window_index} 不存在")

        if not self._prepare_window_for_preview(window_index, channel_id, confirm_replace=confirm_replace):
            return

        widget = self.video_grid.get_widget(window_index)
        
        hwnd = widget.get_win_id()
        if hwnd == 0:
            raise RuntimeError("无法获取窗口句柄")
        
        try:
            # 绑定通道到窗口
            self.video_grid.bind_channel(window_index, channel_id, channel_name)
            widget = self.video_grid.get_widget(window_index)
            
            # 启动预览（不显示"连接中..."，让SDK直接渲染）
            # 只在启动失败时显示错误
            preview_handle = self._device.start_preview(channel_id, hwnd)
            
            # 更新窗口显示
            widget.set_preview_handle(preview_handle)
            
            # 确保隐藏"连接中..."标签
            widget.set_loading(False)
            
            display_id = ""
            for ch in self._channels:
                if ch['id'] == channel_id:
                    display_id = ch.get('display_id', '')
                    break
            
            self.status_label.setText(f"窗口 {window_index + 1} 正在预览: {display_id} - {channel_name}")
            self._logger.info(
                "preview_bind_success window=%s channel=%s display_id=%s name=%s handle=%s",
                window_index,
                channel_id,
                display_id,
                channel_name,
                preview_handle,
            )
            self.log_message.emit(f"[信息] 开始预览: {display_id} - {channel_name}")
            
        except Exception as e:
            self._logger.error(
                "preview_bind_failed window=%s channel=%s name=%s error=%s",
                window_index,
                channel_id,
                channel_name,
                e,
            )
            widget.set_loading(False)
            widget.clear_channel()
            raise
    
    def _stop_preview(self, window_index: int):
        """
        停止指定窗口的预览
        
        Args:
            window_index: 视频窗口索引
        """
        if not self._device:
            return
        
        widget = self.video_grid.get_widget(window_index)
        if not widget or widget.channel_id is None:
            return
        
        channel_id = widget.channel_id
        
        try:
            # 停止设备预览
            self._device.stop_preview(channel_id)
            
            # 清除窗口绑定
            self.video_grid.unbind_channel(channel_id)
            
            self.status_label.setText(f"窗口 {window_index + 1} 已停止")
            
        except Exception as e:
            self.log_message.emit(f"[警告] 停止预览失败: {e}")
    
    def _on_stop_clicked(self):
        """停止按钮点击"""
        # 获取当前选中的通道
        current_item = self.channel_list.currentItem()
        if current_item:
            channel_id = current_item.data(Qt.ItemDataRole.UserRole)
            # 查找该通道在哪个窗口
            widget = self.video_grid.get_widget_by_channel(channel_id)
            if widget:
                self._stop_preview(widget.index)
            else:
                QMessageBox.information(self, "提示", "该通道当前未在预览")
        else:
            QMessageBox.information(self, "提示", "请先选择一个通道")
    
    def _on_stop_all(self):
        """停止所有预览"""
        self._stop_all_previews()
        self.status_label.setText("已停止所有预览")
    
    def _stop_all_previews(self):
        """停止所有窗口的预览"""
        if not self._device:
            return
        
        # 停止设备所有预览
        self._device.stop_all_previews()
        
        # 清除所有窗口绑定
        self.video_grid.clear_all_channels()
    
    def _on_play_clicked(self):
        """播放按钮点击"""
        current_item = self.channel_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择一个通道")
            return
        
        channel_id = current_item.data(Qt.ItemDataRole.UserRole)
        channel_name = current_item.data(Qt.ItemDataRole.UserRole + 1)
        
        # 显示窗口选择对话框
        self._show_assign_dialog(channel_id, channel_name)
    
    def _show_assign_dialog(self, channel_id: int, channel_name: str):
        """显示分配到指定窗口的对话框"""
        # 获取可用窗口
        widget_count = self.video_grid.widget_count
        choices = []
        for i in range(widget_count):
            widget = self.video_grid.get_widget(i)
            if widget and widget.channel_id is not None:
                # 显示当前占用的通道
                choices.append(f"窗口 {i+1} (已占用: {widget._channel_name or widget.channel_id})")
            else:
                choices.append(f"窗口 {i+1} (空闲)")
        
        # 显示选择对话框
        text, ok = QInputDialog.getItem(
            self, "选择窗口", 
            f"将通道 [{channel_name}] 分配到:",
            choices, 0, False
        )
        
        if ok and text:
            # 解析选择的窗口索引
            window_index = int(text.split("窗口 ")[1].split(" (")[0]) - 1
            if 0 <= window_index < widget_count:
                self._start_preview(window_index, channel_id, channel_name)
    
    def _on_channel_context_menu(self, position):
        """通道列表右键菜单"""
        item = self.channel_list.itemAt(position)
        if not item:
            return
        
        channel_id = item.data(Qt.ItemDataRole.UserRole)
        channel_name = item.data(Qt.ItemDataRole.UserRole + 1)
        
        menu = QMenu(self)
        
        # 播放菜单项
        play_action = menu.addAction("播放")
        play_action.triggered.connect(lambda: self._start_preview_for_channel(channel_id, channel_name))
        
        # 停止菜单项
        stop_action = menu.addAction("停止")
        stop_action.triggered.connect(lambda: self._stop_preview_by_channel(channel_id))
        
        # 选择窗口播放子菜单
        menu.addSeparator()
        assign_menu = menu.addMenu("分配到窗口")
        
        for i in range(self.video_grid.widget_count):
            widget = self.video_grid.get_widget(i)
            if widget and widget.channel_id is not None:
                action_text = f"窗口 {i+1} (已占用)"
            else:
                action_text = f"窗口 {i+1} (空闲)"
            
            action = assign_menu.addAction(action_text)
            action.triggered.connect(lambda checked, idx=i: self._start_preview(idx, channel_id, channel_name))
        
        menu.exec(self.channel_list.mapToGlobal(position))
    
    def _stop_preview_by_channel(self, channel_id: int):
        """通过通道ID停止预览"""
        widget = self.video_grid.get_widget_by_channel(channel_id)
        if widget:
            self._stop_preview(widget.index)
        else:
            QMessageBox.information(self, "提示", "该通道当前未在预览")
    
    def _on_video_clicked(self, index: int):
        """视频窗口被点击"""
        widget = self.video_grid.get_widget(index)
        if widget:
            if widget.channel_id is not None:
                self.status_label.setText(f"选中窗口 {index + 1}: {widget.channel_name}")
            else:
                self.status_label.setText(f"选中窗口 {index + 1}")
    
    def _on_video_double_clicked(self, index: int):
        """视频窗口被双击 - 切换单窗全屏模式"""
        widget = self.video_grid.get_widget(index)
        if not widget or widget.channel_id is None:
            return

        if self._is_fullscreen:
            self.video_grid.clear_all_channels()
            self._stop_all_previews()
            self._current_layout = self._fullscreen_previous_layout
            self.video_grid.set_layout(self._fullscreen_previous_layout)
            self._connect_video_widget_signals()
            self._saved_bindings = list(self._fullscreen_previous_bindings)
            self._restore_bindings_to_available_windows()
            self._fullscreen_previous_bindings = []
            self._is_fullscreen = False
            self.status_label.setText("已退出单窗查看")
            return

        self._fullscreen_previous_layout = self._current_layout
        self._fullscreen_previous_bindings = self.video_grid.get_bound_channels()
        target_binding = (0, widget.channel_id, widget.channel_name)
        self._stop_all_previews()
        self._current_layout = 1
        self.video_grid.set_layout(1)
        self._connect_video_widget_signals()
        self._saved_bindings = [target_binding]
        self._is_fullscreen = True
        self._start_preview(0, widget.channel_id, widget.channel_name, confirm_replace=False)
        self.status_label.setText(f"单窗查看: {widget.channel_name}")
    
    def _on_device_status_changed(self, status: str, error_msg: str):
        """设备状态变化"""
        previous_status = self._last_device_status
        self._last_device_status = status
        self._update_device_status_display(status, error_msg)

        if status == DeviceStatus.ONLINE and previous_status in (
            DeviceStatus.RECONNECTING,
            DeviceStatus.OFFLINE,
            DeviceStatus.ERROR,
        ):
            self._logger.info("device_recovered previous_status=%s", previous_status)
            QTimer.singleShot(300, self._restore_current_previews_after_reconnect)
    
    def _update_device_status_display(self, status: str, error_msg: str = ""):
        """更新设备状态显示"""
        status_text_map = {
            DeviceStatus.OFFLINE: ("离线", "offline"),
            DeviceStatus.CONNECTING: ("连接中...", "warning"),
            DeviceStatus.ONLINE: ("在线", "success"),
            DeviceStatus.ERROR: ("错误", "error"),
            DeviceStatus.RECONNECTING: ("重连中...", "warning"),
        }

        text, role = status_text_map.get(status, ("未知", "secondary"))

        if error_msg and status in (DeviceStatus.ERROR, DeviceStatus.OFFLINE):
            display_text = f"状态: {text} - {error_msg}"
        else:
            display_text = f"状态: {text}"

        self.device_status_label.setText(display_text)
        set_status_style(self.device_status_label, role, bold=True)
    
    def _on_channel_status_changed(self, channel_id: int, status: str):
        """通道状态变化"""
        item = self._channel_items.get(channel_id)
        if item:
            # 更新列表项显示
            if status == ChannelStatus.PREVIEWING:
                item.setBackground(Qt.GlobalColor.blue)
                item.setForeground(Qt.GlobalColor.white)
            elif status == ChannelStatus.ERROR:
                item.setBackground(Qt.GlobalColor.red)
                item.setForeground(Qt.GlobalColor.white)
            elif status == ChannelStatus.OFFLINE:
                item.setBackground(Qt.GlobalColor.transparent)
                item.setForeground(Qt.GlobalColor.gray)
            else:
                item.setBackground(Qt.GlobalColor.transparent)
                item.setForeground(Qt.GlobalColor.black)

        widget = self.video_grid.get_widget_by_channel(channel_id)
        if widget:
            detail = item.toolTip() if item else ""
            if status == ChannelStatus.PREVIEWING:
                widget.set_status("previewing", detail)
                widget.set_loading(False)  # 确保隐藏"连接中..."
            elif status == ChannelStatus.ERROR:
                widget.set_status("error", detail)
                widget.set_loading(False)
            elif status == ChannelStatus.RECONNECTING:
                widget.set_status("reconnecting", detail)
                # 只有在没有预览句柄时才显示"连接中..."
                if widget._preview_handle < 0:
                    widget.set_loading(True)
            elif status == ChannelStatus.OFFLINE:
                widget.set_status("offline", detail)
                widget.set_loading(False)
            else:
                widget.set_status("online", detail)
                widget.set_loading(False)
    
    def _save_current_layout(self):
        """保存当前布局和通道绑定"""
        config = get_config()
        
        # 保存布局类型
        config.set('preview.default_layout', self._current_layout)
        
        # 保存通道绑定
        bindings = self.video_grid.get_bound_channels()
        # 转换为可序列化的格式
        saved_bindings = [
            {'window': w, 'channel': c, 'name': n}
            for w, c, n in bindings
        ]
        config.set('preview.saved_bindings', saved_bindings)
        
        self._saved_layout = self._current_layout
        self._saved_bindings = bindings
        
        self.status_label.setText("布局已保存")
        self.log_message.emit(f"[信息] 布局已保存: {self._current_layout}分屏, {len(bindings)} 个通道")
    
    def _load_saved_layout(self):
        """加载保存的布局设置"""
        config = get_config()
        
        self._saved_layout = config.get('preview.default_layout', 4)
        saved_bindings = config.get('preview.saved_bindings', [])
        
        # 转换绑定格式
        self._saved_bindings = [
            (b['window'], b['channel'], b.get('name', f"通道{b['channel']}"))
            for b in saved_bindings
            if 'window' in b and 'channel' in b
        ]
        
        # 设置布局下拉框
        layout_map = {1: 0, 2: 1, 3: 2, 4: 3, 8: 4}
        index = layout_map.get(self._saved_layout, 3)
        self.layout_combo.setCurrentIndex(index)
    
    def _auto_play_all_channels(self):
        """
        自动将所有通道按顺序加入播放
        根据通道数量自动选择合适的分屏布局
        """
        if not self._device or not self._channels:
            return
        
        channel_count = len(self._channels)
        if channel_count == 0:
            return
        
        self._logger.info("auto_play_all_channels count=%s", channel_count)
        self.log_message.emit(f"[信息] 自动播放所有 {channel_count} 个通道")
        
        # 根据通道数量选择合适的布局
        if channel_count == 1:
            target_layout = 1
        elif channel_count <= 2:
            target_layout = 2
        elif channel_count <= 4:
            target_layout = 4
        else:
            target_layout = 8
        
        # 切换布局
        if self._current_layout != target_layout:
            layout_map = {1: 0, 2: 1, 3: 2, 4: 3, 8: 4}
            index = layout_map.get(target_layout, 3)
            self.layout_combo.setCurrentIndex(index)
            self._logger.info("auto_switch_layout layout=%s", target_layout)
        
        # 按顺序将通道分配到窗口
        played = 0
        failed = 0
        
        for i, channel in enumerate(self._channels):
            if i >= self.video_grid.widget_count:
                # 窗口已满，停止分配
                self._logger.info("windows_full stopped_at=%s", i)
                break
            
            channel_id = channel['id']
            channel_name = channel.get('name', f"通道{channel_id}")
            
            # 跳过离线通道（但记录日志）
            if channel.get('has_device') is False:
                self._logger.debug("skip_offline_channel channel=%s", channel_id)
                continue
            
            try:
                self._logger.info("auto_play_channel window=%s channel=%s name=%s", 
                                i, channel_id, channel_name)
                self._start_preview(i, channel_id, channel_name, confirm_replace=False)
                played += 1
            except Exception as e:
                self._logger.error("auto_play_failed channel=%s error=%s", channel_id, e)
                failed += 1
        
        # 保存当前布局（下次启动时恢复）
        self._save_current_layout()
        
        # 显示结果
        msg = f"自动播放完成: {played} 个通道成功"
        if failed > 0:
            msg += f", {failed} 个失败"
        if played < len(self._channels):
            msg += f", {len(self._channels) - played} 个未分配（窗口不足）"
        
        self.status_label.setText(msg)
        self.log_message.emit(f"[信息] {msg}")
    
    def _restore_saved_layout(self):
        """恢复保存的布局和通道绑定"""
        if not self._saved_bindings:
            self._logger.info("no_saved_bindings_to_restore")
            return
        
        self._logger.info(
            "restoring_saved_layout layout=%s bindings=%s",
            self._saved_layout, len(self._saved_bindings)
        )
        
        # 恢复布局
        layout_map = {1: 0, 2: 1, 3: 2, 4: 3, 8: 4}
        index = layout_map.get(self._saved_layout, 3)
        self._restoring_layout = True
        self.layout_combo.setCurrentIndex(index)
        self._current_layout = self._saved_layout
        self.video_grid.set_layout(self._saved_layout)
        self._connect_video_widget_signals()
        self._restoring_layout = False
        
        # 显示恢复提示
        binding_info = ", ".join([f"窗口{w+1}-通道{c}" for w, c, n in self._saved_bindings[:3]])
        if len(self._saved_bindings) > 3:
            binding_info += f" 等{len(self._saved_bindings)}个通道"
        self.log_message.emit(f"[信息] 正在恢复上次布局: {self._saved_layout}分屏 - {binding_info}")
        
        # 延迟恢复通道预览，确保通道列表已加载
        QTimer.singleShot(800, self._restore_bindings_to_available_windows)
    
    def cleanup(self):
        """清理资源"""
        self._stop_all_previews()
        
        # 断开信号
        if self._device:
            try:
                self._device.device_status_changed.disconnect(self._on_device_status_changed)
                self._device.channel_status_changed.disconnect(self._on_channel_status_changed)
            except:
                pass
        
        # 清理视频窗口
        for widget in self.video_grid.get_all_widgets():
            widget.cleanup()
