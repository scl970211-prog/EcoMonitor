# -*- coding: utf-8 -*-
"""
视频显示控件 - 使用 OpenGL 渲染视频帧
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QColor, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLTexture

from ...gui.theme import get_theme_manager

logger = logging.getLogger(__name__)


class VideoRenderWidget(QOpenGLWidget):
    """
    OpenGL 视频渲染控件
    高效渲染视频帧
    """
    
    # 信号
    clicked = pyqtSignal()           # 点击
    double_clicked = pyqtSignal()    # 双击
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_image: Optional[QImage] = None
        self._keep_aspect_ratio = True
        self._bg_color = QColor(20, 20, 20)
        self._show_loading = False
        self._loading_text = "连接中..."
        self._error_text = ""
        
        # 设置焦点策略
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        
    def update_frame(self, image: QImage):
        """更新视频帧"""
        self._current_image = image
        self._show_loading = False
        self._error_text = ""
        self.update()  # 触发重绘
    
    def show_loading(self, text: str = "连接中..."):
        """显示加载状态"""
        self._show_loading = True
        self._loading_text = text
        self._error_text = ""
        self.update()
    
    def show_error(self, text: str):
        """显示错误信息"""
        self._error_text = text
        self._show_loading = False
        self.update()
    
    def clear(self):
        """清除显示"""
        self._current_image = None
        self._show_loading = False
        self._error_text = ""
        self.update()
    
    def paintEvent(self, event):
        """绘制事件"""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 填充背景
        painter.fillRect(self.rect(), self._bg_color)
        
        # 绘制视频帧
        if self._current_image and not self._current_image.isNull():
            self._draw_video_frame(painter)
        
        # 绘制加载提示
        elif self._show_loading:
            self._draw_centered_text(painter, self._loading_text, QColor(200, 200, 200))
        
        # 绘制错误信息
        elif self._error_text:
            self._draw_centered_text(painter, self._error_text, QColor(255, 100, 100))
        
        # 绘制默认提示
        else:
            self._draw_centered_text(painter, "无信号", QColor(100, 100, 100))
        
        painter.end()
    
    def _draw_video_frame(self, painter: QPainter):
        """绘制视频帧"""
        widget_rect = self.rect()
        img_width = self._current_image.width()
        img_height = self._current_image.height()
        
        if self._keep_aspect_ratio:
            # 保持宽高比
            widget_aspect = widget_rect.width() / widget_rect.height()
            img_aspect = img_width / img_height
            
            if widget_aspect > img_aspect:
                # 窗口更宽，按高度缩放
                new_height = widget_rect.height()
                new_width = int(new_height * img_aspect)
                x = (widget_rect.width() - new_width) // 2
                y = 0
            else:
                # 窗口更高，按宽度缩放
                new_width = widget_rect.width()
                new_height = int(new_width / img_aspect)
                x = 0
                y = (widget_rect.height() - new_height) // 2
            
            target_rect = painter.viewport().adjusted(x, y, x, y)
            target_rect.setWidth(new_width)
            target_rect.setHeight(new_height)
        else:
            # 拉伸填充
            target_rect = widget_rect
        
        painter.drawImage(target_rect, self._current_image)
    
    def _draw_centered_text(self, painter: QPainter, text: str, color: QColor):
        """绘制居中文本"""
        painter.setPen(color)
        font = QFont("Microsoft YaHei", 12)
        painter.setFont(font)
        
        rect = self.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    
    def mousePressEvent(self, event):
        """鼠标点击"""
        super().mousePressEvent(event)
        self.clicked.emit()
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击"""
        super().mouseDoubleClickEvent(event)
        self.double_clicked.emit()


class VideoWidget(QWidget):
    """
    视频控件（带边框和标题）
    """
    
    # 信号
    clicked = pyqtSignal(int)           # 点击，参数: index
    double_clicked = pyqtSignal(int)    # 双击，参数: index
    channel_dropped = pyqtSignal(int, int, str)  # 通道拖放，参数: index, channel_id, channel_name
    
    def __init__(self, index: int = 0, parent=None):
        super().__init__(parent)
        
        self.index = index
        self.channel_id: Optional[int] = None
        self.channel_name: str = ""
        self._preview_handle: int = -1
        
        self._init_ui()
        self._setup_drag_drop()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # 视频渲染区
        self.video_render = VideoRenderWidget()
        self.video_render.clicked.connect(lambda: self.clicked.emit(self.index))
        self.video_render.double_clicked.connect(lambda: self.double_clicked.emit(self.index))
        layout.addWidget(self.video_render, 1)
        
        # 信息标签
        tc = get_theme_manager().colors()
        self.info_label = QLabel(f"窗口 {self.index + 1}")
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {tc.text_secondary};
                background-color: {tc.panel};
                padding: 4px 8px;
                font-size: 11px;
            }}
        """)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        # 默认样式
        self.setStyleSheet(f"""
            VideoWidget {{
                background-color: {tc.video_bg};
                border: 2px solid {tc.border};
            }}
            VideoWidget:hover {{
                border: 2px solid {tc.text_disabled};
            }}
            VideoWidget[active="true"] {{
                border: 2px solid {tc.success};
            }}
            VideoWidget[selected="true"] {{
                border: 2px solid {tc.primary};
            }}
        """)
        
        self.setProperty("active", False)
        self.setProperty("selected", False)
    
    def _setup_drag_drop(self):
        """设置拖拽接收"""
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event):
        """拖拽进入"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """拖放"""
        text = event.mimeData().text()
        try:
            channel_id, channel_name = text.split(":", 1)
            channel_id = int(channel_id)
            self.channel_dropped.emit(self.index, channel_id, channel_name)
            event.acceptProposedAction()
        except Exception as e:
            logger.warning(f"拖放数据解析失败: {e}")
    
    def bind_channel(self, channel_id: int, channel_name: str = ""):
        """绑定通道"""
        self.channel_id = channel_id
        self.channel_name = channel_name or f"通道{channel_id}"
        self.info_label.setText(f"{self.channel_name}")
        self.setProperty("active", True)
        self.style().unpolish(self)
        self.style().polish(self)
    
    def unbind_channel(self):
        """解绑通道"""
        self.channel_id = None
        self.channel_name = ""
        self._preview_handle = -1
        self.info_label.setText(f"窗口 {self.index + 1}")
        self.video_render.clear()
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)
    
    def update_frame(self, image: QImage):
        """更新视频帧"""
        self.video_render.update_frame(image)
    
    def show_loading(self, text: str = "连接中..."):
        """显示加载状态"""
        self.video_render.show_loading(text)
    
    def show_error(self, text: str):
        """显示错误"""
        self.video_render.show_error(text)
    
    def clear(self):
        """清除显示"""
        self.video_render.clear()
    
    def set_selected(self, selected: bool):
        """设置选中状态"""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
    
    def set_preview_handle(self, handle: int):
        """设置预览句柄"""
        self._preview_handle = handle
    
    @property
    def is_bound(self) -> bool:
        """是否已绑定通道"""
        return self.channel_id is not None
