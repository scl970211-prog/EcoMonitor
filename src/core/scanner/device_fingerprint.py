# -*- coding: utf-8 -*-
"""
设备指纹识别模块 - 应对随机MAC地址的设备识别

针对:
- iPhone/iPad (iOS 14+ 私有Wi-Fi地址)
- 安卓手机 (随机MAC)
- Windows (随机硬件地址)
- 智能电视、IoT设备隐私模式
"""

import socket
import struct
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class DeviceFingerprint:
    """设备指纹信息"""
    ip: str
    device_type: str = ""  # 设备类型: Phone, Tablet, PC, TV, IoT, Camera, etc.
    os_family: str = ""    # 操作系统: iOS, Android, Windows, Linux, etc.
    vendor_hint: str = ""  # 可能的厂商
    confidence: int = 0    # 置信度 0-100
    methods: List[str] = None  # 识别方法
    
    def __post_init__(self):
        if self.methods is None:
            self.methods = []


class DeviceFingerprinter:
    """设备指纹识别器"""
    
    # 常见设备端口指纹
    PORT_FINGERPRINTS = {
        # iOS 设备常见开放端口
        'iOS': {
            'ports': [62078],  # Apple Mobile Sync
            'patterns': [
                (80, b'Apple'),
                (443, b'Apple'),
            ]
        },
        # Android 设备
        'Android': {
            'ports': [5555],  # ADB
            'patterns': []
        },
        # Windows 设备
        'Windows': {
            'ports': [135, 139, 445, 3389],  # SMB, RDP
            'patterns': []
        },
        # 监控设备
        'Camera': {
            'ports': [80, 443, 554, 8000, 8080, 8443],  # RTSP, HTTP
            'patterns': [
                (80, b'Hikvision'),
                (80, b'Dahua'),
                (80, b'IPC'),
                (80, b'Camera'),
            ]
        },
    }
    
    # mDNS/Bonjour 服务类型映射
    MDNS_SERVICES = {
        '_apple-mobdev._tcp': 'iOS Device',
        '_apple-mobdev2._tcp': 'iOS Device',
        '_airplay._tcp': 'Apple TV/AirPlay',
        '_raop._tcp': 'AirPort Express',
        '_companion-link._tcp': 'Apple Device',
        '_googlecast._tcp': 'Chromecast/Android',
        '_androidtvremote._tcp': 'Android TV',
        '_http._tcp': 'Web Service',
        '_ipp._tcp': 'Printer',
        '_pdl-datastream._tcp': 'Printer',
    }
    
    # DHCP 指纹 (选项参数组合)
    DHCP_FINGERPRINTS = {
        '61,60,55,43': 'iOS',
        '1,121,33,3,6,15,119,252,95,44,46,47': 'Windows',
        '1,3,6,15,26,28,51,58,59,43': 'Android',
        '1,3,6,12,15,28,42,121': 'Linux',
    }
    
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
    
    def fingerprint_device(self, ip: str, open_ports: List[int] = None) -> DeviceFingerprint:
        """
        对设备进行指纹识别
        
        Args:
            ip: IP地址
            open_ports: 已发现的开放端口
            
        Returns:
            DeviceFingerprint: 设备指纹信息
        """
        result = DeviceFingerprint(ip=ip)
        
        if open_ports is None:
            open_ports = []
        
        # 1. 尝试 mDNS/Bonjour 发现 (iOS/macOS 设备)
        self._try_mdns_discovery(ip, result)
        
        # 2. 尝试 SNMP 查询
        self._try_snmp_query(ip, result)
        
        # 3. 尝试 UPnP/SSDP 发现 (智能电视、IoT)
        self._try_upnp_discovery(ip, result)
        
        # 4. 基于端口组合识别
        self._analyze_port_pattern(open_ports, result)
        
        # 5. 尝试 HTTP 服务识别
        self._try_http_identify(ip, open_ports, result)
        
        # 6. NetBIOS 查询 (Windows)
        self._try_netbios_query(ip, result)
        
        return result
    
    def _try_mdns_discovery(self, ip: str, result: DeviceFingerprint):
        """尝试 mDNS 服务发现 - 适用于 iOS/macOS 设备"""
        try:
            # 尝试连接到常见的 mDNS 多播地址
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # 简单的 mDNS PTR 查询包 (简化版)
            query = self._build_mdns_query()
            
            sock.sendto(query, (ip, 5353))
            response, addr = sock.recvfrom(1024)
            
            if response:
                # 解析 mDNS 响应获取设备信息
                hostname = self._parse_mdns_response(response)
                if hostname:
                    result.device_type = self._guess_type_from_hostname(hostname)
                    if 'iPhone' in hostname or 'iPad' in hostname or 'Apple' in hostname:
                        result.os_family = 'iOS'
                        result.vendor_hint = 'Apple'
                        result.confidence = 90
                    elif 'Android' in hostname:
                        result.os_family = 'Android'
                        result.confidence = 80
                    result.methods.append('mDNS')
                    
        except Exception:
            pass
    
    def _build_mdns_query(self) -> bytes:
        """构建简单的 mDNS 查询包"""
        # DNS 查询包头
        transaction_id = b'\x00\x00'
        flags = b'\x00\x00'
        questions = struct.pack('>H', 1)
        answer_rrs = struct.pack('>H', 0)
        authority_rrs = struct.pack('>H', 0)
        additional_rrs = struct.pack('>H', 0)
        
        # 查询 _services._dns-sd._udp.local
        query_name = b'\x09_services\x07_dns-sd\x04_udp\x05_local\x00'
        query_type = struct.pack('>H', 12)  # PTR
        query_class = struct.pack('>H', 1)  # IN
        
        return (transaction_id + flags + questions + answer_rrs + 
                authority_rrs + additional_rrs + query_name + query_type + query_class)
    
    def _parse_mdns_response(self, response: bytes) -> str:
        """解析 mDNS 响应"""
        try:
            # 简化解析，提取主机名
            if b'iPhone' in response:
                return 'iPhone'
            elif b'iPad' in response:
                return 'iPad'
            elif b'Apple' in response:
                return 'Apple-Device'
            elif b'Android' in response:
                return 'Android-Device'
        except Exception:
            pass
        return ''
    
    def _try_snmp_query(self, ip: str, result: DeviceFingerprint):
        """尝试 SNMP 查询获取设备信息"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # SNMP v1 GetRequest (sysDescr)
            snmp_request = bytes([
                0x30, 0x26,  # SEQUENCE
                0x02, 0x01, 0x00,  # INTEGER version (0 = v1)
                0x04, 0x06, 0x70, 0x75, 0x62, 0x6c, 0x69, 0x63,  # OCTET STRING "public"
                0xa0, 0x19,  # GetRequest-PDU
                0x02, 0x04, 0x00, 0x00, 0x00, 0x01,  # request-id
                0x02, 0x01, 0x00,  # error-status
                0x02, 0x01, 0x00,  # error-index
                0x30, 0x0b,  # variable-bindings
                0x30, 0x09,
                0x06, 0x05, 0x2b, 0x06, 0x01, 0x02, 0x01,  # OID 1.3.6.1.2.1 (system)
                0x01, 0x01, 0x00,  # sysDescr.0
                0x05, 0x00,  # NULL
            ])
            
            sock.sendto(snmp_request, (ip, 161))
            response, _ = sock.recvfrom(1024)
            
            if response and len(response) > 50:
                # 解析 SNMP 响应中的设备描述
                desc = self._parse_snmp_response(response)
                if desc:
                    self._identify_from_description(desc, result)
                    result.methods.append('SNMP')
                    
        except Exception:
            pass
    
    def _parse_snmp_response(self, response: bytes) -> str:
        """解析 SNMP 响应"""
        try:
            # 查找字符串描述
            start = response.find(b'Linux')
            if start == -1:
                start = response.find(b'Windows')
            if start == -1:
                start = response.find(b'Apple')
            
            if start != -1:
                end = response.find(b'\x00', start)
                if end == -1:
                    end = len(response)
                return response[start:end].decode('utf-8', errors='ignore')
        except Exception:
            pass
        return ''
    
    def _try_upnp_discovery(self, ip: str, result: DeviceFingerprint):
        """尝试 UPnP/SSDP 发现 - 适用于智能电视、IoT"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # SSDP M-SEARCH 请求
            ssdp_request = (
                b'M-SEARCH * HTTP/1.1\r\n'
                b'HOST: 239.255.255.250:1900\r\n'
                b'MAN: "ssdp:discover"\r\n'
                b'MX: 1\r\n'
                b'ST: ssdp:all\r\n'
                b'\r\n'
            )
            
            # 直接查询目标设备
            sock.sendto(ssdp_request, (ip, 1900))
            response, _ = sock.recvfrom(2048)
            
            if response:
                headers = self._parse_http_headers(response)
                
                # 分析 SSDP 头部
                server = headers.get('SERVER', '').lower()
                usn = headers.get('USN', '').lower()
                
                if 'android' in server or 'google' in usn:
                    result.os_family = 'Android'
                    result.device_type = 'TV' if 'tv' in server else 'Phone'
                    result.confidence = 85
                elif 'tizen' in server or 'samsung' in server:
                    result.os_family = 'Tizen'
                    result.vendor_hint = 'Samsung'
                    result.device_type = 'TV'
                    result.confidence = 90
                elif 'webos' in server or 'lg' in server:
                    result.vendor_hint = 'LG'
                    result.device_type = 'TV'
                    result.confidence = 90
                elif 'roku' in server:
                    result.vendor_hint = 'Roku'
                    result.device_type = 'TV'
                    result.confidence = 95
                    
                result.methods.append('SSDP')
                
        except Exception:
            pass
    
    def _analyze_port_pattern(self, open_ports: List[int], result: DeviceFingerprint):
        """基于开放端口组合识别设备类型"""
        port_set = set(open_ports)
        
        # iOS 设备特征
        if 62078 in port_set:
            result.os_family = 'iOS'
            result.device_type = 'Phone'
            result.vendor_hint = 'Apple'
            result.confidence = max(result.confidence, 85)
            if 'Port-Fingerprint' not in result.methods:
                result.methods.append('Port-Fingerprint')
            return
        
        # Windows 设备特征
        if {135, 445}.issubset(port_set) or 3389 in port_set:
            result.os_family = 'Windows'
            result.device_type = 'PC'
            result.confidence = max(result.confidence, 80)
            if 'Port-Fingerprint' not in result.methods:
                result.methods.append('Port-Fingerprint')
            return
        
        # 安卓 ADB
        if 5555 in port_set:
            result.os_family = 'Android'
            result.confidence = max(result.confidence, 90)
            if 'Port-Fingerprint' not in result.methods:
                result.methods.append('Port-Fingerprint')
            return
        
        # 监控设备特征
        if 554 in port_set or 8000 in port_set:
            result.device_type = 'Camera'
            result.confidence = max(result.confidence, 75)
            if 'Port-Fingerprint' not in result.methods:
                result.methods.append('Port-Fingerprint')
    
    def _try_http_identify(self, ip: str, open_ports: List[int], result: DeviceFingerprint):
        """尝试通过 HTTP 服务识别设备"""
        http_ports = [p for p in open_ports if p in [80, 443, 8000, 8080, 8443]]
        
        for port in http_ports[:2]:  # 最多尝试2个端口
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((ip, port))
                
                # 发送 HTTP 请求
                request = f'GET / HTTP/1.1\r\nHost: {ip}\r\nUser-Agent: Mozilla/5.0\r\n\r\n'
                sock.send(request.encode())
                
                response = sock.recv(4096).decode('utf-8', errors='ignore')
                sock.close()
                
                if response:
                    headers = self._parse_http_headers(response.encode())
                    server = headers.get('SERVER', '').lower()
                    
                    # 识别特定设备
                    if 'apple' in server or 'airtunes' in response.lower():
                        result.vendor_hint = 'Apple'
                        if not result.os_family:
                            result.os_family = 'iOS'
                        result.confidence = max(result.confidence, 80)
                        result.methods.append(f'HTTP-{port}')
                    elif 'android' in server:
                        result.os_family = 'Android'
                        result.confidence = max(result.confidence, 75)
                        result.methods.append(f'HTTP-{port}')
                    elif 'microsoft' in server or 'iis' in server:
                        result.os_family = 'Windows'
                        result.confidence = max(result.confidence, 80)
                        result.methods.append(f'HTTP-{port}')
                        
                    # 检查页面内容
                    if 'hikvision' in response.lower():
                        result.vendor_hint = 'Hikvision'
                        result.device_type = 'Camera'
                        result.confidence = 95
                    elif 'dahua' in response.lower():
                        result.vendor_hint = 'Dahua'
                        result.device_type = 'Camera'
                        result.confidence = 95
                        
                    break
                    
            except Exception:
                continue
    
    def _try_netbios_query(self, ip: str, result: DeviceFingerprint):
        """尝试 NetBIOS 查询 - 主要用于识别 Windows"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # NetBIOS 名称服务查询
            netbios_query = bytes([
                0x00, 0x00,  # Transaction ID
                0x00, 0x10,  # Flags
                0x00, 0x01,  # Questions
                0x00, 0x00,  # Answer RRs
                0x00, 0x00,  # Authority RRs
                0x00, 0x00,  # Additional RRs
                # Query: *\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00
                0x20, 0x43, 0x4b, 0x41, 0x41, 0x41, 0x41, 0x41,
                0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41,
                0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41,
                0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41,
                0x00, 0x00, 0x21, 0x00, 0x01,  # Type NB, Class IN
            ])
            
            sock.sendto(netbios_query, (ip, 137))
            response, _ = sock.recvfrom(1024)
            
            if response and len(response) > 50:
                # 解析 NetBIOS 名称
                names = self._parse_netbios_names(response)
                if names:
                    result.os_family = 'Windows'
                    result.device_type = 'PC'
                    result.confidence = max(result.confidence, 85)
                    result.methods.append('NetBIOS')
                    
        except Exception:
            pass
    
    def _parse_http_headers(self, data: bytes) -> Dict[str, str]:
        """解析 HTTP 头部"""
        headers = {}
        try:
            lines = data.decode('utf-8', errors='ignore').split('\r\n')
            for line in lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().upper()] = value.strip()
        except Exception:
            pass
        return headers
    
    def _parse_netbios_names(self, response: bytes) -> List[str]:
        """解析 NetBIOS 名称"""
        names = []
        try:
            # 简化解析
            offset = 57
            while offset < len(response) - 2:
                name_type = response[offset + 15]
                if name_type == 0x00:  # Workstation
                    name = response[offset:offset+15].decode('ascii', errors='ignore').strip()
                    if name:
                        names.append(name)
                offset += 18
        except Exception:
            pass
        return names
    
    def _guess_type_from_hostname(self, hostname: str) -> str:
        """从主机名猜测设备类型"""
        hostname_lower = hostname.lower()
        
        if 'iphone' in hostname_lower:
            return 'Phone'
        elif 'ipad' in hostname_lower:
            return 'Tablet'
        elif 'macbook' in hostname_lower or 'pc' in hostname_lower:
            return 'PC'
        elif 'tv' in hostname_lower:
            return 'TV'
        elif 'watch' in hostname_lower:
            return 'Wearable'
        return 'Unknown'
    
    def _identify_from_description(self, desc: str, result: DeviceFingerprint):
        """从设备描述字符串识别"""
        desc_lower = desc.lower()
        
        if 'iphone' in desc_lower:
            result.os_family = 'iOS'
            result.device_type = 'Phone'
            result.vendor_hint = 'Apple'
            result.confidence = 95
        elif 'ipad' in desc_lower:
            result.os_family = 'iOS'
            result.device_type = 'Tablet'
            result.vendor_hint = 'Apple'
            result.confidence = 95
        elif 'android' in desc_lower:
            result.os_family = 'Android'
            result.confidence = 90
        elif 'windows' in desc_lower:
            result.os_family = 'Windows'
            result.device_type = 'PC'
            result.confidence = 90
        elif 'linux' in desc_lower:
            result.os_family = 'Linux'
            result.confidence = 80


def get_fingerprinter(timeout: float = 2.0) -> DeviceFingerprinter:
    """获取设备指纹识别器实例"""
    return DeviceFingerprinter(timeout=timeout)
