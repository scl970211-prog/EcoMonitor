# -*- coding: utf-8 -*-
"""
扫描器设备信息解析单元测试
"""

import pytest
from src.core.scanner.device_info import DeviceInfoResolver, Device


@pytest.fixture
def resolver():
    """禁用联网查询的解析器。"""
    return DeviceInfoResolver(enable_online_lookup=False)


class TestDeviceInfoResolver:
    """DeviceInfoResolver 测试。"""

    def test_get_vendor_known_hikvision(self, resolver):
        """应正确识别本地 OUI 数据库中的海康 MAC。"""
        assert resolver.get_vendor("00:1A:79:01:02:03", try_online=False) == "Hikvision"
        assert resolver.get_vendor("18:68:CB:FF:FF:FF", try_online=False) == "Hikvision"

    def test_get_vendor_known_dahua(self, resolver):
        """应正确识别本地 OUI 数据库中的大华 MAC。"""
        assert resolver.get_vendor("4C:11:BF:01:02:03", try_online=False) == "Dahua"

    def test_get_vendor_unknown_mac(self, resolver):
        """未知 MAC 应返回空字符串。"""
        assert resolver.get_vendor("00:00:00:00:00:00", try_online=False) == ""
        assert resolver.get_vendor("FF:FF:FF:FF:FF:FF", try_online=False) == ""
        assert resolver.get_vendor("AB:CD:EF:12:34:56", try_online=False) == ""

    def test_get_vendor_different_formats(self, resolver):
        """支持冒号和横线两种分隔符。"""
        assert resolver.get_vendor("00-1A-79-01-02-03", try_online=False) == "Hikvision"
        assert resolver.get_vendor("00:1A:79:01:02:03", try_online=False) == "Hikvision"

    def test_normalize_mac(self, resolver):
        """MAC 标准化应正确。"""
        assert resolver.normalize_mac("001a79010203") == "00:1A:79:01:02:03"
        assert resolver.normalize_mac("00-1a-79-01-02-03") == "00:1A:79:01:02:03"
        assert resolver.normalize_mac("00:1A:79:01:02:03") == "00:1A:79:01:02:03"
        assert resolver.normalize_mac("") == ""
        assert resolver.normalize_mac("invalid") == ""
        assert resolver.normalize_mac("00:1A:79:01:02") == ""

    def test_set_online_lookup(self, resolver):
        """应能切换联网查询开关。"""
        assert resolver.enable_online_lookup is False
        resolver.set_online_lookup(True)
        assert resolver.enable_online_lookup is True


class TestDevice:
    """Device 数据类测试。"""

    def test_to_dict(self):
        """to_dict 应包含所有字段。"""
        device = Device("192.168.1.10")
        device.mac = "00:1A:79:01:02:03"
        device.vendor = "Hikvision"
        device.is_online = True
        device.open_ports = [8000, 554]

        d = device.to_dict()
        assert d["ip"] == "192.168.1.10"
        assert d["mac"] == "00:1A:79:01:02:03"
        assert d["vendor"] == "Hikvision"
        assert d["is_online"] is True
        assert d["open_ports"] == [8000, 554]

    def test_get_display_vendor_mac_priority(self):
        """有 MAC 厂商时应优先显示。"""
        device = Device("192.168.1.10")
        device.vendor = "Hikvision"
        assert device.get_display_vendor() == "Hikvision"

    def test_get_display_vendor_random_mac_fingerprint(self):
        """移动设备 + 高置信度指纹应优先显示指纹。"""
        device = Device("192.168.1.10")
        device.device_type = "Phone"
        device.vendor = "RandomVendor"
        device.fingerprint_vendor = "Apple"
        device.fingerprint_confidence = 80
        assert device.get_display_vendor() == "Apple(?)"

    def test_get_display_vendor_from_hostname(self):
        """无 MAC 厂商时，可从主机名推断。"""
        device = Device("192.168.1.10")
        device.hostname = "iPhone-ABC"
        assert device.get_display_vendor() == "Apple(?)"

    def test_get_display_type_explicit(self):
        """显式设备类型优先。"""
        device = Device("192.168.1.10")
        device.device_type = "Camera"
        assert device.get_display_type() == "Camera"

    def test_get_display_type_infer_from_ports(self):
        """未设置设备类型时，应根据端口推断。"""
        device = Device("192.168.1.10")
        device.open_ports = [8000]
        assert device.get_display_type() == "Camera(?)"

    def test_get_display_type_windows(self):
        """开放 SMB 端口时应推断为 Windows。"""
        device = Device("192.168.1.10")
        device.open_ports = [135, 445]
        assert device.get_display_type() == "Windows(?)"
