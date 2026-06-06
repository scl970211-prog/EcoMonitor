# -*- coding: utf-8 -*-
"""
全局样式定义
"""

MAIN_WINDOW = """
QMainWindow {
    background-color: #f5f5f5;
}
QTabWidget::pane {
    border: 1px solid #cccccc;
    background-color: white;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #e0e0e0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #2196F3;
    color: white;
}
QTabBar::tab:hover:!selected {
    background-color: #d0d0d0;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #cccccc;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #2196F3;
    color: white;
    border: none;
    padding: 6px 16px;
    border-radius: 4px;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #1976D2;
}
QPushButton:pressed {
    background-color: #0D47A1;
}
QPushButton:disabled {
    background-color: #cccccc;
    color: #666666;
}
QLineEdit, QComboBox, QSpinBox, QDateTimeEdit {
    padding: 5px;
    border: 1px solid #cccccc;
    border-radius: 3px;
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
    border-color: #2196F3;
}
QTextEdit {
    border: 1px solid #cccccc;
    border-radius: 3px;
    background-color: #fafafa;
}
QProgressBar {
    border: 1px solid #cccccc;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #4CAF50;
    border-radius: 3px;
}
QSplitter::handle {
    background-color: #cccccc;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}
QSplitter::handle:hover {
    background-color: #999999;
}
"""

LOG_TOOLBAR_BTN = """
QPushButton {
    background: #f3f3f3;
    border: 1px solid #ccc;
    border-radius: 4px;
    color: #444;
    font-size: 8pt;
    padding: 0 6px;
}
QPushButton:hover {
    background: #e8e8e8;
}
"""
