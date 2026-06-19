# -*- coding: utf-8 -*-
"""
图标字体工具模块

使用系统自带的 Segoe Fluent Icons（或降级到 Segoe MDL2 Assets）作为图标字体，
将图标渲染为 QIcon/QPixmap 后设置到控件上，避免引入外部 SVG/字体文件。

使用方式：
    from src.gui.icons import Icon, set_button_icon, create_icon
    set_button_icon(btn, Icon.CLEAR)
    tab.setTabIcon(index, create_icon(Icon.SEARCH))
"""

import logging
from typing import Dict, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QPushButton

from .constants import Color, TabLabel

logger = logging.getLogger(__name__)

# 图标字体候选，按优先级匹配
_FONT_CANDIDATES = [
    "Segoe Fluent Icons",
    "Segoe MDL2 Assets",
    "Segoe UI Symbol",
]


class Icon:
    """Segoe Fluent Icons 常用图标 Unicode 码点（PUA 区域）"""

    # 标签页图标
    SEARCH = "\ue721"          # 设备搜索
    CONNECT = "\ue703"         # 设备连接
    VIDEO = "\ue714"           # 视频预览
    DOWNLOAD = "\ue896"        # 批量下载
    MANAGE = "\ue71d"          # 下载管理（AllApps）
    TERMINAL = "\uec31"        # 终端调试（KeyboardFull）
    NETWORK_QUALITY = "\uec05" # 网络质量（NetworkTower）
    SPEED = "\uec4a"           # 网络测速（SpeedHigh）
    WARNING = "\ue7ba"         # IP 冲突检测
    TRAFFIC = "\ue7a5"         # 流量分析（DataSenseBar）
    FILTER = "\ue71c"          # 抓包分析

    # 通用工具图标
    CLEAR = "\ue894"
    EXPORT = "\ue72d"          # Share
    ADD = "\ue710"
    CANCEL = "\ue711"
    SETTINGS = "\ue713"
    REFRESH = "\ue72c"


# 标签页 -> 图标映射
TAB_ICONS: Dict[str, str] = {
    TabLabel.DEVICE_SCAN: Icon.SEARCH,
    TabLabel.CONNECTION: Icon.CONNECT,
    TabLabel.PREVIEW: Icon.VIDEO,
    TabLabel.DOWNLOAD: Icon.DOWNLOAD,
    TabLabel.DOWNLOAD_MANAGER: Icon.MANAGE,
    TabLabel.TERMINAL: Icon.TERMINAL,
    TabLabel.NETWORK_QUALITY: Icon.NETWORK_QUALITY,
    TabLabel.SPEEDTEST: Icon.SPEED,
    TabLabel.IP_CONFLICT: Icon.WARNING,
    TabLabel.TRAFFIC_ANALYSIS: Icon.TRAFFIC,
    TabLabel.PACKET_CAPTURE: Icon.FILTER,
}


def icon_font_family() -> Optional[str]:
    """返回系统中可用的图标字体名称，若无可用字体则返回 None。"""
    try:
        available = set(QFontDatabase.families())
    except Exception:
        logger.debug("读取系统字体列表失败")
        return None

    for family in _FONT_CANDIDATES:
        if family in available:
            return family
    return None


def is_icon_font_available() -> bool:
    """系统是否安装了支持的图标字体"""
    return icon_font_family() is not None


def create_icon(
    codepoint: str,
    size: int = 18,
    color: Optional[QColor] = None,
) -> Optional[QIcon]:
    """将单个图标字体码点渲染为 QIcon。

    Args:
        codepoint: 图标 Unicode 码点，如 Icon.SEARCH。
        size: 图标像素尺寸（默认 18）。
        color: 图标颜色，默认使用 Color.GRAY_700。

    Returns:
        QIcon 实例；如果图标字体不可用或码点为空，则返回 None。
    """
    family = icon_font_family()
    if not family or not codepoint:
        return None

    if color is None:
        color = QColor(Color.GRAY_700)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(family, int(size * 0.7))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, codepoint)
    finally:
        painter.end()

    return QIcon(pixmap)


def set_button_icon(
    button: QPushButton,
    codepoint: str,
    size: int = 16,
    color: Optional[QColor] = None,
) -> None:
    """为 QPushButton 设置图标字体图标（保留原有文字）。

    如果图标字体不可用，则保持按钮原状，实现静默降级。
    """
    icon = create_icon(codepoint, size, color)
    if icon is None:
        return
    button.setIcon(icon)
    button.setIconSize(QSize(size, size))


def create_tab_icon(label: str, size: int = 18, color: Optional[QColor] = None) -> Optional[QIcon]:
    """根据标签页标题获取对应的图标。"""
    codepoint = TAB_ICONS.get(label)
    if not codepoint:
        return None
    return create_icon(codepoint, size, color)
