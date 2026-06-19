# -*- coding: utf-8 -*-
"""
核心常量模块

集中管理网络端口、扫描、设备类型、超时等核心数值，
减少各模块中的魔数与重复定义。
"""

from typing import FrozenSet


# ==================== 设备连接 ====================
DEFAULT_SDK_PORT = 8000
DEFAULT_HTTP_PORT = 80
DEFAULT_DAHUA_PORT = 37777
DEFAULT_USERNAME = "admin"
DEFAULT_RECONNECT_INTERVAL = 5  # 秒
DEFAULT_HEARTBEAT_INTERVAL = 0  # 0 表示关闭心跳
DEFAULT_DOWNLOAD_TIMEOUT = 3600  # 秒
DEFAULT_DOWNLOAD_STALL_TIMEOUT = 60  # 秒


# ==================== 扫描 ====================
DEFAULT_SCAN_TIMEOUT = 1.0  # 秒
MAX_SCAN_IP_COUNT = 65536
SCAN_BATCH_SIZE = 50
DEFAULT_ICMP_COUNT = 10
DEFAULT_ICMP_TIMEOUT = 3  # 秒

# 常见设备特征端口（监控/网络设备）
COMMON_TCP_PORTS: tuple = (
    80, 443, 554, 8000, 8080,  # 监控/Web
    22, 23, 21,                # 远程管理
    3389, 445, 139, 135,       # Windows
    62078,                     # iOS
    5555,                      # Android ADB
    1900, 5353,                # UPnP/mDNS
    8443,                      # HTTPS 备用
)

# 快速指纹识别端口
FINGERPRINT_PORTS: tuple = (62078, 5555, 554, 8000, 80, 445, 3389)

# 知名监控厂商关键词
CAMERA_VENDOR_KEYWORDS: FrozenSet[str] = frozenset(
    ["hikvision", "dahua", "uniview", "tiandy", "jovision", "海康", "大华", "宇视", "天地伟业", "中维"]
)

# 监控设备特征端口
CAMERA_FEATURE_PORTS: FrozenSet[int] = frozenset([554, 8000, 8080, 37777])


# ==================== 设备类型映射 ====================
DEVICE_TYPE_MAP = {
    1: "DVR",
    2: "DVS",
    3: "IPC",
    4: "NVR",
    5: "NVR",
    6: "NVR",
    7: "NVR",
    8: "NVR",
    9: "NVR",
    10: "NVR",
    90: "NVR",
}


# ==================== 下载 ====================
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2
DEFAULT_SPLIT_SIZE_GB = 4.0
TEMP_FILE_RESERVE_MB = 500  # 临时目录保留空间
OUTPUT_FILE_RESERVE_MB = 100  # 输出目录保留空间
DEFAULT_MAX_TEMP_SIZE_GB = 2.0


# ==================== 网络测速 ====================
SPEEDTEST_DOWNLOAD_DURATION = 8  # 秒
SPEEDTEST_UPLOAD_DURATION = 6  # 秒
SPEEDTEST_LATENCY_ATTEMPTS = 1
SPEEDTEST_WORKER_COUNT = 4


# ==================== MTU 测试 ====================
MTU_OVERHEAD = 28
MTU_MAX_PAYLOAD = 1472
MTU_COMMON_VALUES = {
    1500: "标准以太网 (1500)",
    1492: "PPPoE (1492)",
    1480: "IPv6 over IPv4 隧道 (1480)",
    1400: "VPN/隧道",
    1280: "IPv6 最小 (1280)",
}


# ==================== DSCP 名称映射 ====================
DSCP_NAMES = {
    0: "CS0 / BE (默认)",
    8: "CS1",
    10: "AF11",
    12: "AF12",
    14: "AF13",
    16: "CS2",
    18: "AF21",
    20: "AF22",
    22: "AF23",
    24: "CS3",
    26: "AF31",
    28: "AF32",
    30: "AF33",
    32: "CS4",
    34: "AF41",
    36: "AF42",
    38: "AF43",
    40: "CS5",
    44: "VA (语音准入)",
    46: "EF (加速转发)",
    48: "CS6",
    56: "CS7",
}


# ==================== 状态颜色（语义色） ====================
class StatusColor:
    """通用状态颜色，与 src/gui/constants.py 中的 UI 色值保持一致语义。"""

    SUCCESS = "#107c10"
    WARNING = "#d67f00"
    ERROR = "#c42b1c"
    INFO = "#0078d4"
    PENDING = "#666666"
    DISABLED = "#999999"
    ONLINE = "#4caf50"
    OFFLINE = "#999999"
    RECONNECTING = "#ff9800"
