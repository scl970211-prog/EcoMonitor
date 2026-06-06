# -*- coding: utf-8 -*-
"""
可拖拽的通道列表组件
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QApplication

logger = logging.getLogger(__name__)


class DraggableChannelList(QListWidget):
    """
    支持拖拽的通道列表
    可以将通道拖拽到视频窗口
    """
    
    # 信号
    channel_dragged = pyqtSignal(int, str)  # channel_id, channel_name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 启用拖拽
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        
        # 设置选择模式
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        # 禁用编辑
        self.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        
        # 拖拽起始位置
        self._drag_start_pos = None
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 启动拖拽"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        
        if self._drag_start_pos is None:
            return
        
        # 计算移动距离，防止误触
        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            return
        
        # 获取当前选中的项
        current_item = self.currentItem()
        if not current_item:
            return
        
        # 获取通道信息
        channel_id = current_item.data(Qt.ItemDataRole.UserRole)
        channel_name = current_item.data(Qt.ItemDataRole.UserRole + 1)
        
        if channel_id is None:
            return
        
        # 发射信号
        self.channel_dragged.emit(int(channel_id), channel_name or str(channel_id))
        
        # 创建拖拽对象
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"{channel_id}:{channel_name}")
        drag.setMimeData(mime_data)
        
        # 执行拖拽
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
