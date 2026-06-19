# -*- coding: utf-8 -*-
"""
图标字体工具模块测试
"""

from PyQt6.QtWidgets import QPushButton

from src.gui.constants import TabLabel
from src.gui.icons import (
    Icon,
    TAB_ICONS,
    create_icon,
    create_tab_icon,
    icon_font_family,
    is_icon_font_available,
    set_button_icon,
)


def test_icon_font_family_available():
    """在 Windows 开发/打包环境中应至少能匹配到一种系统图标字体。"""
    family = icon_font_family()
    assert family is not None or not is_icon_font_available()
    if family is not None:
        assert "Segoe" in family


def test_create_icon_returns_icon():
    icon = create_icon(Icon.SEARCH, size=18)
    if is_icon_font_available():
        assert icon is not None
        pixmap = icon.pixmap(18, 18)
        assert not pixmap.isNull()
    else:
        assert icon is None


def test_create_icon_with_empty_codepoint():
    assert create_icon("", size=18) is None


def test_tab_icon_mapping_complete():
    """所有主窗口标签页都应存在图标映射。"""
    for label in (
        TabLabel.DEVICE_SCAN,
        TabLabel.CONNECTION,
        TabLabel.PREVIEW,
        TabLabel.DOWNLOAD,
        TabLabel.DOWNLOAD_MANAGER,
        TabLabel.TERMINAL,
        TabLabel.NETWORK_QUALITY,
        TabLabel.SPEEDTEST,
        TabLabel.IP_CONFLICT,
        TabLabel.TRAFFIC_ANALYSIS,
        TabLabel.PACKET_CAPTURE,
    ):
        assert label in TAB_ICONS
        assert isinstance(TAB_ICONS[label], str)
        assert len(TAB_ICONS[label]) == 1


def test_create_tab_icon(qapp):
    icon = create_tab_icon(TabLabel.DEVICE_SCAN)
    if is_icon_font_available():
        assert icon is not None
        pixmap = icon.pixmap(18, 18)
        assert not pixmap.isNull()
    else:
        assert icon is None


def test_set_button_icon(qapp):
    button = QPushButton("test")
    set_button_icon(button, Icon.CLEAR, size=14)
    if is_icon_font_available():
        assert not button.icon().isNull()
    # 即使图标字体不可用，也应保持按钮原状不抛出异常
    assert button.text() == "test"
