"""
视频窗格组件。
使用 SDK 原生渲染到窗口句柄。
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class VideoWidget(QWidget):
    """单个视频显示窗格。"""

    clicked = pyqtSignal(int)
    double_clicked = pyqtSignal(int)
    channel_dropped = pyqtSignal(int, int, str)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._channel_id = None
        self._channel_name = ""
        self._preview_handle = -1
        self._is_loading = False
        self._loading_timer: QTimer | None = None
        self._init_ui()
        self._init_loading_timer()
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def _init_ui(self):
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 26))
        self.setPalette(palette)

        self.setStyleSheet(
            """
            VideoWidget {
                background-color: #1a1a1a;
                border: 1px solid #333;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)

        self.video_container = QWidget()
        self.video_container.setStyleSheet(
            """
            background-color: #0d0d0d;
            border: 1px solid #333;
            """
        )
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_container.setMinimumSize(120, 90)
        self.video_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_container.setAutoFillBackground(True)
        video_palette = self.video_container.palette()
        video_palette.setColor(QPalette.ColorRole.Window, QColor(13, 13, 13))
        self.video_container.setPalette(video_palette)
        main_layout.addWidget(self.video_container, 1)

        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(4, 0, 4, 0)
        info_layout.setSpacing(8)

        self.index_label = QLabel(f"{self._index + 1}")
        self.index_label.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        info_layout.addWidget(self.index_label)

        self.name_label = QLabel("未分配")
        self.name_label.setStyleSheet("color: #999; font-size: 11px;")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(self.name_label, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 10px;")
        info_layout.addWidget(self.status_label)

        main_layout.addLayout(info_layout)

        self.loading_label = QLabel("连接中...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet(
            """
            color: #4CAF50;
            font-size: 12px;
            background-color: rgba(0, 0, 0, 180);
            padding: 8px 16px;
            border-radius: 4px;
            """
        )
        self.loading_label.hide()
        self.loading_label.setParent(self.video_container)
        self.loading_label.raise_()

    def _init_loading_timer(self):
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._update_loading_text)
        self._loading_dots = 0

    def _update_loading_text(self):
        dots = "." * (self._loading_dots % 4)
        self.loading_label.setText(f"连接中{dots}")
        self._loading_dots += 1

    def set_channel(self, channel_id: int, channel_name: str = ""):
        self._channel_id = channel_id
        self._channel_name = channel_name or f"通道{channel_id}"
        self.name_label.setText(self._channel_name)
        self.name_label.setStyleSheet("color: #2196F3; font-size: 11px; font-weight: bold;")
        self.set_status("loading")

    def bind_channel(self, channel_id: int, channel_name: str = ""):
        self.set_channel(channel_id, channel_name)

    def unbind_channel(self):
        self.clear_channel()

    def clear_channel(self):
        self._channel_id = None
        self._channel_name = ""
        self._preview_handle = -1
        self.name_label.setText("未分配")
        self.name_label.setStyleSheet("color: #999; font-size: 11px;")
        self.set_status("idle")
        self.set_loading(False)
        self._clear_video_display()

    def _clear_video_display(self):
        self.video_container.setStyleSheet(
            """
            background-color: #0d0d0d;
            border: 1px solid #333;
            """
        )
        self.video_container.update()

    def set_preview_handle(self, handle: int):
        self._preview_handle = handle
        self.set_loading(False)
        if handle >= 0:
            self.set_status("previewing")
        else:
            self.set_status("error")

    def stop_preview(self):
        self._preview_handle = -1
        self.set_loading(False)
        self._clear_video_display()

    def set_loading(self, loading: bool):
        self._is_loading = loading
        if loading:
            self.loading_label.show()
            self._loading_dots = 0
            self._loading_timer.start(500)
            self._update_loading_text()
            self.set_status("loading")
        else:
            self.loading_label.hide()
            self._loading_timer.stop()

    def show_loading(self, text: str = "连接中..."):
        self.loading_label.setText(text)
        self.set_loading(True)

    def show_error(self, detail: str = ""):
        self.set_loading(False)
        self.set_status("error", detail)

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet(
                """
                VideoWidget {
                    background-color: #1a1a1a;
                    border: 2px solid #0078d4;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                VideoWidget {
                    background-color: #1a1a1a;
                    border: 1px solid #333;
                }
                """
            )

    def set_status(self, status: str, detail: str = ""):
        status_styles = {
            "previewing": ("●", "#4CAF50", "播放中"),
            "online": ("●", "#4CAF50", "在线"),
            "loading": ("●", "#ff9800", "连接中"),
            "reconnecting": ("●", "#ff9800", "重连中"),
            "error": ("✗", "#f44336", "错误"),
            "offline": ("●", "#999999", "离线"),
            "idle": ("", "#999999", ""),
        }
        symbol, color, tooltip_text = status_styles.get(status, status_styles["idle"])
        self.status_label.setText(symbol)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.status_label.setToolTip(detail or tooltip_text)

    def get_win_id(self) -> int:
        return int(self.video_container.winId())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            if self.loading_label and self.video_container and self.loading_label.isVisible():
                label_size = self.loading_label.sizeHint()
                x = max(0, (self.video_container.width() - label_size.width()) // 2)
                y = max(0, (self.video_container.height() - label_size.height()) // 2)
                self.loading_label.move(x, y)
        except (RuntimeError, AttributeError):
            pass

    def cleanup(self):
        if self._loading_timer:
            self._loading_timer.stop()
        self._clear_video_display()

    @property
    def index(self) -> int:
        return self._index

    @property
    def channel_id(self):
        return self._channel_id

    @property
    def preview_handle(self) -> int:
        return self._preview_handle

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @property
    def channel_name(self) -> str:
        return self._channel_name

    @property
    def is_bound(self) -> bool:
        return self._channel_id is not None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._index)
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            text = event.mimeData().text()
            if ":" in text:
                event.acceptProposedAction()
                self.video_container.setStyleSheet(
                    """
                    background-color: #0d3d0d;
                    border: 2px solid #4CAF50;
                    """
                )

    def dragLeaveEvent(self, event):
        if not self._is_loading:
            self.video_container.setStyleSheet(
                """
                background-color: #0d0d0d;
                border: 1px solid #333;
                """
            )

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self._is_loading:
            self.video_container.setStyleSheet(
                """
                background-color: #0d0d0d;
                border: 1px solid #333;
                """
            )

        if not event.mimeData().hasText():
            return

        text = event.mimeData().text()
        if ":" not in text:
            return

        try:
            channel_id_str, channel_name = text.split(":", 1)
            channel_id = int(channel_id_str)
            self.channel_dropped.emit(self._index, channel_id, channel_name or f"通道{channel_id}")
            event.acceptProposedAction()
        except (ValueError, IndexError):
            return
