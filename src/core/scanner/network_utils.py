# -*- coding: utf-8 -*-
"""
网络工具模块 - IP计算、网段生成、本机网络信息获取
与原项目设备搜索功能对齐
"""

import socket
import ipaddress
import logging
import subprocess
import platform
import re
from typing import List, Optional, Iterator

logger = logging.getLogger(__name__)


def _is_virtual_interface(name: str) -> bool:
    """判断是否为虚拟网卡接口"""
    name_lower = name.lower()
    virtual_keywords = (
        "vethernet", "vmware", "virtualbox", "hyper-v",
        "tailscale", "zerotier", "tap-windows", "tun",
        "docker", "ppp", "nvidia", "vmnet", "wintun",
    )
    for keyword in virtual_keywords:
        if keyword in name_lower:
            return True
    return False


def _interface_priority(name: str) -> int:
    """
    接口优先级排序：数值越小越优先
    WLAN/WiFi > 以太网(Ethernet) > 其他物理接口 > 未知
    """
    name_lower = name.lower()
    if "wlan" in name_lower or "wi-fi" in name_lower:
        return 0
    if "ethernet" in name_lower or "以太网" in name:
        return 1
    if "本地连接" in name:
        return 2
    return 3


def get_local_networks() -> List[dict]:
    """
    获取本机所有有效的物理网络接口信息

    Returns:
        List[dict]: 网络接口列表，按优先级排序（WLAN优先）
    """
    networks = []

    try:
        import psutil

        stats = psutil.net_if_addrs()

        for interface_name, addrs in stats.items():
            # 跳过回环接口和虚拟网卡
            if interface_name.lower() in ("lo", "loopback", "本地连接*"):
                continue
            if _is_virtual_interface(interface_name):
                continue

            for addr in addrs:
                if addr.family == socket.AF_INET:  # IPv4
                    ip = addr.address
                    netmask = addr.netmask

                    # 跳过回环地址和自动配置地址
                    if ip.startswith("127.") or ip.startswith("169.254."):
                        continue

                    try:
                        # 计算网段
                        network = ipaddress.IPv4Network(
                            f"{ip}/{netmask}", strict=False
                        )
                        networks.append(
                            {
                                "interface": interface_name,
                                "ip": ip,
                                "netmask": netmask,
                                "network": str(network.network_address),
                                "cidr": f"{network.network_address}/{network.prefixlen}",
                                "broadcast": str(network.broadcast_address),
                                "priority": _interface_priority(interface_name),
                            }
                        )
                    except Exception as e:
                        logger.debug(f"解析网络接口失败 {interface_name}: {e}")
                        continue

    except Exception as e:
        logger.error(f"获取网络信息失败: {e}")

    # 按优先级排序
    networks.sort(key=lambda x: x["priority"])
    return networks


def parse_ip_range(range_str: str) -> Iterator[str]:
    """
    解析IP范围字符串，生成所有IP地址

    支持格式:
    - CIDR: 192.168.1.0/24
    - 范围: 192.168.1.1-192.168.1.100
    - 单个IP: 192.168.1.1

    Args:
        range_str: IP范围字符串

    Yields:
        str: IP地址字符串
    """
    range_str = range_str.strip()

    try:
        # 尝试CIDR格式
        if "/" in range_str:
            network = ipaddress.IPv4Network(range_str, strict=False)
            # 排除网络地址和广播地址
            for ip in network.hosts():
                yield str(ip)
            return

        # 尝试范围格式: 192.168.1.1-192.168.1.100
        if "-" in range_str:
            parts = range_str.split("-")
            if len(parts) == 2:
                start_ip = parts[0].strip()
                end_ip = parts[1].strip()

                start = ipaddress.IPv4Address(start_ip)
                end = ipaddress.IPv4Address(end_ip)

                current = int(start)
                end_int = int(end)

                while current <= end_int:
                    yield str(ipaddress.IPv4Address(current))
                    current += 1
            return

        # 单个IP
        ip = ipaddress.IPv4Address(range_str)
        yield str(ip)

    except Exception as e:
        logger.error(f"解析IP范围失败 '{range_str}': {e}")
        return


def get_ip_count(range_str: str) -> int:
    """
    计算IP范围内的地址数量

    Args:
        range_str: IP范围字符串

    Returns:
        int: IP地址数量
    """
    try:
        if "/" in range_str:
            network = ipaddress.IPv4Network(range_str, strict=False)
            num = network.num_addresses
            return max(0, num - 2) if num > 2 else num

        if "-" in range_str:
            parts = range_str.split("-")
            start = int(ipaddress.IPv4Address(parts[0].strip()))
            end = int(ipaddress.IPv4Address(parts[1].strip()))
            return end - start + 1

        return 1

    except Exception as e:
        logger.error(f"计算IP数量失败 '{range_str}': {e}")
        return 0


def get_default_gateway() -> Optional[str]:
    """
    获取默认网关IP

    Returns:
        str: 网关IP，失败返回None
    """
    try:
        system = platform.system().lower()

        if system == "windows":
            # Windows: 使用route命令获取默认网关
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # 解析输出找默认网关
            for line in result.stdout.split("\n"):
                if "0.0.0.0" in line and "Gateway" not in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        gateway = parts[2]
                        if gateway and gateway != "On-link":
                            return gateway

        elif system == "linux":
            # Linux: 使用ip route或route命令
            try:
                result = subprocess.run(
                    ["ip", "route"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.split("\n"):
                    if "default" in line:
                        match = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            return match.group(1)
            except Exception:
                pass

            # 备选：使用route命令
            result = subprocess.run(
                ["route", "-n"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("0.0.0.0") or line.startswith("default"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]

        elif system == "darwin":
            # macOS
            result = subprocess.run(
                ["netstat", "-rn"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("default"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]

        # 备选方法：使用网络接口的第一个IP推测网关
        networks = get_local_networks()
        if networks:
            network = ipaddress.IPv4Network(networks[0]["cidr"])
            return str(network.network_address + 1)

    except Exception as e:
        logger.error(f"获取默认网关失败: {e}")

    return None
