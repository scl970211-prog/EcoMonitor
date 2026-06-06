# -*- coding: utf-8 -*-
"""
设备扫描模块
提供高速多线程网络设备发现功能
"""

# 基础组件
from .device_info import Device, DeviceInfoResolver, get_resolver
from .network_utils import (
    get_local_networks,
    parse_ip_range,
    get_ip_count,
    get_default_gateway,
)

# 扫描器
from .fast_scanner import FastScanner, OptimizedScannerManager
from .enhanced_scanner import (
    EnhancedScanner,
    ARPScanner,
    ICMPScanner,
    TCPScanner,
    ScanResult,
    create_scanner,
)
from .onvif_scanner import (
    OnvifScanner,
    OnvifDeviceInfo,
    discover_onvif_devices,
)

# 兼容性别名
ScannerManager = OptimizedScannerManager

__all__ = [
    # 基础组件
    'Device',
    'DeviceInfoResolver',
    'get_resolver',
    'get_local_networks',
    'parse_ip_range',
    'get_ip_count',
    'get_default_gateway',
    # 扫描器
    'FastScanner',
    'OptimizedScannerManager',
    'ScannerManager',  # 兼容性别名
    'EnhancedScanner',
    'ARPScanner',
    'ICMPScanner',
    'TCPScanner',
    'ScanResult',
    'create_scanner',
    # ONVIF
    'OnvifScanner',
    'OnvifDeviceInfo',
    'discover_onvif_devices',
]
