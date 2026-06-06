# -*- coding: utf-8 -*-
"""
ONVIF WS-Discovery 扫描器

零依赖实现，仅使用 Python 标准库。
发送 UDP 多播 Probe 到 239.255.255.250:3702，
接收设备单播响应并解析。
"""

import logging
import socket
import struct
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# WS-Discovery 常量
WS_DISCOVERY_ADDR = "239.255.255.250"
WS_DISCOVERY_PORT = 3702
PROBE_TIMEOUT = 2.0  # 秒

# XML 命名空间
NS_SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
NS_ADDRESSING = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
NS_DISCOVERY = "http://schemas.xmlsoap.org/ws/2005/04/discovery"


@dataclass
class OnvifDeviceInfo:
    """ONVIF WS-Discovery 发现的设备信息"""
    ip: str
    port: int
    xaddrs: List[str] = field(default_factory=list)
    epr: str = ""
    types: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    name: str = ""
    hardware: str = ""
    location: str = ""

    def get_display_name(self) -> str:
        if self.name:
            return self.name
        if self.hardware:
            return self.hardware
        return f"ONVIF 设备 ({self.ip})"

    def get_vendor_hint(self) -> str:
        for scope in self.scopes:
            lower = scope.lower()
            if "manufacturer" in lower or "name/" in lower:
                parts = scope.split("/")
                if parts:
                    return parts[-1]
        # 从 types 或常见型号猜测
        for t in self.types:
            if "hikvision" in t.lower():
                return "Hikvision"
            if "dahua" in t.lower():
                return "Dahua"
        return ""


class OnvifScanner:
    """
    ONVIF WS-Discovery 扫描器

    用法:
        scanner = OnvifScanner(timeout=2.0)
        devices = scanner.discover()
        for d in devices:
            print(d.ip, d.get_display_name())
    """

    def __init__(self, timeout: float = PROBE_TIMEOUT):
        self.timeout = timeout

    def _build_probe_message(self, message_id: str) -> bytes:
        """构建 WS-Discovery Probe SOAP 消息"""
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap-env:Envelope xmlns:soap-env="http://www.w3.org/2003/05/soap-envelope"
                   xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                   xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
   <soap-env:Header>
      <a:Action mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>
      <a:MessageID>uuid:{message_id}</a:MessageID>
      <a:ReplyTo>
         <a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address>
      </a:ReplyTo>
      <a:To mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>
   </soap-env:Header>
   <soap-env:Body>
      <d:Probe>
         <d:Types>dn:NetworkVideoTransmitter</d:Types>
      </d:Probe>
   </soap-env:Body>
