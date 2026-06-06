# -*- coding: utf-8 -*-
"""
增强型扫描器 - 整合 ARP、ICMP、TCP 三种扫描方式
与原项目设备搜索功能对齐
"""

import logging
import platform
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal

from .device_info import Device, get_resolver
from .device_fingerprint import DeviceFingerprinter, get_fingerprinter
from .network_utils import parse_ip_range, get_ip_count, get_local_networks

logger = logging.getLogger(__name__)


# 预编译MAC地址正则表达式
MAC_PATTERN = re.compile(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})")


@dataclass
class ScanResult:
    """扫描结果"""
    ip: str
    is_online: bool = False
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    scan_method: str = ""
    response_time: float = -1.0
    open_ports: List[int] = field(default_factory=list)


class ARPScanner:
    """ARP 扫描器 - 读取系统 ARP 缓存获取 MAC 地址"""
    
    # 多播 MAC 前缀
    MULTICAST_PREFIXES = ('01:00:5e', '33:33:', 'ff:ff:ff')
    
    def __init__(self):
        self.resolver = get_resolver()
        self.system = platform.system().lower()
    
    def scan_batch(self, ips: List[str], timeout: float = 1.0) -> Dict[str, str]:
        """
        批量读取 ARP 缓存
        
        Returns:
            Dict[str, str]: IP 到 MAC 的映射
        """
        if not ips:
            return {}
        
        cache = self._read_arp_cache()
        results = {}
        
        for ip in ips:
            if ip in cache:
                results[ip] = cache[ip]
        
        return results
    
    def get_all_cached_devices(self) -> Dict[str, str]:
        """
        获取 ARP 缓存中的所有有效设备（过滤多播/广播）
        
        Returns:
            Dict[str, str]: IP 到 MAC 的映射
        """
        cache = self._read_arp_cache()
        # 过滤多播和广播地址
        filtered = {}
        for ip, mac in cache.items():
            normalized_mac = mac.lower().replace('-', ':')
            if not any(normalized_mac.startswith(p) for p in self.MULTICAST_PREFIXES):
                # 排除广播地址
                if not ip.endswith('.255') and not ip == '255.255.255.255':
                    filtered[ip] = mac
        return filtered
    
    def _read_arp_cache(self) -> Dict[str, str]:
        """读取系统 ARP 缓存"""
        try:
            if self.system == "windows":
                return self._read_arp_cache_windows()
            else:
                return self._read_arp_cache_unix()
        except Exception as e:
            logger.debug(f"读取 ARP 缓存失败: {e}")
            return {}
    
    def _read_arp_cache_windows(self) -> Dict[str, str]:
        """Windows: 使用 arp -a 读取缓存"""
        cache = {}
        encodings = ["utf-8", "gbk", "gb2312", "cp936"]
        
        for encoding in encodings:
            try:
                result = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True,
                    text=True,
                    encoding=encoding,
                    errors="ignore",
                    timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # 解析输出：格式为 "  192.168.1.1           00-11-22-33-44-55     动态"
                for line in result.stdout.splitlines():
                    match = MAC_PATTERN.search(line)
                    if match:
                        mac = match.group(0)
                        parts = line[:match.start()].split()
                        if parts:
                            ip = parts[-1].strip()
                            # 验证 IP 格式
                            if ip and self._is_valid_ip(ip):
                                cache[ip] = mac
                
                return cache
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.debug(f"读取 ARP 缓存失败: {e}")
                break
        
        return cache
    
    def _read_arp_cache_unix(self) -> Dict[str, str]:
        """Linux/Mac: 使用 arp -an 读取缓存"""
        cache = {}
        
        try:
            result = subprocess.run(
                ["arp", "-an"],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            # 解析输出：格式为 "? (192.168.1.1) at 00:11:22:33:44:55 on eth0"
            for line in result.stdout.splitlines():
                match = MAC_PATTERN.search(line)
                if match:
                    mac = match.group(0)
                    ip_match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
                    if ip_match:
                        ip = ip_match.group(1)
                        if self._is_valid_ip(ip):
                            cache[ip] = mac
        except Exception as e:
            logger.debug(f"读取 ARP 缓存失败: {e}")
        
        return cache
    
    def _is_valid_ip(self, ip: str) -> bool:
        """验证 IP 地址格式"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip):
            return False
        # 验证每个字节范围
        for part in ip.split('.'):
            if not 0 <= int(part) <= 255:
                return False
        return True


class ICMPScanner:
    """ICMP 扫描器 - 使用 icmplib 或系统 ping"""
    
    def __init__(self):
        self.resolver = get_resolver()
        self._use_icmplib = False
        self._check_icmplib()
    
    def _check_icmplib(self):
        """检查是否可用 icmplib"""
        try:
            from icmplib import multiping
            # 测试本地回环
            hosts = multiping(["127.0.0.1"], count=1, timeout=1, privileged=False)
            if hosts and hosts[0].is_alive:
                self._use_icmplib = True
                logger.info("使用 icmplib 进行 ICMP 扫描")
        except Exception as e:
            logger.warning(f"icmplib 不可用，将使用系统 ping: {e}")
            self._use_icmplib = False
    
    def scan_batch(self, ips: List[str], timeout: float = 1.0) -> Dict[str, ScanResult]:
        """批量 ICMP 扫描"""
        if self._use_icmplib:
            return self._scan_icmplib(ips, timeout)
        else:
            return self._scan_system_ping(ips, timeout)
    
    def _scan_icmplib(self, ips: List[str], timeout: float) -> Dict[str, ScanResult]:
        """使用 icmplib 扫描"""
        from icmplib import multiping
        
        results = {}
        
        try:
            hosts = multiping(
                addresses=ips,
                count=1,
                interval=0,
                timeout=timeout,
                concurrent_tasks=min(100, len(ips)),
                privileged=False,  # Windows 无需管理员权限
            )
            
            for host in hosts:
                if host.is_alive:
                    results[host.address] = ScanResult(
                        ip=host.address,
                        is_online=True,
                        response_time=round(host.min_rtt, 2),
                        scan_method="ICMP"
                    )
        except Exception as e:
            logger.debug(f"icmplib 扫描失败: {e}")
        
        return results
    
    def _scan_system_ping(self, ips: List[str], timeout: float) -> Dict[str, ScanResult]:
        """使用系统 ping 命令扫描"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            future_to_ip = {
                executor.submit(self._ping_single, ip, timeout): ip
                for ip in ips
            }
            
            for future in as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    response_time = future.result()
                    if response_time > 0:
                        results[ip] = ScanResult(
                            ip=ip,
                            is_online=True,
                            response_time=response_time,
                            scan_method="ICMP"
                        )
                except Exception:
                    pass
        
        return results
    
    def _ping_single(self, ip: str, timeout: float) -> float:
        """单个 ping"""
        try:
            start_time = time.time()
            
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout + 0.5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]
                result = subprocess.run(cmd, capture_output=True, timeout=timeout + 0.5)
            
            if result.returncode == 0:
                return (time.time() - start_time) * 1000
        except Exception:
            pass
        
        return -1


