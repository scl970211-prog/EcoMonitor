# -*- coding: utf-8 -*-
"""
网络测速实时曲线控件

同时显示下载/上传两条速度曲线，带网格、坐标轴、渐变填充与图例。
直接使用 QPainter 绘制，不依赖 matplotlib。
"""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from ..theme import get_theme_manager


class SpeedChartWidget(QWidget):
    """实时双曲线图"""

    def __init__(self, parent=None, max_points: int = 80):
        super().__init__(parent)
        self._download_points = []
        self._upload_points = []
        self._max_points = max(max_points, 20)
        self.setMinimumSize(320, 220)
        self.setObjectName("speedChart")

    # ---- 公共接口 ----

    def add_download_point(self, value: float):
        self._download_points.append(value)
        if len(self._download_points) > self._max_points:
            self._download_points.pop(0)
        self.update()

    def add_upload_point(self, value: float):
        self._upload_points.append(value)
        if len(self._upload_points) > self._max_points:
            self._upload_points.pop(0)
        self.update()

    def reset(self):
        self._download_points.clear()
        self._upload_points.clear()
        self.update()

    # ---- 绘制 ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tc = get_theme_manager().colors()
        # 绘图区域：留出坐标轴标签空间（使用 QRectF 避免 QPoint/QPointF 类型问题）
        plot_rect = QRectF(self.rect()).adjusted(44, 24, -16, -40)

        # 网格
        self._draw_grid(painter, plot_rect, tc)

        # 坐标轴
        self._draw_axes(painter, plot_rect, tc)

        # 曲线
        max_value = max(1.0, max(self._download_points + self._upload_points, default=1.0))
        self._draw_series(
            painter, plot_rect, self._download_points, QColor(tc.primary), max_value
        )
        self._draw_series(
            painter, plot_rect, self._upload_points, QColor(tc.success), max_value
        )

        # 图例
        self._draw_legend(painter, tc)

    def _draw_grid(self, painter: QPainter, rect, tc):
        pen = QPen(QColor(tc.border))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        rows = 4
        cols = 6
        for i in range(1, rows):
            y = rect.top() + i * rect.height() / rows
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
        for i in range(1, cols):
            x = rect.left() + i * rect.width() / cols
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))

    def _draw_axes(self, painter: QPainter, rect, tc):
        pen = QPen(QColor(tc.text_secondary))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.right()), int(rect.bottom()))
        painter.drawLine(int(rect.left()), int(rect.top()), int(rect.left()), int(rect.bottom()))

        max_value = max(1.0, max(self._download_points + self._upload_points, default=1.0))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        painter.setPen(QColor(tc.text_secondary))
        for i, label in enumerate(["0", f"{max_value * 0.25:.0f}", f"{max_value * 0.5:.0f}", f"{max_value:.0f}"]):
            y = rect.bottom() - i * rect.height() / 4
            painter.drawText(int(rect.left() - 38), int(y - 6), 34, 12, Qt.AlignmentFlag.AlignRight, label)

    def _draw_series(self, painter: QPainter, rect, points, color, max_value):
        if len(points) < 2:
            return
        path = QPainterPath()
        for i, value in enumerate(points):
            x = rect.left() + i * rect.width() / (len(points) - 1)
            y = rect.bottom() - (value / max_value) * rect.height()
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # 曲线
        pen = QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

        # 渐变填充
        fill_path = QPainterPath(path)
        fill_path.lineTo(rect.right(), rect.bottom())
        fill_path.lineTo(rect.left(), rect.bottom())
        fill_path.closeSubpath()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 50))
        gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.fillPath(fill_path, QBrush(gradient))

    def _draw_legend(self, painter: QPainter, tc):
        rect = self.rect()
        font = QFont("Microsoft YaHei", 9)
        painter.setFont(font)
        items = [
            ("下载", QColor(tc.primary)),
            ("上传", QColor(tc.success)),
        ]
        x = rect.right() - 16
        for text, color in reversed(items):
            text_width = painter.fontMetrics().horizontalAdvance(text) + 8
            x -= text_width + 18
            painter.fillRect(int(x), int(rect.top() + 6), 10, 4, color)
            painter.setPen(QColor(tc.text_secondary))
            painter.drawText(int(x + 14), int(rect.top() + 8), text)
