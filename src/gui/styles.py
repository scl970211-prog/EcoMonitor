# -*- coding: utf-8 -*-
"""
全局样式定义

本文件作为设计系统的 QSS 入口，统一维护颜色、字号、间距、边框等视觉 token。
各标签页应尽量减少内联 setStyleSheet，优先通过 objectName 或类选择器在此集中管理。
"""

from .constants import FontSize, Size
from .theme import ThemeColors, get_theme_manager


# ==================== 主窗口全局样式 ====================
def _build_main_window(tc: ThemeColors) -> str:
    BORDER_RADIUS = Size.BORDER_RADIUS
    return f"""
QMainWindow {{
    background-color: {tc.background};
}}

QTabWidget::pane {{
    border: 1px solid {tc.border};
    background-color: {tc.surface};
    border-radius: {BORDER_RADIUS};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {tc.panel};
    color: {tc.text_primary};
    padding: 8px 16px;
    min-width: 90px;
    margin-right: 2px;
    border-top-left-radius: {BORDER_RADIUS};
    border-top-right-radius: {BORDER_RADIUS};
    border: 1px solid transparent;
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: {tc.surface};
    color: {tc.primary};
    border: 1px solid {tc.border};
    border-bottom: 1px solid {tc.surface};
    font-weight: bold;
}}

QTabBar::tab:hover:!selected {{
    background-color: {tc.border};
}}

QGroupBox {{
    font-weight: bold;
    color: {tc.text_primary};
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    margin-top: 10px;
    padding-top: 10px;
    background-color: {tc.surface};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

QPushButton {{
    background-color: {tc.primary};
    color: white;
    border: none;
    padding: 6px 16px;
    border-radius: {BORDER_RADIUS};
    min-width: {Size.BTN_MIN_WIDTH}px;
    min-height: {Size.BTN_MIN_HEIGHT}px;
}}

QPushButton:hover {{
    background-color: {tc.primary_hover};
}}

QPushButton:pressed {{
    background-color: {tc.primary_pressed};
}}

QPushButton:disabled {{
    background-color: {tc.text_disabled};
    color: {tc.text_secondary};
}}

QPushButton#danger {{
    background-color: {tc.error};
}}

QPushButton#danger:hover {{
    background-color: {tc.error};
}}

QPushButton#secondary {{
    background-color: {tc.panel};
    color: {tc.text_primary};
    border: 1px solid {tc.border};
}}

QPushButton#secondary:hover {{
    background-color: {tc.border};
}}

QLineEdit, QComboBox, QSpinBox, QDateTimeEdit {{
    padding: 6px 10px;
    border: 1px solid {tc.border};
    border-radius: 3px;
    min-height: {Size.INPUT_MIN_HEIGHT}px;
    background-color: {tc.surface};
}}

QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {{
    border-color: {tc.primary};
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateTimeEdit:disabled {{
    background-color: {tc.background};
    color: {tc.text_disabled};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 20px;
}}

QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 10px;
    height: 10px;
}}

QTextEdit {{
    border: 1px solid {tc.border};
    border-radius: 3px;
    background-color: {tc.surface};
    color: {tc.text_primary};
}}

QTextEdit#terminal {{
    background-color: {tc.terminal_bg};
    color: {tc.terminal_fg};
    border: 1px solid {tc.border};
}}

QProgressBar {{
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    text-align: center;
    background-color: {tc.panel};
}}

QProgressBar::chunk {{
    background-color: {tc.success};
    border-radius: 3px;
}}

QProgressBar::chunk#warning {{
    background-color: {tc.warning};
}}

QProgressBar::chunk#error {{
    background-color: {tc.error};
}}

QSplitter::handle {{
    background-color: {tc.border};
}}

QSplitter::handle:horizontal {{
    width: {Size.SPLITTER_HANDLE_SIZE}px;
}}

QSplitter::handle:vertical {{
    height: {Size.SPLITTER_HANDLE_SIZE}px;
}}

QSplitter::handle:hover {{
    background-color: {tc.text_disabled};
}}

QTableWidget {{
    background-color: {tc.surface};
    alternate-background-color: {tc.panel};
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    gridline-color: {tc.border};
}}

QTableWidget::item:selected {{
    background-color: {tc.panel};
    color: {tc.text_primary};
}}

QHeaderView::section {{
    background-color: {tc.panel};
    color: {tc.text_primary};
    padding: 6px;
    border: 1px solid {tc.border};
    border-left: none;
    font-weight: bold;
}}

QHeaderView::section:first {{
    border-left: 1px solid {tc.border};
}}

QStatusBar {{
    background-color: {tc.panel};
    color: {tc.text_secondary};
    border-top: 1px solid {tc.border};
}}

QMenu {{
    background-color: {tc.surface};
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px;
    border-radius: 3px;
}}

QMenu::item:selected {{
    background-color: {tc.panel};
}}

QToolTip {{
    background-color: {tc.tooltip_bg};
    color: {tc.tooltip_fg};
    border: none;
    border-radius: 3px;
    padding: 4px 8px;
}}
"""


