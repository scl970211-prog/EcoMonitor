# -*- coding: utf-8 -*-
"""
主题管理模块测试
"""

import pytest
from PyQt6.QtWidgets import QLabel

from src.gui.theme import (
    Theme,
    ThemeManager,
    get_theme_manager,
    log_badge_colors,
    rgba_color,
    set_status_style,
    set_text_style,
    status_color,
    task_status_color,
    task_status_surface,
    terminal_color,
    text_color,
)


@pytest.fixture(autouse=True)
def reset_theme_manager():
    """每个测试结束后恢复浅色主题，避免单例状态污染。"""
    yield
    get_theme_manager().set_theme(Theme.LIGHT)


def test_theme_enum_values():
    assert Theme.LIGHT.value == "light"
    assert Theme.DARK.value == "dark"
    assert Theme.SYSTEM.value == "system"


def test_theme_manager_singleton():
    manager_a = get_theme_manager()
    manager_b = ThemeManager()
    assert manager_a is manager_b


def test_set_theme_from_string():
    manager = get_theme_manager()
    manager.set_theme("dark")
    assert manager.current() == Theme.DARK
    manager.set_theme("light")
    assert manager.current() == Theme.LIGHT


def test_unknown_theme_fallback():
    manager = get_theme_manager()
    manager.set_theme("invalid")
    assert manager.current() == Theme.LIGHT


def test_light_colors():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    colors = manager.colors()
    assert colors.background == "#f5f5f5"
    assert colors.surface == "#ffffff"
    assert colors.text_primary == "#333333"
    assert colors.success_surface == "#e8f5e9"
    assert colors.tooltip_bg == "#333333"


def test_dark_colors():
    manager = get_theme_manager()
    manager.set_theme(Theme.DARK)
    colors = manager.colors()
    assert colors.background == "#1e1e1e"
    assert colors.surface == "#252526"
    assert colors.text_primary == "#e0e0e0"
    assert colors.success_surface == "#1b3a1b"
    assert colors.tooltip_bg == "#2d2d30"


def test_apply_to_app_with_qapp(qapp):
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    # 不应抛出异常
    manager.apply_to_app(qapp)


def test_status_color():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    assert status_color("online") == manager.colors().success
    assert status_color("offline") == manager.colors().text_secondary
    assert status_color("error") == manager.colors().error
    assert status_color("unknown") == manager.colors().text_primary


def test_text_color():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    assert text_color("primary") == manager.colors().text_primary
    assert text_color("secondary") == manager.colors().text_secondary
    assert text_color("disabled") == manager.colors().text_disabled


def test_log_badge_colors():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    bg, fg = log_badge_colors("INFO")
    assert bg == manager.colors().info_surface
    assert fg == manager.colors().info


def test_task_status_color_and_surface():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    assert task_status_color("completed") == manager.colors().success
    assert task_status_color("failed") == manager.colors().error
    assert task_status_surface("completed") == manager.colors().success_surface


def test_terminal_color():
    manager = get_theme_manager()
    manager.set_theme(Theme.LIGHT)
    assert terminal_color("info") == manager.colors().terminal_info
    assert terminal_color("error") == manager.colors().terminal_error


def test_rgba_color():
    assert rgba_color("#107c10", 128) == "rgba(16, 124, 16, 128)"


def test_set_status_style(qapp):
    label = QLabel()
    set_status_style(label, "success", size="10px", bold=True)
    style = label.styleSheet()
    assert "color" in style
    assert "font-weight: bold" in style


def test_set_text_style(qapp):
    label = QLabel()
    set_text_style(label, "secondary", size="12px")
    style = label.styleSheet()
    assert "color" in style
    assert "font-size: 12px" in style
