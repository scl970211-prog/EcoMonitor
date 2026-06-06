# -*- coding: utf-8 -*-
"""
视频网格布局组件。
基于原预览项目行为，支持 1/2/3/4/8 分屏。
"""

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from .video_widget import VideoWidget


class VideoGridV2(QWidget):
    """视频网格布局管理器。"""

    video_clicked = pyqtSignal(int)
    video_double_clicked = pyqtSignal(int)
    channel_dropped = pyqtSignal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = 4
        self._video_widgets: List[VideoWidget] = []
        self._channel_bindings: Dict[int, int] = {}
        self._init_ui()
        self._create_widgets(4)

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

    def _create_widgets(self, count: int):
        for widget in self._video_widgets:
            widget.deleteLater()
        self._video_widgets.clear()
        self._channel_bindings.clear()

        for i in range(count):
            widget = VideoWidget(i)
            widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            widget.setMinimumSize(160, 90)
            widget.clicked.connect(self.video_clicked.emit)
            widget.double_clicked.connect(self.video_double_clicked.emit)
            widget.channel_dropped.connect(self.channel_dropped.emit)
            self._video_widgets.append(widget)

        self._arrange_widgets()

    def _arrange_widgets(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if self._layout_type == 3:
            self._arrange_3_split()
            return

        if self._layout_type == 1:
            rows, cols = 1, 1
        elif self._layout_type == 2:
            rows, cols = 1, 2
        elif self._layout_type == 4:
            rows, cols = 2, 2
        elif self._layout_type == 8:
            rows, cols = 2, 4
        else:
            rows, cols = 2, 2

        index = 0
        for row in range(rows):
            for col in range(cols):
                if index < len(self._video_widgets):
                    self.grid_layout.addWidget(self._video_widgets[index], row, col)
                    index += 1

        for i in range(rows):
            self.grid_layout.setRowStretch(i, 1)
        for i in range(cols):
            self.grid_layout.setColumnStretch(i, 1)

    def _arrange_3_split(self):
        if len(self._video_widgets) < 3:
            return

        self.grid_layout.addWidget(self._video_widgets[0], 0, 0)
        self.grid_layout.addWidget(self._video_widgets[1], 0, 1)
        self.grid_layout.addWidget(self._video_widgets[2], 1, 0, 1, 2)

        self.grid_layout.setRowStretch(0, 1)
        self.grid_layout.setRowStretch(1, 1)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)

    def set_layout(self, layout_type: int):
        if layout_type not in (1, 2, 3, 4, 8):
            layout_type = 4

        if self._layout_type == layout_type:
            return

        self._layout_type = layout_type
        current_count = len(self._video_widgets)
        needed_count = layout_type

        if current_count != needed_count:
            old_bindings = {}
            for widget in self._video_widgets:
                if widget.channel_id is not None:
                    old_bindings[widget.index] = (widget.channel_id, widget.channel_name)

            self._create_widgets(needed_count)

            for new_index, (_, binding) in enumerate(old_bindings.items()):
                if new_index < needed_count:
                    channel_id, name = binding
                    self._video_widgets[new_index].set_channel(channel_id, name)
                    self._channel_bindings[channel_id] = new_index
        else:
            self._arrange_widgets()

    def get_widget(self, index: int) -> Optional[VideoWidget]:
        if 0 <= index < len(self._video_widgets):
            return self._video_widgets[index]
        return None

    def get_widget_by_channel(self, channel_id: int) -> Optional[VideoWidget]:
        if channel_id in self._channel_bindings:
            return self._video_widgets[self._channel_bindings[channel_id]]
        return None

    def bind_channel(self, window_index: int, channel_id: int, channel_name: str = ""):
        if window_index < 0 or window_index >= len(self._video_widgets):
            return

        if channel_id in self._channel_bindings:
            old_index = self._channel_bindings[channel_id]
            if old_index != window_index:
                self._video_widgets[old_index].clear_channel()

        widget = self._video_widgets[window_index]
        if widget.channel_id is not None and widget.channel_id != channel_id:
            self._channel_bindings.pop(widget.channel_id, None)

        widget.set_channel(channel_id, channel_name)
        self._channel_bindings[channel_id] = window_index

    def unbind_channel(self, channel_id: int):
        if channel_id in self._channel_bindings:
            index = self._channel_bindings.pop(channel_id)
            if index < len(self._video_widgets):
                self._video_widgets[index].clear_channel()

    def clear_all_channels(self):
        for widget in self._video_widgets:
            widget.clear_channel()
        self._channel_bindings.clear()

    def get_bound_channels(self) -> List[Tuple[int, int, str]]:
        bindings = []
        for widget in self._video_widgets:
            if widget.channel_id is not None:
                bindings.append((widget.index, widget.channel_id, widget.channel_name))
        return bindings

    def get_available_window(self) -> int:
        for i, widget in enumerate(self._video_widgets):
            if widget.channel_id is None:
                return i
        return -1

    def get_all_widgets(self) -> List[VideoWidget]:
        return self._video_widgets.copy()

    def show_channel_loading(self, channel_id: int, text: str = "连接中..."):
        widget = self.get_widget_by_channel(channel_id)
        if widget:
            widget.show_loading(text)

    def show_channel_error(self, channel_id: int, error_msg: str):
        widget = self.get_widget_by_channel(channel_id)
        if widget:
            widget.show_error(error_msg)

    @property
    def current_layout(self) -> int:
        return self._layout_type

    @property
    def widget_count(self) -> int:
        return len(self._video_widgets)
