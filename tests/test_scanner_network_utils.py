# -*- coding: utf-8 -*-
"""
扫描器网络工具单元测试
"""

import pytest
from src.core.scanner.network_utils import (
    _is_virtual_interface,
    _interface_priority,
    parse_ip_range,
    get_ip_count,
)


class TestInterfaceClassification:
    """网卡接口分类测试。"""

    def test_is_virtual_interface(self):
        """应正确识别常见虚拟网卡。"""
        assert _is_virtual_interface("VMware Network Adapter") is True
        assert _is_virtual_interface("vEthernet (Default Switch)") is True
        assert _is_virtual_interface("DockerNAT") is True
        assert _is_virtual_interface("VirtualBox Host-Only Ethernet Adapter") is True
        assert _is_virtual_interface("TAP-Windows Adapter V9") is True
        assert _is_virtual_interface("以太网") is False
        assert _is_virtual_interface("WLAN") is False

    def test_interface_priority(self):
        """WLAN 优先级最高，未知接口最低。"""
        assert _interface_priority("WLAN") == 0
        assert _interface_priority("Wi-Fi") == 0
        assert _interface_priority("Ethernet") == 1
        assert _interface_priority("以太网") == 1
        assert _interface_priority("本地连接") == 2
        assert _interface_priority("其他接口") == 3


class TestParseIPRange:
    """IP 范围解析测试。"""

    def test_parse_single_ip(self):
        """单个 IP 应被正确解析。"""
        result = list(parse_ip_range("192.168.1.10"))
        assert result == ["192.168.1.10"]

    def test_parse_cidr(self):
        """CIDR 应解析为可用主机地址。"""
        result = list(parse_ip_range("192.168.1.0/30"))
        # /30 可用主机为 .1, .2
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_parse_range(self):
        """范围格式应被正确解析。"""
        result = list(parse_ip_range("192.168.1.1-192.168.1.3"))
        assert result == ["192.168.1.1", "192.168.1.2", "192.168.1.3"]

    def test_parse_range_with_spaces(self):
        """范围中的空格应被正确处理。"""
        result = list(parse_ip_range("192.168.1.1 - 192.168.1.2"))
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_parse_invalid_range(self):
        """无效范围应返回空列表，不抛出异常。"""
        result = list(parse_ip_range("not-an-ip"))
        assert result == []


class TestGetIPCount:
    """IP 数量计算测试。"""

    def test_get_ip_count_single(self):
        assert get_ip_count("192.168.1.1") == 1

    def test_get_ip_count_cidr(self):
        assert get_ip_count("192.168.1.0/30") == 2
        assert get_ip_count("192.168.1.0/24") == 254

    def test_get_ip_count_range(self):
        assert get_ip_count("192.168.1.1-192.168.1.10") == 10

    def test_get_ip_count_invalid(self):
        assert get_ip_count("invalid") == 0