# ==================== 主窗口具名控件（替代内联 setStyleSheet） ====================
def _build_main_window_named(tc: ThemeColors) -> str:
    BORDER_RADIUS = Size.BORDER_RADIUS
    return f"""
QLabel#footerLabel {{
    color: {tc.text_secondary};
    font-size: 9pt;
}}

QWidget#logPanel {{
    background-color: {tc.surface};
    border-top: 1px solid {tc.border};
}}

QWidget#logToolbar {{
    background-color: {tc.panel};
    border-bottom: 1px solid {tc.border};
}}

QLabel#logTitle {{
    font-weight: 600;
    font-size: 8pt;
    color: {tc.text_primary};
}}

QComboBox#logLevelCombo {{
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    font-size: 8pt;
    padding: 0 4px;
    background-color: {tc.surface};
    min-height: 22px;
}}

QLineEdit#logSearchInput {{
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    font-size: 8pt;
    padding: 0 6px;
    background-color: {tc.surface};
    min-height: 22px;
}}

QPushButton#logToolbarBtn {{
    background: {tc.panel};
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
    color: {tc.text_primary};
    font-size: {FontSize.XS};
    padding: 0 6px;
    min-height: 22px;
}}

QPushButton#logToolbarBtn:hover {{
    background: {tc.border};
}}

QPushButton#largePrimaryBtn {{
    font-size: 14px;
    padding: 10px 30px;
}}

QPushButton#largeSecondaryBtn {{
    font-size: 13px;
    padding: 10px 24px;
}}

QPushButton#smallBtn {{
    padding: 2px 10px;
    font-size: 9pt;
    min-height: 28px;
}}

QPushButton#smallBtn:disabled {{
    padding: 2px 10px;
    min-height: 28px;
}}

QLabel#autoLoginTitle {{
    font-size: 14px;
    font-weight: bold;
    color: {tc.text_primary};
}}

QLabel#autoLoginInfo {{
    font-size: 12px;
    color: {tc.text_secondary};
}}

QLabel#autoLoginCountdown {{
    font-size: 11px;
    color: {tc.text_disabled};
}}

QPushButton#autoLoginCancel {{
    background-color: {tc.panel};
    color: {tc.text_primary};
    border: 1px solid {tc.border};
}}
"""


# ==================== 视频窗格样式 ====================
def _build_video_widget(tc: ThemeColors) -> str:
    BORDER_RADIUS = Size.BORDER_RADIUS
    return f"""
VideoWidget {{
    background-color: {tc.video_bg};
    border: 1px solid {tc.border};
    border-radius: {BORDER_RADIUS};
}}

VideoWidget:focus,
VideoWidget#selected {{
    border: 2px solid {tc.primary};
}}

VideoWidget #videoContainer {{
    background-color: {tc.video_container_bg};
    border: 1px solid {tc.border};
}}
"""


# ==================== 测速页专用样式 ====================
def _build_speedtest(tc: ThemeColors) -> str:
    return f"""
QLabel#speedPageTitle {{
    font-size: 16px;
    font-weight: bold;
    color: {tc.text_primary};
}}

QLabel#speedStatusLabel {{
    color: {tc.text_secondary};
    font-size: 12px;
}}

QProgressBar#speedProgressBar {{
    border: none;
    border-radius: 3px;
    background-color: {tc.panel};
    max-height: 6px;
    min-height: 6px;
}}

QProgressBar#speedProgressBar::chunk {{
    background-color: {tc.primary};
    border-radius: 3px;
}}

QWidget#speedGauge {{
    background-color: transparent;
}}

QWidget#speedChart {{
    background-color: transparent;
}}

QFrame#speedCard {{
    background-color: {tc.surface};
    border: 1px solid {tc.border};
    border-radius: 10px;
}}

QLabel#speedCardTitle {{
    color: {tc.text_secondary};
    font-size: 12px;
}}

QLabel#speedCardValue {{
    color: {tc.text_primary};
    font-size: 24px;
    font-weight: bold;
}}

QLabel#speedCardValueDownload {{
    color: {tc.primary};
    font-size: 24px;
    font-weight: bold;
}}

QLabel#speedCardValueUpload {{
    color: {tc.success};
    font-size: 24px;
    font-weight: bold;
}}

QLabel#speedCardValuePing {{
    color: {tc.warning};
    font-size: 24px;
    font-weight: bold;
}}

QLabel#speedCardUnit {{
    color: {tc.text_secondary};
    font-size: 11px;
}}

QPushButton#speedStartBtn {{
    font-size: 14px;
    padding: 10px 32px;
    min-width: 140px;
}}

QPushButton#speedStopBtn {{
    background-color: {tc.error};
    color: white;
    font-size: 14px;
    padding: 10px 24px;
}}

QPushButton#speedStopBtn:hover {{
    background-color: {tc.error};
}}

QPushButton#speedStopBtn:pressed {{
    background-color: {tc.error};
}}

QTableWidget#speedHistoryTable {{
    background-color: {tc.surface};
    alternate-background-color: {tc.panel};
    border: 1px solid {tc.border};
    border-radius: 6px;
}}

QTextEdit#speedLogPanel {{
    background-color: {tc.surface};
    border: 1px solid {tc.border};
    border-radius: 6px;
    color: {tc.text_primary};
}}

QGroupBox#speedResultGroup,
QGroupBox#speedHistoryGroup {{
    background-color: {tc.surface};
    border: 1px solid {tc.border};
    border-radius: 10px;
    color: {tc.text_primary};
}}

QLabel#speedValueTitle,
QLabel#speedValueUnit {{
    color: {tc.text_secondary};
    font-size: 12px;
}}

QFrame#speedSeparator {{
    color: {tc.border};
}}
"""


# ==================== 合并后的全局样式（供主窗口使用） ====================
def get_global_stylesheet(theme_colors: ThemeColors = None) -> str:
    """返回完整的全局样式表。

    Args:
        theme_colors: 可选的 ThemeColors 实例；默认使用 ThemeManager 当前主题。
    """
    if theme_colors is None:
        theme_colors = get_theme_manager().colors()
    return "\n".join([
        _build_main_window(theme_colors),
        _build_main_window_named(theme_colors),
        _build_video_widget(theme_colors),
        _build_speedtest(theme_colors),
    ])