class TCPScanner:
    """TCP 扫描器 - 探测开放端口"""
    
    # 常见端口 + 设备特征端口（用于指纹识别）
    COMMON_PORTS = [
        80, 443, 554, 8000, 8080,  # 监控设备、Web服务
        22, 23, 21,                 # 远程管理
        3389, 445, 139, 135,        # Windows
        62078,                      # iOS Apple Mobile Sync
        5555,                       # Android ADB
        1900, 5353,                 # UPnP/SSDP, mDNS
        8443,                       # HTTPS备用
    ]
    
    def scan_batch(self, ips: List[str], timeout: float = 1.0,
                   max_ports: int = 5) -> Dict[str, ScanResult]:
        """批量 TCP 扫描"""
        import socket
        
        results = {}
        ports = self.COMMON_PORTS[:max_ports]
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            future_to_ip = {}
            for ip in ips:
                for port in ports:
                    future = executor.submit(self._check_port, ip, port, timeout)
                    future_to_ip[future] = (ip, port)
            
            ip_ports: Dict[str, List[int]] = {}
            
            for future in as_completed(future_to_ip):
                ip, port = future_to_ip[future]
                try:
                    is_open = future.result()
                    if is_open:
                        if ip not in ip_ports:
                            ip_ports[ip] = []
                        ip_ports[ip].append(port)
                except Exception:
                    pass
            
            for ip, open_ports in ip_ports.items():
                results[ip] = ScanResult(
                    ip=ip,
                    is_online=True,
                    open_ports=open_ports,
                    scan_method="TCP"
                )
        
        return results
    
    def _check_port(self, ip: str, port: int, timeout: float) -> bool:
        """检查端口是否开放"""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False


