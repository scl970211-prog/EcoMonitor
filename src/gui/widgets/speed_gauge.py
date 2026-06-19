# -*- coding: utf-8 -*-
"""
网络测速仪表盘控件

一个自绘的圆形速度仪表盘，支持：
- 动态进度弧与中心大字显示；
- 阶段颜色切换（延迟/下载/上传/完成/错误）；
- value/progress 属性动画（QPropertyAnimation）。
"""

from enum import Enum

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..theme import get_theme_manager


class SpeedPhase(Enum):
    """测速阶段"""

    IDLE = "idle"
    LATENCY = "latency"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    DONE = "done"
    ERROR = "error"


class SpeedGauge(QWidget):
    """圆形速度仪表盘"""

    valueChanged = pyqtSignal(float)
    progressChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._progress = 0.0
        self._phase = SpeedPhase.IDLE
        self._max_value = 100.0
        self._color = QColor(self._phase_color(SpeedPhase.IDLE))
        self._target_color = QColor(self._color)
        self._color_anim = None
        self._value_anim = None
        self._progress_anim = None
        self.setMinimumSize(280, 280)
        self.setObjectName("speedGauge")

    # ---- 公共接口 ----

    def set_phase(self, phase: SpeedPhase, animate: bool = True):
        """切换当前阶段，同步改变仪表盘主题色"""
        self._phase = phase
        target = QColor(self._phase_color(phase))
        self._target_color = target
        if animate:
            self._start_color_animation(target)
        else:
            self._color = target
        self.update()

    def set_value(self, value: float, animate: bool = True):
        """设置当前显示数值，并自动调整表盘上限"""
        value = max(0.0, value)
        self._max_value = self._auto_max(value)
        if animate:
            self._start_value_animation(value)
        else:
            self._value = value
            self.valueChanged.emit(value)
            self.update()

    def set_progress(self, progress: float, animate: bool = True):
        """设置进度弧 0.0-1.0"""
        progress = max(0.0, min(1.0, progress))
        if animate:
            self._start_progress_animation(progress)
        else:
            self._progress = progress
            self.progressChanged.emit(progress)
            self.update()

    def reset(self):
        """重置为空闲状态"""
        self._value = 0.0
        self._progress = 0.0
        self._max_value = 100.0
        self.set_phase(SpeedPhase.IDLE, animate=False)
        self.update()

    # ---- 绘制 ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tc = get_theme_manager().colors()
        rect = self.rect().adjusted(24, 24, -24, -24)
        center = rect.center()
        radius = min(rect.width(), rect.height()) / 2.0 - 16

        # 背景圆环
        pen_bg = QPen(QColor(tc.border), 10)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            int(center.x() - radius),
            int(center.y() - radius),
            int(radius * 2),
            int(radius * 2),
            225 * 16,
            -270 * 16,
        )

        # 进度弧
        pen_fg = QPen(self._color, 12)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        span = int(-270 * 16 * self._progress)
        painter.drawArc(
            int(center.x() - radius),
            int(center.y() - radius),
            int(radius * 2),
            int(radius * 2),
            225 * 16,
            span,
        )

        # 中心数值
        value_text = f"{self._value:.1f}"
        unit_text = self._phase_unit(self._phase)
        phase_text = self._phase_label(self._phase)

        painter.setPen(QColor(tc.text_primary))
        value_font = QFont("Microsoft YaHei", 26, QFont.Weight.Bold)
        painter.setFont(value_font)
        painter.drawText(
            rect.adjusted(0, -24, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            value_text,
        )

        painter.setPen(QColor(tc.text_secondary))
        unit_font = QFont("Microsoft YaHei", 10)
        painter.setFont(unit_font)
        painter.drawText(
            rect.adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            unit_text,
        )

        phase_font = QFont("Microsoft YaHei", 9)
        painter.setFont(phase_font)
        painter.drawText(
            rect.adjusted(0, 46, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            phase_text,
        )

    # ---- 私有辅助 ----

    def _phase_color(self, phase: SpeedPhase) -> str:
        tc = get_theme_manager().colors()
        mapping = {
            SpeedPhase.IDLE: tc.primary,
            SpeedPhase.LATENCY: tc.warning,
            SpeedPhase.DOWNLOAD: tc.primary,
            SpeedPhase.UPLOAD: tc.success,
            SpeedPhase.DONE: tc.success,
            SpeedPhase.ERROR: tc.error,
        }
        return mapping.get(phase, tc.primary)

    def _phase_label(self, phase: SpeedPhase) -> str:
        mapping = {
            SpeedPhase.IDLE: "准备就绪",
            SpeedPhase.LATENCY: "网络延迟",
            SpeedPhase.DOWNLOAD: "下载速度",
            SpeedPhase.UPLOAD: "上传速度",
            SpeedPhase.DONE: "测速完成",
            SpeedPhase.ERROR: "测速失败",
        }
        return mapping.get(phase, "")

    def _phase_unit(self, phase: SpeedPhase) -> str:
        if phase == SpeedPhase.LATENCY:
            return "ms"
        return "Mbps"

    def _auto_max(self, value: float) -> float:
        thresholds = [10, 50, 100, 200, 500, 1000, 2000, 5000]
        for t in thresholds:
            if value <= t:
                return t
        return 10000.0

    def _start_value_animation(self, target: float):
        if self._value_anim is not None:
            self._value_anim.stop()
        self._value_anim = QPropertyAnimation(self, b"value")
        self._value_anim.setDuration(250)
        self._value_anim.setStartValue(self._value)
        self._value_anim.setEndValue(target)
        self._value_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._value_anim.start()

    def _start_progress_animation(self, target: float):
        if self._progress_anim is not None:
            self._progress_anim.stop()
        self._progress_anim = QPropertyAnimation(self, b"progress")
        self._progress_anim.setDuration(350)
        self._progress_anim.setStartValue(self._progress)
        self._progress_anim.setEndValue(target)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._progress_anim.start()

    def _start_color_animation(self, target: QColor):
        if self._color_anim is not None:
            self._color_anim.stop()
        self._color_anim = QPropertyAnimation(self, b"gaugeColor")
        self._color_anim.setDuration(300)
        self._color_anim.setStartValue(self._color)
        self._color_anim.setEndValue(target)
        self._color_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._color_anim.valueChanged.connect(self._on_color_changed)
        self._color_anim.start()

    def _on_color_changed(self, color):
        self._color = QColor(color)
        self.update()

    # ---- Qt 属性 ----

    @pyqtProperty(float)
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v
        self.valueChanged.emit(v)
        self.update()

    @pyqtProperty(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, p):
        self._progress = p
        self.progressChanged.emit(p)
        self.update()

    @pyqtProperty(QColor)
    def gaugeColor(self):
        return self._color

    @gaugeColor.setter
    def gaugeColor(self, c):
        self._color = QColor(c)
        self.update()
