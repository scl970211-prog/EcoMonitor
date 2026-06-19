"""
ISAPI 客户端 - 通过 HTTP 接口获取设备信息。
用于获取 SDK 无法直接提供的通道名称和接入状态。
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

logger = logging.getLogger(__name__)


class ISAPIClient:
    """视频设备 ISAPI 客户端。"""

    NS = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}

    def __init__(
        self,
        ip: str,
        port: int = 80,
        username: str = "",
        password: str = "",
        use_https: bool = True,
        verify: bool = False,
    ):
        self._ip = ip
        self._http_port = port
        self.username = username
        self.password = password
        self._use_https = use_https
        self._verify = verify
        self.base_url = ""

        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/xml",
                "Content-Type": "application/xml; charset=UTF-8",
            }
        )
        self.session.verify = verify
        self._connected = False
        self._auth_type: Optional[str] = None

    def _try_base_url(self, base_url: str) -> bool:
        """尝试使用指定 URL 连接 ISAPI。"""
        self.base_url = base_url
        try:
            response = self.session.get(
                f"{self.base_url}/ISAPI/System/deviceInfo", timeout=5
            )
            if response.status_code == 200:
                self._connected = True
                self._auth_type = "digest"
                return True

            if response.status_code == 401:
                self.session.auth = HTTPBasicAuth(self.username, self.password)
                response = self.session.get(
                    f"{self.base_url}/ISAPI/System/deviceInfo", timeout=5
                )
                if response.status_code == 200:
                    self._connected = True
                    self._auth_type = "basic"
                    return True
            return False
        except Exception as exc:
            logger.debug("ISAPI connect failed %s: %s", base_url, exc)
            return False

    def connect(self) -> bool:
        """测试 ISAPI 是否可用。优先 HTTPS，失败则降级到 HTTP 并记录安全警告。"""
        if self._use_https:
            if self._try_base_url(f"https://{self._ip}:443"):
                logger.info("ISAPI 通过 HTTPS 连接成功: %s", self.base_url)
                return True
            logger.warning("ISAPI HTTPS 连接失败，尝试降级到 HTTP: %s", self._ip)

        if self._try_base_url(f"http://{self._ip}:{self._http_port}"):
            if self._use_https:
                logger.warning(
                    "ISAPI 已通过 HTTP 明文传输（%s），建议设备启用 HTTPS",
                    self.base_url,
                )
            else:
                logger.info("ISAPI 通过 HTTP 连接成功: %s", self.base_url)
            return True

        return False

    def get_channel_name(self, channel_id: int) -> Optional[str]:
        """获取指定通道名称。"""
        for getter in (self._get_video_input_channel_name, self._get_ip_channel_name):
            name = getter(channel_id)
            if name:
                return name
        return None

    def _get_video_input_channel_name(self, channel_id: int) -> Optional[str]:
        try:
            response = self.session.get(
                f"{self.base_url}/ISAPI/System/Video/inputs/channels/{channel_id}",
                timeout=5,
            )
            if response.status_code != 200:
                return None

            root = ET.fromstring(response.content)
            name_elem = root.find(".//hik:name", self.NS) or root.find(".//name")
            if name_elem is not None and name_elem.text:
                return name_elem.text.strip()
            return None
        except Exception:
            return None

    def _get_ip_channel_name(self, channel_id: int) -> Optional[str]:
        try:
            response = self.session.get(
                f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels/{channel_id}",
                timeout=5,
            )
            if response.status_code != 200:
                return None

            root = ET.fromstring(response.content)
            name_elem = root.find(".//hik:name", self.NS) or root.find(".//name")
            if name_elem is not None and name_elem.text:
                return name_elem.text.strip()
            return None
        except Exception:
            return None

    def get_all_channel_names(self, start_dchan: int = 33) -> Dict[int, str]:
        """获取所有可读通道名称。"""
        names: Dict[int, str] = {}

        try:
            response = self.session.get(
                f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels",
                timeout=10,
            )
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                channels = root.findall(".//hik:InputProxyChannel", self.NS)
                for index, channel in enumerate(channels):
                    name_elem = channel.find("hik:name", self.NS)
                    if name_elem is not None and name_elem.text:
                        names[start_dchan + index] = name_elem.text.strip()
                if names:
                    return names

            response = self.session.get(
                f"{self.base_url}/ISAPI/System/Video/inputs/channels",
                timeout=10,
            )
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                channels = root.findall(".//hik:VideoInputChannel", self.NS)
                for channel in channels:
                    id_elem = channel.find("hik:id", self.NS)
                    name_elem = channel.find("hik:name", self.NS)
                    if id_elem is None or name_elem is None:
                        continue
                    if not id_elem.text or not name_elem.text:
                        continue
                    try:
                        names[int(id_elem.text)] = name_elem.text.strip()
                    except ValueError:
                        continue
        except Exception as exc:
            logger.debug("ISAPI get_all_channel_names failed: %s", exc)

        return names

    def get_input_proxy_channels(self, start_dchan: int = 33) -> List[Dict]:
        """
        获取已配置的 IP 通道清单。

        Returns:
            [{"id": 1, "sdk_id": 33, "name": "通道名", "ip": "1.2.3.4", "enabled": True}, ...]
        """
        channels_info: List[Dict] = []

        try:
            response = self.session.get(
                f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels",
                timeout=10,
            )
            if response.status_code != 200:
                return channels_info

            root = ET.fromstring(response.content)
            channels = root.findall(".//hik:InputProxyChannel", self.NS)

            for index, channel in enumerate(channels):
                id_elem = channel.find("hik:id", self.NS)
                name_elem = channel.find("hik:name", self.NS)
                ip_elem = channel.find(".//hik:ipAddress", self.NS)

                try:
                    logical_id = int(id_elem.text) if id_elem is not None and id_elem.text else index + 1
                except ValueError:
                    logical_id = index + 1

                channel_name = (
                    name_elem.text.strip()
                    if name_elem is not None and name_elem.text
                    else f"通道{logical_id}"
                )
                ip_address = ip_elem.text.strip() if ip_elem is not None and ip_elem.text else ""

                channels_info.append(
                    {
                        "id": logical_id,
                        "sdk_id": start_dchan + index,
                        "name": channel_name,
                        "ip": ip_address,
                        "enabled": True,
                    }
                )
        except Exception as exc:
            logger.debug("ISAPI get_input_proxy_channels failed: %s", exc)
            return channels_info

        return channels_info

    def close(self):
        """关闭会话。"""
        self.session.close()
        self._connected = False
