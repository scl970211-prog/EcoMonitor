# -*- coding: utf-8 -*-
"""
主题管理模块

提供浅色 / 深色 / 跟随系统三种主题模式，以及统一的主题色角色（Token）。
当前作为基础设施先行，默认保持浅色主题，为后续全面深色主题切换预留接口。
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Union

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


class Theme(str, Enum):
    """支持的主题模式"""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass(frozen=True)
class ThemeColors:
    """主题色角色，所有 GUI 组件应通过这些语义化角色获取颜色。"""

    background: str
    surface: str
    panel: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    border: str
    primary: str
    primary_hover: str
    primary_pressed: str
    success: str
    warning: str
    error: str
    info: str
    success_surface: str
    warning_surface: str
    error_surface: str
    info_surface: str
    tooltip_bg: str
    tooltip_fg: str
    video_bg: str
    video_container_bg: str
    terminal_bg: str
    terminal_fg: str
    terminal_info: str
    terminal_success: str
    terminal_error: str
    terminal_warning: str


# 浅色主题：与当前 design system 保持一致
LIGHT_COLORS = ThemeColors(
    background="#f5f5f5",
    surface="#ffffff",
    panel="#f9f9f9",
    text_primary="#333333",
    text_secondary="#666666",
    text_disabled="#999999",
    border="#cccccc",
    primary="#2196F3",
    primary_hover="#1976D2",
    primary_pressed="#0D47A1",
    success="#107c10",
    warning="#d67f00",
    error="#c42b1c",
    info="#0078d4",
    success_surface="#e8f5e9",
    warning_surface="#fff3e0",
    error_surface="#ffebee",
    info_surface="#e3f2fd",
    tooltip_bg="#333333",
    tooltip_fg="#ffffff",
    video_bg="#1a1a1a",
    video_container_bg="#0d0d0d",
    terminal_bg="#1e1e1e",
    terminal_fg="#d4d4d4",
    terminal_info="#569cd6",
    terminal_success="#4ec9b0",
    terminal_error="#f44747",
    terminal_warning="#ce9178",
)

# 深色主题：高对比、低饱和，适合长时间监控场景
DARK_COLORS = ThemeColors(
    background="#1e1e1e",
    surface="#252526",
    panel="#2d2d30",
    text_primary="#e0e0e0",
    text_secondary="#a0a0a0",
    text_disabled="#6e6e6e",
    border="#3e3e42",
    primary="#4fc3f7",
    primary_hover="#29b6f6",
    primary_pressed="#0288d1",
    success="#2ecc71",
    warning="#f39c12",
    error="#e74c3c",
    info="#5dade2",
    success_surface="#1b3a1b",
    warning_surface="#3d2e0e",
    error_surface="#3b1b1b",
    info_surface="#1a2f3f",
    tooltip_bg="#2d2d30",
    tooltip_fg="#e0e0e0",
    video_bg="#0a0a0a",
    video_container_bg="#000000",
    terminal_bg="#0c0c0c",
    terminal_fg="#cccccc",
    terminal_info="#569cd6",
    terminal_success="#4ec9b0",
    terminal_error="#f44747",
    terminal_warning="#ce9178",
)


def _is_windows_dark_mode() -> bool:
    """检测 Windows 是否处于深色应用模式（仅 Windows）"""
    try:
        # 通过注册表读取系统主题设置
        settings = QSettings(
            "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
            QSettings.Format.NativeFormat,
        )
        value = settings.value("AppsUseLightTheme", 1)
        # 0 表示深色，1 表示浅色
        return int(value) == 0
    except Exception:
        logger.debug("检测 Windows 系统主题失败，默认按浅色处理")
        return False


class ThemeManager:
    """主题管理器（单例）

    负责维护当前主题、提供主题色 Token、将主题应用到 QApplication。
    """

    _instance: Optional["ThemeManager"] = None

    def __new__(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._theme = Theme.LIGHT
        return cls._instance

    def set_theme(self, theme: Union[Theme, str]) -> None:
        """设置当前主题"""
        if isinstance(theme, str):
            try:
                theme = Theme(theme.lower())
            except ValueError:
                logger.warning(f"未知主题值 {theme!r}，使用浅色主题")
                theme = Theme.LIGHT
        self._theme = theme
        logger.info(f"主题已设置为 {self._theme.value}")

    def current(self) -> Theme:
        """返回实际生效的主题（SYSTEM 会解析为 LIGHT 或 DARK）"""
        if self._theme == Theme.SYSTEM:
            return Theme.DARK if _is_windows_dark_mode() else Theme.LIGHT
        return self._theme

    def colors(self) -> ThemeColors:
        """返回当前主题对应的色板"""
        return DARK_COLORS if self.current() == Theme.DARK else LIGHT_COLORS

    def apply_to_app(self, app: Optional[QApplication] = None) -> None:
        """将当前主题映射到 QApplication 的 QPalette。

        注意：本方法只设置基础调色板，未迁移到动态 QSS 的控件仍可能
        保持原有样式。在全面完成样式 Token 化之前，默认保持浅色主题。
        """
        if app is None:
            app = QApplication.instance()
        if app is None:
            logger.warning("QApplication 尚未创建，无法应用主题调色板")
            return

        colors = self.colors()
        palette = QPalette()

        palette.setColor(QPalette.ColorRole.Window, QColor(colors.background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.text_primary))
        palette.setColor(QPalette.ColorRole.Base, QColor(colors.surface))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors.panel))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.panel))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.text_primary))
        palette.setColor(QPalette.ColorRole.Text, QColor(colors.text_primary))
        palette.setColor(QPalette.ColorRole.Button, QColor(colors.panel))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.text_primary))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(colors.error))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.primary))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        palette.setColor(QPalette.ColorRole.Link, QColor(colors.info))

        # Disabled 状态
        disabled_color = QColor(colors.text_disabled)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_color)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_color)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_color)

        app.setPalette(palette)
        logger.debug(f"已应用 {self.current().value} 主题调色板")


def _get_colors(colors: Optional[ThemeColors] = None) -> ThemeColors:
    """返回传入的色板或当前主题色板。"""
    return colors if colors is not None else get_theme_manager().colors()


def status_color(status: str, colors: Optional[ThemeColors] = None) -> str:
    """根据状态名称返回主题色。

    支持的状态：online/connected/success、offline/disconnected、error/failed、
    warning/reconnecting/loading、info。
    """
    colors = _get_colors(colors)
    mapping = {
        "online": colors.success,
        "connected": colors.success,
        "success": colors.success,
        "offline": colors.text_secondary,
        "disconnected": colors.text_secondary,
        "error": colors.error,
        "failed": colors.error,
        "warning": colors.warning,
        "reconnecting": colors.warning,
        "loading": colors.warning,
        "info": colors.info,
    }
    return mapping.get(status.lower(), colors.text_primary)


def set_status_style(
    widget: QWidget,
    status: str,
    size: Optional[str] = None,
    bold: bool = False,
    colors: Optional[ThemeColors] = None,
) -> None:
    """为控件设置状态颜色样式（保留字号、加粗等可选属性）。"""
    parts = [f"color: {status_color(status, colors)};"]
    if size:
        parts.append(f"font-size: {size};")
    if bold:
        parts.append("font-weight: bold;")
    widget.setStyleSheet(" ".join(parts))


def text_color(role: str, colors: Optional[ThemeColors] = None) -> str:
    """返回文本角色对应的主题色。

    支持的角色：primary、secondary、disabled、success、warning、error、info、primary_color。
    """
    colors = _get_colors(colors)
    mapping = {
        "primary": colors.text_primary,
        "secondary": colors.text_secondary,
        "disabled": colors.text_disabled,
        "success": colors.success,
        "warning": colors.warning,
        "error": colors.error,
        "info": colors.info,
        "primary_color": colors.primary,
    }
    return mapping.get(role, colors.text_primary)


def set_text_style(
    widget: QWidget,
    role: str = "primary",
    size: Optional[str] = None,
    bold: bool = False,
    colors: Optional[ThemeColors] = None,
) -> None:
    """为控件设置文本角色样式。"""
    parts = [f"color: {text_color(role, colors)};"]
    if size:
        parts.append(f"font-size: {size};")
    if bold:
        parts.append("font-weight: bold;")
    widget.setStyleSheet(" ".join(parts))


def log_badge_colors(
    level: str, colors: Optional[ThemeColors] = None
) -> Tuple[str, str]:
    """返回日志 badge 的背景色与前景色。"""
    colors = _get_colors(colors)
    mapping = {
        "INFO": (colors.info_surface, colors.info),
        "WARN": (colors.warning_surface, colors.warning),
        "ERROR": (colors.error_surface, colors.error),
    }
    return mapping.get(level, (colors.panel, colors.text_secondary))


def task_status_color(status: str, colors: Optional[ThemeColors] = None) -> str:
    """返回下载任务状态对应的主题色。"""
    colors = _get_colors(colors)
    mapping = {
        "pending": colors.text_disabled,
        "downloading": colors.primary,
        "converting": colors.info,
        "reconnecting": colors.warning,
        "completed": colors.success,
        "failed": colors.error,
        "paused": colors.warning,
        "cancelled": colors.text_disabled,
    }
    return mapping.get(status.lower(), colors.text_primary)


def task_status_surface(status: str, colors: Optional[ThemeColors] = None) -> str:
    """返回下载任务状态对应的背景表面色。"""
    colors = _get_colors(colors)
    mapping = {
        "pending": colors.panel,
        "downloading": colors.info_surface,
        "converting": colors.info_surface,
        "reconnecting": colors.warning_surface,
        "completed": colors.success_surface,
        "failed": colors.error_surface,
        "paused": colors.warning_surface,
        "cancelled": colors.panel,
    }
    return mapping.get(status.lower(), colors.surface)


def terminal_color(level: str, colors: Optional[ThemeColors] = None) -> str:
    """返回终端语义色。"""
    colors = _get_colors(colors)
    mapping = {
        "info": colors.terminal_info,
        "success": colors.terminal_success,
        "ok": colors.terminal_success,
        "error": colors.terminal_error,
        "warning": colors.terminal_warning,
        "disconnected": colors.terminal_warning,
        "text": colors.terminal_fg,
    }
    return mapping.get(level.lower(), colors.terminal_fg)


def rgba_color(hex_color: str, alpha: int) -> str:
    """将十六进制颜色转换为 rgba 字符串，用于 QSS。

    Args:
        hex_color: #RRGGBB 格式颜色。
        alpha: 0-255 的透明度。
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def get_theme_manager() -> ThemeManager:
    """获取 ThemeManager 单例"""
    return ThemeManager()
