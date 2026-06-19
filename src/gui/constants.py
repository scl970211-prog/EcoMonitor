# -*- coding: utf-8 -*-
"""
GUI 常量模块

集中管理颜色、字号、间距、布局映射等 UI 相关常量，
为统一视觉风格和后续主题切换提供基础。
"""

from typing import Dict, List, Tuple


# ==================== 设计系统 - 颜色 ====================
class Color:
    """核心调色板"""

    # 主色
    PRIMARY = "#2196F3"
    PRIMARY_HOVER = "#1976D2"
    PRIMARY_PRESSED = "#0D47A1"

    # 语义色
    SUCCESS = "#107c10"
    SUCCESS_LIGHT = "#4CAF50"
    WARNING = "#d67f00"
    WARNING_LIGHT = "#ff9800"
    ERROR = "#c42b1c"
    ERROR_LIGHT = "#f44336"
    INFO = "#0078d4"
    INFO_LIGHT = "#569cd6"

    # 中性色
    WHITE = "#ffffff"
    GRAY_50 = "#fafafa"
    GRAY_100 = "#f5f5f5"
    GRAY_200 = "#f0f0f0"
    GRAY_300 = "#e0e0e0"
    GRAY_400 = "#cccccc"
    GRAY_500 = "#999999"
    GRAY_600 = "#666666"
    GRAY_700 = "#555555"
    GRAY_800 = "#444444"
    GRAY_900 = "#333333"
    BLACK = "#1a1a1a"

    # 背景/表面
    BACKGROUND = "#f5f5f5"
    SURFACE = "#ffffff"
    PANEL = "#f9f9f9"
    VIDEO_BG = "#1a1a1a"
    VIDEO_CONTAINER_BG = "#0d0d0d"
    TERMINAL_BG = "#1e1e1e"
    TERMINAL_FG = "#d4d4d4"

    # 边框
    BORDER = "#cccccc"
    BORDER_DARK = "#333333"
    BORDER_VIDEO = "#333333"
    BORDER_VIDEO_ACTIVE = "#0078d4"


# ==================== 设计系统 - 字号 ====================
class FontSize:
    """字号体系（pt）"""

    XS = "8pt"
    SM = "9pt"
    BASE = "10pt"
    MD = "11px"  # 部分控件使用像素
    LG = "12px"
    XL = "14px"
    XXL = "20px"
    DISPLAY = "34px"


# ==================== 设计系统 - 间距/尺寸 ====================
class Size:
    """通用尺寸"""

    BORDER_RADIUS = "4px"
    BORDER_RADIUS_LG = "10px"
    BTN_MIN_WIDTH = 80
    BTN_MIN_HEIGHT = 32
    INPUT_MIN_HEIGHT = 32
    SMALL_BTN_HEIGHT = 24
    SMALL_BTN_WIDTH = 72
    LOG_PANEL_MIN_HEIGHT = 100
    SPLITTER_HANDLE_SIZE = 4


# ==================== 布局映射 ====================
LAYOUT_COMBO_INDEX_MAP: Dict[int, int] = {1: 0, 2: 1, 3: 2, 4: 3, 8: 4}
LAYOUT_INDEX_COMBO_MAP: Dict[int, int] = {0: 1, 1: 2, 2: 3, 3: 4, 4: 8}
LAYOUT_LABEL_MAP: Dict[int, str] = {1: "1分屏", 2: "2分屏", 3: "3分屏", 4: "4分屏", 8: "8分屏"}


# ==================== 表格默认列宽比例 ====================
class TableColumnDefaults:
    """表格默认列宽配置"""

    DEVICE_SCAN: List[float] = [0.15, 0.20, 0.25, 0.12, 0.18, 0.10]
    DEVICE_SCAN_MIN_WIDTH = 50


# ==================== 日志级别映射 ====================
LOG_LEVEL_MAP = {"全部": "ALL", "信息": "INFO", "警告": "WARN", "错误": "ERROR"}


# ==================== 标签页标题（无 Emoji，稳定跨平台） ====================
class TabLabel:
    """主窗口标签页标题，使用文字标签替代 Emoji，避免不同系统字体差异。"""

    DEVICE_SCAN = "设备搜索"
    CONNECTION = "设备连接"
    PREVIEW = "视频预览"
    DOWNLOAD = "批量下载"
    DOWNLOAD_MANAGER = "下载管理"
    TERMINAL = "终端调试"
    NETWORK_QUALITY = "网络质量"
    SPEEDTEST = "网络测速"
    IP_CONFLICT = "IP冲突检测"
    TRAFFIC_ANALYSIS = "流量分析"
    PACKET_CAPTURE = "抓包分析"


# ==================== 状态颜色别名 ====================
class StatusColor:
    """语义化状态颜色别名，便于在代码中直观表达状态含义。"""

    ONLINE = Color.SUCCESS
    OFFLINE = Color.GRAY_500
    ERROR = Color.ERROR
    WARNING = Color.WARNING
    SUCCESS = Color.SUCCESS_LIGHT
    INFO = Color.PRIMARY