class EnhancedScanner(QObject):
    """
    增强型扫描器 - 整合 ARP、ICMP、TCP 三种方式
    与原项目设备搜索功能对齐
    """
    
    # 信号
    devices_found = pyqtSignal(list)       # 批量发现设备
    progress_update = pyqtSignal(int, int)  # 当前进度, 总数
    scan_finished = pyqtSignal()           # 扫描完成
    scan_error = pyqtSignal(str)           # 错误信息
    
    # 每批处理的IP数量
    BATCH_SIZE = 50
    
    def __init__(self):
        super().__init__()
        
        # 初始化扫描器
        self._arp_scanner = ARPScanner()
        self._icmp_scanner = ICMPScanner()
        self._tcp_scanner = TCPScanner()
        self._fingerprinter = get_fingerprinter(timeout=2.0)
        
        # 状态
        self._is_scanning = False
        self._should_stop = False
        self._lock = threading.Lock()
        
        # 扫描选项
        self.use_arp = True
        self.use_icmp = True
        self.use_tcp = True
        self.use_onvif = True         # 新增：是否启用 ONVIF 快速发现
        self.use_fingerprint = False  # 默认关闭指纹识别以提升扫描速度
        self.timeout = 1.0
    
    def start_scan(self, ip_range: str, use_arp: bool = True,
                   use_icmp: bool = True, use_tcp: bool = True,
                   use_onvif: bool = True,
                   timeout: float = 1.0):
        """
        开始扫描
        
        Args:
            ip_range: IP范围字符串（CIDR或范围格式）
            use_arp: 是否使用 ARP 扫描
            use_icmp: 是否使用 ICMP 扫描
            use_tcp: 是否使用 TCP 扫描
            use_onvif: 是否使用 ONVIF 快速发现
            timeout: 超时时间（秒）
        """
        with self._lock:
            if self._is_scanning:
                self.scan_error.emit("扫描正在进行中")
                return
        
        # 计算 IP 数量
        ip_count = get_ip_count(ip_range)
        
        if ip_count == 0:
            self.scan_error.emit("无效的IP范围")
            return
        
        if ip_count > 65536:
            self.scan_error.emit("IP范围过大（超过65536个地址）")
            return
        
        # 初始化状态
        with self._lock:
            self._is_scanning = True
            self._should_stop = False
            self.use_arp = use_arp
            self.use_icmp = use_icmp
            self.use_tcp = use_tcp
            self.use_onvif = use_onvif
            self.timeout = timeout
        
        self.progress_update.emit(0, ip_count)
        
        # 在后台线程中执行扫描
        thread = threading.Thread(
            target=self._scan_worker,
            args=(list(parse_ip_range(ip_range)), ip_count)
        )
        thread.daemon = True
        thread.start()
    
    def _scan_worker(self, ip_list: List[str], total_count: int):
        """扫描工作线程 - 优化版：先 ONVIF 快速发现，再深度扫描"""
        try:
            processed = 0
            all_devices: Dict[str, 'Device'] = {}
            
            # ========== 第一阶段：ONVIF WS-Discovery 快速发现 ==========
            if not self._should_stop and self.use_onvif:
                try:
                    from .onvif_scanner import OnvifScanner
                    onvif_scanner = OnvifScanner(timeout=2.0)
                    onvif_devices = onvif_scanner.discover()
                    
                    for od in onvif_devices:
                        if self._should_stop:
                            break
                        # 只保留在目标 IP 范围内的设备
                        if od.ip in ip_list:
                            device = Device(od.ip)
                            device.is_online = True
                            device.scan_method = "ONVIF"
                            device.hostname = od.get_display_name()
                            # 尝试从 scopes 提取厂商
                            vendor = od.get_vendor_hint()
                            if vendor:
                                device.vendor = vendor
                                device.fingerprint_vendor = vendor
                            # 从 XAddrs 提取端口
                            if od.port and od.port != 80:
                                device.open_ports = [od.port]
                            all_devices[od.ip] = device
                            self.devices_found.emit([device])
                    
                    logger.info(f"ONVIF 发现 {len(onvif_devices)} 台设备，"
                                f"其中 {len(all_devices)} 台在目标范围内")
                except Exception as e:
                    logger.debug(f"ONVIF 扫描失败: {e}")
            # ==========================================================
            
            # 更新进度（ONVIF 阶段快速完成，不占用大量进度）
            if all_devices:
                self.progress_update.emit(min(len(all_devices), total_count), total_count)
            
            # ========== 第二阶段：ICMP + TCP 深度扫描（兜底） ==========
            # 排除已被 ONVIF 发现的 IP
            remaining_ips = [ip for ip in ip_list if ip not in all_devices]
            
            for i in range(0, len(remaining_ips), self.BATCH_SIZE):
                if self._should_stop:
                    break
                
                batch = remaining_ips[i:i + self.BATCH_SIZE]
                devices = self._scan_batch(batch)
                
                if devices:
                    for d in devices:
                        all_devices[d.ip] = d
                    self.devices_found.emit(devices)
                
                processed += len(batch)
                current_progress = len(all_devices) + processed
                self.progress_update.emit(min(current_progress, total_count), total_count)
            
            # 最后统一做主机名解析（只对 ONVIF/ICMP 发现但没解析到主机名的设备）
            unresolved = [d for d in all_devices.values() if not d.hostname]
            if unresolved:
                self._resolve_hostnames(unresolved)
                
        except Exception as e:
            logger.exception("扫描过程出错")
            self.scan_error.emit(f"扫描错误: {e}")
        finally:
            with self._lock:
                self._is_scanning = False
            self.scan_finished.emit()
    
    def _scan_batch(self, ip_batch: List[str]) -> List[Device]:
        """扫描一批 IP - 优化策略：ARP缓存优先 + ICMP + TCP兜底"""
        found_devices: Dict[str, Device] = {}
        
        # 1. 先读取 ARP 缓存获取已知设备（包含MAC地址）
        arp_cached_devices = {}
        if self.use_arp:
            try:
                # 获取当前批次的 ARP 缓存
                arp_cached_devices = self._arp_scanner.scan_batch(ip_batch, self.timeout)
                # 同时获取所有缓存中的设备（用于补充）
                all_cached = self._arp_scanner.get_all_cached_devices()
                arp_cached_devices.update(all_cached)
            except Exception as e:
                logger.debug(f"读取 ARP 缓存失败: {e}")
        
        # 2. ICMP 批量探测（最快速，跳过 ARP 已知的设备）
        icmp_results = {}
        if self.use_icmp:
            # ICMP 扫描 ARP 中没有的设备
            icmp_ips = [ip for ip in ip_batch if ip not in arp_cached_devices]
            if icmp_ips:
                icmp_results = self._icmp_scanner.scan_batch(icmp_ips, self.timeout)
                for ip, result in icmp_results.items():
                    device = Device(ip)
                    device.is_online = True
                    device.response_time = result.response_time
                    device.scan_method = result.scan_method
                    found_devices[ip] = device
        
        # 3. 将 ARP 缓存中的设备添加到结果（标记为在线）
        for ip, mac in arp_cached_devices.items():
            if ip in ip_batch and ip not in found_devices:
                device = Device(ip)
                device.is_online = True
                device.mac = self._normalize_mac(mac)
                device.vendor = self._get_vendor(mac)
                device.scan_method = "ARP"
                found_devices[ip] = device
        
        # 4. 为 ICMP 发现的设备补充 ARP 信息
        if self.use_arp and found_devices:
            try:
                arp_results = self._arp_scanner.scan_batch(
                    list(found_devices.keys()), self.timeout
                )
                for ip, mac in arp_results.items():
                    if ip in found_devices and not found_devices[ip].mac:
                        found_devices[ip].mac = self._normalize_mac(mac)
                        found_devices[ip].vendor = self._get_vendor(mac)
            except Exception as e:
                logger.debug(f"ARP 补充扫描失败: {e}")
        
        # 5. TCP 批量探测（对 ICMP 和 ARP 都未发现的 IP 进行兜底）
        if self.use_tcp:
            unchecked_ips = [ip for ip in ip_batch if ip not in found_devices]
            if unchecked_ips:
                tcp_results = self._tcp_scanner.scan_batch(unchecked_ips, self.timeout)
                
                # 为 TCP 发现的设备补充 ARP 信息
                if self.use_arp and tcp_results:
                    try:
                        arp_results_2 = self._arp_scanner.scan_batch(
                            list(tcp_results.keys()), self.timeout
                        )
                        for ip, mac in arp_results_2.items():
                            if ip in tcp_results:
                                tcp_results[ip].mac = self._normalize_mac(mac)
                                tcp_results[ip].vendor = self._get_vendor(mac)
                    except Exception:
                        pass
                
                for ip, result in tcp_results.items():
                    if ip not in found_devices:
                        device = Device(ip)
                        device.is_online = True
                        device.scan_method = result.scan_method
                        device.open_ports = result.open_ports
                        device.mac = result.mac
                        device.vendor = result.vendor
                        found_devices[ip] = device
        
        # 6. 异步解析主机名（不阻塞扫描进度）
        if found_devices:
            self._resolve_hostnames(list(found_devices.values()))
        
        # 7. 设备指纹识别（应对随机MAC地址设备）
        if self.use_fingerprint and found_devices:
            self._fingerprint_devices(list(found_devices.values()))
        
        return list(found_devices.values())
    
    def _fingerprint_devices(self, devices: List[Device]):
        """对设备进行指纹识别（识别随机MAC设备）"""
        def fingerprint_single(device: Device):
            try:
                # 如果没有开放端口，先快速扫描关键特征端口
                #（ARP发现的设备通常没有端口信息）
                ports = device.open_ports
                if not ports:
                    ports = self._quick_port_scan(device.ip)
                    device.open_ports = ports
                
                # 执行指纹识别
                fp = self._fingerprinter.fingerprint_device(device.ip, ports)
                
                # 更新设备信息（仅当指纹结果有效时）
                if fp.device_type:
                    device.device_type = fp.device_type
                if fp.os_family:
                    device.os_family = fp.os_family
                if fp.vendor_hint:
                    device.fingerprint_vendor = fp.vendor_hint
                if fp.confidence > 0:
                    device.fingerprint_confidence = fp.confidence
                if fp.methods:
                    device.fingerprint_methods = fp.methods
                    
            except Exception as e:
                logger.debug(f"指纹识别失败 {device.ip}: {e}")
        
        # 对所有在线设备进行指纹识别（包括只有MAC地址的设备）
        devices_to_fingerprint = [d for d in devices if d.is_online]
        
        if devices_to_fingerprint:
            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(fingerprint_single, devices_to_fingerprint)
    
    def _quick_port_scan(self, ip: str) -> List[int]:
        """快速扫描关键特征端口（用于指纹识别）"""
        import socket
        
        # 设备特征端口（快速识别用）
        key_ports = [62078, 5555, 554, 8000, 80, 445, 3389]
        open_ports = []
        
        for port in key_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)  # 短超时，快速扫描
                result = sock.connect_ex((ip, port))
                sock.close()
                if result == 0:
                    open_ports.append(port)
            except Exception:
                pass
        
        return open_ports
    
    def _resolve_hostnames(self, devices: List[Device]):
        """异步解析主机名"""
        def resolve_device(device: Device):
            try:
                import socket
                hostname = socket.gethostbyaddr(device.ip)[0]
                if hostname:
                    device.hostname = hostname
            except Exception:
                pass
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(resolve_device, devices)
    
    def _normalize_mac(self, mac: str) -> str:
        """标准化 MAC 地址"""
        return self._arp_scanner.resolver.normalize_mac(mac) if hasattr(self._arp_scanner, 'resolver') else mac
    
    def _get_vendor(self, mac: str) -> str:
        """获取厂商信息"""
        return self._arp_scanner.resolver.get_vendor(mac) if hasattr(self._arp_scanner, 'resolver') else ""
    
    def stop_scan(self):
        """停止扫描"""
        with self._lock:
            self._should_stop = True
            self._is_scanning = False
        self.scan_finished.emit()
    
    def is_scanning(self) -> bool:
        """是否正在扫描"""
        with self._lock:
            return self._is_scanning
    
    def get_auto_range(self) -> str:
        """获取自动网段"""
        networks = get_local_networks()
        if networks:
            return networks[0]["cidr"]
        return ""


def create_scanner() -> EnhancedScanner:
    """创建扫描器实例（兼容旧接口）"""
    return EnhancedScanner()