</soap-env:Envelope>'''
        return xml.encode('utf-8')

    def _parse_probe_match(self, data: bytes, addr: tuple) -> Optional[OnvifDeviceInfo]:
        """解析 ProbeMatch 响应"""
        try:
            root = ET.fromstring(data.decode('utf-8', errors='ignore'))
        except ET.ParseError:
            return None

        # 注册命名空间（处理带前缀的标签）
        ns_map = {
            'soap-env': NS_SOAP_ENV,
            'a': NS_ADDRESSING,
            'd': NS_DISCOVERY,
        }

        body = root.find('soap-env:Body', ns_map)
        if body is None:
            body = root.find(f'{{{NS_SOAP_ENV}}}Body')
        if body is None:
            return None

        # 有些设备返回 ProbeMatches 包装，有些直接返回 ResolveMatches
        probe_matches = body.find('d:ProbeMatches', ns_map)
        if probe_matches is None:
            probe_matches = body.find(f'{{{NS_DISCOVERY}}}ProbeMatches')
        if probe_matches is None:
            return None

        probe_match = probe_matches.find('d:ProbeMatch', ns_map)
        if probe_match is None:
            probe_match = probe_matches.find(f'{{{NS_DISCOVERY}}}ProbeMatch')
        if probe_match is None:
            return None

        def _find_text(elem, tag_local: str, ns_uri: str) -> str:
            """优先用前缀查找，fallback 到完整命名空间"""
            prefix = None
            for p, u in ns_map.items():
                if u == ns_uri:
                    prefix = p
                    break
            if prefix:
                child = elem.find(f'{prefix}:{tag_local}', ns_map)
                if child is not None and child.text:
                    return child.text
            child = elem.find(f'{{{ns_uri}}}{tag_local}')
            if child is not None and child.text:
                return child.text
            return ""

        def _find_all_text(elem, tag_local: str, ns_uri: str) -> List[str]:
            prefix = None
            for p, u in ns_map.items():
                if u == ns_uri:
                    prefix = p
                    break
            results = []
            if prefix:
                for child in elem.findall(f'{prefix}:{tag_local}', ns_map):
                    if child.text:
                        results.append(child.text)
            if not results:
                for child in elem.findall(f'{{{ns_uri}}}{tag_local}'):
                    if child.text:
                        results.append(child.text)
            return results

        epr = _find_text(probe_match, "EndpointReference", NS_ADDRESSING)
        # 有时 EndpointReference 是嵌套结构
        if not epr:
            epr_elem = probe_match.find('a:EndpointReference', ns_map)
            if epr_elem is not None:
                addr_elem = epr_elem.find('a:Address', ns_map)
                if addr_elem is not None and addr_elem.text:
                    epr = addr_elem.text
                else:
                    addr_elem = epr_elem.find(f'{{{NS_ADDRESSING}}}Address')
                    if addr_elem is not None and addr_elem.text:
                        epr = addr_elem.text

        types = _find_all_text(probe_match, "Types", NS_DISCOVERY)
        scopes = _find_all_text(probe_match, "Scopes", NS_DISCOVERY)
        xaddrs = _find_all_text(probe_match, "XAddrs", NS_DISCOVERY)

        # 从 XAddrs 提取 IP 和端口
        ip = addr[0]
        port = 80
        if xaddrs:
            import re
            m = re.search(r'http://([^/]+)/', xaddrs[0])
            if m:
                host_port = m.group(1)
                if ':' in host_port:
                    ip, p = host_port.rsplit(':', 1)
                    try:
                        port = int(p)
                    except ValueError:
                        pass
                else:
                    ip = host_port

        # 从 scopes 解析友好字段
        name = ""
        hardware = ""
        location = ""
        for scope in scopes:
            # scope 格式通常为: onvif://www.onvif.org/name/IPC_xxx
            if "name/" in scope.lower():
                name = scope.split("/")[-1]
            elif "hardware/" in scope.lower():
                hardware = scope.split("/")[-1]
            elif "location/" in scope.lower():
                location = scope.split("/")[-1]

        return OnvifDeviceInfo(
            ip=ip,
            port=port,
            xaddrs=xaddrs,
            epr=epr,
            types=types,
            scopes=scopes,
            name=name,
            hardware=hardware,
            location=location,
        )

    def discover(self) -> List[OnvifDeviceInfo]:
        """
        执行 ONVIF WS-Discovery 扫描

        Returns:
            发现的 ONVIF 设备列表
        """
        devices: Dict[str, OnvifDeviceInfo] = {}
        message_id = str(uuid.uuid4())
        probe_msg = self._build_probe_message(message_id)

        # 创建 UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Windows 需要设置多播 TTL
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', 1))

        try:
            # 绑定到任意地址的 3702 端口（用于接收单播响应）
            try:
                sock.bind(("", WS_DISCOVERY_PORT))
            except OSError as e:
                # 端口可能被占用（如本机有其他 ONVIF 工具），尝试随机端口
                logger.warning(f"绑定 {WS_DISCOVERY_PORT} 失败: {e}，尝试随机端口")
                sock.bind(("", 0))

            # 设置接收超时
            sock.settimeout(self.timeout)

            # 发送 Probe 多播
            logger.info(f"发送 ONVIF Probe 到 {WS_DISCOVERY_ADDR}:{WS_DISCOVERY_PORT}")
            try:
                sock.sendto(probe_msg, (WS_DISCOVERY_ADDR, WS_DISCOVERY_PORT))
            except OSError as e:
                logger.error(f"发送 Probe 失败: {e}")
                return list(devices.values())

            # 接收响应直到超时
            end_time = time.time() + self.timeout
            while time.time() < end_time:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    break
                except OSError:
                    break

                device = self._parse_probe_match(data, addr)
                if device and device.ip:
                    # 去重
                    if device.ip not in devices:
                        devices[device.ip] = device
                        logger.info(f"发现 ONVIF 设备: {device.ip} {device.get_display_name()}")

        finally:
            sock.close()

        return list(devices.values())


# 便捷函数
def discover_onvif_devices(timeout: float = PROBE_TIMEOUT) -> List[OnvifDeviceInfo]:
    """便捷函数：快速发现 ONVIF 设备"""
    scanner = OnvifScanner(timeout=timeout)
    return scanner.discover()
