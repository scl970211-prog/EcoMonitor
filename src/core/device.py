"""
设备操作类。
基于原预览项目逻辑，使用 SDK 原生预览链路，并补齐通道元数据和重连能力。
"""

import ctypes
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .isapi_client import ISAPIClient
from .sdk_loader import SDKLoader, NET_DVR_DEVICEINFO_V30, NET_DVR_PREVIEWINFO, get_error_message

logger = logging.getLogger(__name__)


class DeviceStatus:
    """设备状态常量。"""

    OFFLINE = "offline"
    CONNECTING = "connecting"
    ONLINE = "online"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class ChannelStatus:
    """通道状态常量。"""

    OFFLINE = "offline"
    ONLINE = "online"
    PREVIEWING = "previewing"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class DeviceInfo:
    """设备信息摘要。"""

    ip: str
    port: int
    username: str
    serial_number: str = ""
    device_type: str = ""
    analog_channels: int = 0
    ip_channels: int = 0
    total_channels: int = 0


class NET_DVR_CHANNAME(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("sChanName", ctypes.c_byte * 32),
        ("byRes", ctypes.c_byte * 64),
    ]


class Device(QObject):
    """
    单台设备的操作封装。

    功能:
    - 设备登录/登出
    - 自动重连
    - 通道元数据获取（优先 ISAPI）
    - SDK 原生实时预览
    """

    login_state_changed = pyqtSignal(bool)
    device_status_changed = pyqtSignal(str, str)  # status, error_msg
    channel_status_changed = pyqtSignal(int, str)  # channel_id, status

    # 兼容旧接口
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    RECONNECT_INTERVAL = 5
    MAX_RECONNECT_ATTEMPTS = 0
    HEARTBEAT_INTERVAL = 0
    NET_DVR_PLAYSTART = 1
    NET_DVR_PLAYSTOP = 2
    DOWNLOAD_FINISHED = 100
    DOWNLOAD_FAILED = 200
    DOWNLOAD_DISK_FULL = 300
    DOWNLOAD_STALL_TIMEOUT = 60

    def __init__(
        self,
        ip: str,
        port: int = 8000,
        username: str = "",
        password: str = "",
        http_port: int = 80,
    ):
        super().__init__()
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.http_port = http_port

        self.user_id: int = -1
        self._device_info: Optional[NET_DVR_DEVICEINFO_V30] = None
        self._is_connected = False
        self._lock = threading.Lock()
        self._preview_handles: Dict[int, int] = {}

        self._device_status = DeviceStatus.OFFLINE
        self._channel_status: Dict[int, str] = {}
        self._last_error = ""
        self._error_code = 0

        self._reconnect_timer: Optional[QTimer] = None
        self._heartbeat_timer: Optional[QTimer] = None
        self._reconnect_attempts = 0
        self._auto_reconnect_enabled = True
        self._channels_pending_restore: List[int] = []

        self._isapi_client: Optional[ISAPIClient] = None
        self._channel_names: Dict[int, str] = {}
        self._ip_channel_metadata: Dict[int, Dict] = {}

        self._sdk_loader = SDKLoader()
        self._sdk = self._sdk_loader.sdk
        self._init_sdk_functions()
        self._init_timers()

    def _init_sdk_functions(self):
        """补齐本模块依赖的 SDK 函数原型。"""
        if not self._sdk:
            return

        try:
            self._sdk.NET_DVR_GetDVRConfig.argtypes = [
                ctypes.c_long,
                ctypes.c_uint32,
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            self._sdk.NET_DVR_GetDVRConfig.restype = ctypes.c_bool
        except Exception:
            pass

        try:
            self._sdk.NET_DVR_RealPlay_V40.argtypes = [
                ctypes.c_long,
                ctypes.POINTER(NET_DVR_PREVIEWINFO),
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            self._sdk.NET_DVR_RealPlay_V40.restype = ctypes.c_long
            self._sdk.NET_DVR_StopRealPlay.argtypes = [ctypes.c_long]
            self._sdk.NET_DVR_StopRealPlay.restype = ctypes.c_bool
        except Exception:
            pass

    def _init_timers(self):
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._check_connection)

    def _get_sdk_error(self) -> Tuple[int, str]:
        """获取 SDK 错误码和错误消息。"""
        if not self._sdk:
            return -1, "SDK 未加载"

        try:
            error_code = int(self._sdk.NET_DVR_GetLastError())
        except Exception:
            error_code = -1

        return error_code, get_error_message(error_code)

    def _set_device_status(self, status: str, error_msg: str = ""):
        if self._device_status != status or self._last_error != error_msg:
            self._device_status = status
            self._last_error = error_msg
            self.device_status_changed.emit(status, error_msg)
            self.status_changed.emit(status)
            if error_msg:
                self.error_occurred.emit(error_msg)
            logger.info("device_status ip=%s status=%s detail=%s", self.ip, status, error_msg)

    def _set_channel_status(self, channel_id: int, status: str):
        old_status = self._channel_status.get(channel_id)
        if old_status != status:
            self._channel_status[channel_id] = status
            self.channel_status_changed.emit(channel_id, status)
            logger.info("channel_status ip=%s channel=%s status=%s", self.ip, channel_id, status)

    def _try_reconnect(self):
        if not self._auto_reconnect_enabled or self._is_connected:
            return

        self._set_device_status(
            DeviceStatus.RECONNECTING,
            f"第 {self._reconnect_attempts + 1} 次重连...",
        )

        try:
            self.login()
            self._reconnect_attempts = 0
            self._restore_previews()
        except Exception as exc:
            self._reconnect_attempts += 1
            self._set_device_status(DeviceStatus.ERROR, str(exc))
            logger.warning(
                "reconnect_failed ip=%s attempts=%s error=%s",
                self.ip,
                self._reconnect_attempts,
                exc,
            )
            if self.MAX_RECONNECT_ATTEMPTS == 0 or self._reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
                self._reconnect_timer.start(self.RECONNECT_INTERVAL * 1000)

    def _check_connection(self):
        if not self._is_connected or self.HEARTBEAT_INTERVAL <= 0 or not self._device_info:
            return

        try:
            test_channel = int(self._device_info.byStartChan)
            if int(self._device_info.byChanNum) <= 0:
                test_channel = int(self._device_info.byStartDChan)

            if test_channel <= 0:
                return

            chan_name = NET_DVR_CHANNAME()
            chan_name.dwSize = ctypes.sizeof(NET_DVR_CHANNAME)
            bytes_returned = ctypes.c_uint32(0)
            result = self._sdk.NET_DVR_GetDVRConfig(
                self.user_id,
                1064,
                test_channel,
                ctypes.byref(chan_name),
                ctypes.sizeof(NET_DVR_CHANNAME),
                ctypes.byref(bytes_returned),
            )
            if not result:
                error_code, error_msg = self._get_sdk_error()
                self._error_code = error_code
                self._handle_connection_lost(f"连接检测失败 [{error_code}]: {error_msg}")
        except Exception as exc:
            logger.warning("heartbeat_failed ip=%s error=%s", self.ip, exc)
            self._handle_connection_lost("连接丢失")

    def _handle_connection_lost(self, reason: str):
        if not self._is_connected:
            return

        if self._heartbeat_timer:
            self._heartbeat_timer.stop()

        self._is_connected = False
        self.user_id = -1
        self._set_device_status(DeviceStatus.OFFLINE, reason)
        self.login_state_changed.emit(False)

        self._channels_pending_restore = list(self._preview_handles.keys())
        self._preview_handles.clear()
        for channel_id in self._channels_pending_restore:
            self._set_channel_status(channel_id, ChannelStatus.OFFLINE)

        if self._auto_reconnect_enabled:
            self._reconnect_timer.start(self.RECONNECT_INTERVAL * 1000)

    def _restore_previews(self):
        for channel_id in self._channels_pending_restore:
            self._set_channel_status(channel_id, ChannelStatus.RECONNECTING)

    @staticmethod
    def _encode_sdk_text(text: str) -> bytes:
        for encoding in ("gbk", "utf-8"):
            try:
                return text.encode(encoding)
            except UnicodeEncodeError:
                continue
        return text.encode("utf-8", errors="ignore")

    @staticmethod
    def _decode_sdk_text(raw) -> str:
        if not raw:
            return ""

        if not isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw)

        raw = raw.split(b"\x00", 1)[0]
        for encoding in ("utf-8", "gbk", "gb2312", "mbcs", "latin-1"):
            try:
                return raw.decode(encoding).strip()
            except (LookupError, UnicodeDecodeError):
                continue
        return ""

    def get_device_status(self) -> tuple:
        return self._device_status, self._last_error, self._error_code

    def get_channel_status(self, channel_id: int) -> str:
        return self._channel_status.get(channel_id, ChannelStatus.OFFLINE)

    def enable_auto_reconnect(self, enabled: bool = True):
        self._auto_reconnect_enabled = enabled
        if not enabled and self._reconnect_timer:
            self._reconnect_timer.stop()

    def login(self) -> bool:
        with self._lock:
            if self._is_connected:
                return True

            self._set_device_status(DeviceStatus.CONNECTING)

            try:
                self._device_info = NET_DVR_DEVICEINFO_V30()
                self.user_id = self._sdk.NET_DVR_Login_V30(
                    self._encode_sdk_text(self.ip),
                    self.port,
                    self._encode_sdk_text(self.username),
                    self._encode_sdk_text(self.password),
                    ctypes.byref(self._device_info),
                )

                if self.user_id < 0:
                    error_code, error_msg = self._get_sdk_error()
                    self._error_code = error_code
                    if error_code == 1:
                        detail = "用户名或密码错误"
                    elif error_code in (7, 12):
                        detail = "无法连接到设备，请检查 IP 地址和网络"
                    elif error_code == 10:
                        detail = "连接超时，设备可能离线"
                    else:
                        detail = error_msg

                    full_error = f"登录失败 [{error_code}]: {detail}"
                    self._set_device_status(DeviceStatus.ERROR, full_error)
                    raise RuntimeError(full_error)

                self._is_connected = True
                self._error_code = 0
                self._set_device_status(DeviceStatus.ONLINE)
                self.login_state_changed.emit(True)

                if self._heartbeat_timer and self.HEARTBEAT_INTERVAL > 0:
                    self._heartbeat_timer.start(self.HEARTBEAT_INTERVAL * 1000)

                logger.info(
                    "login_success ip=%s port=%s analog=%s ip_channels=%s start_dchan=%s",
                    self.ip,
                    self.port,
                    int(self._device_info.byChanNum),
                    self.get_ip_channel_count(),
                    int(self._device_info.byStartDChan),
                )
                return True
            except Exception as exc:
                logger.error("login_failed ip=%s port=%s error=%s", self.ip, self.port, exc)
                self._is_connected = False
                raise

    def logout(self):
        with self._lock:
            if self._isapi_client:
                try:
                    self._isapi_client.close()
                except Exception:
                    pass
                self._isapi_client = None

            if self._reconnect_timer:
                self._reconnect_timer.stop()
            if self._heartbeat_timer:
                self._heartbeat_timer.stop()

            self._channels_pending_restore = []
            self._channel_names.clear()
            self._ip_channel_metadata.clear()

            for channel_id in list(self._preview_handles.keys()):
                self.stop_preview(channel_id)

            if self.user_id >= 0:
                self._sdk.NET_DVR_Logout(self.user_id)

            self.user_id = -1
            self._is_connected = False
            self._device_info = None
            self._set_device_status(DeviceStatus.OFFLINE, "用户主动断开")
            self.login_state_changed.emit(False)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def device_info(self) -> Optional[NET_DVR_DEVICEINFO_V30]:
        return self._device_info

    @property
    def status(self) -> str:
        return self._device_status

    def get_ip_channel_count(self) -> int:
        if not self._is_connected or not self._device_info:
            return 0
        return int(self._device_info.byIPChanNum) + int(self._device_info.byHighDChanNum) * 256

    def get_channel_count(self) -> int:
        if not self._is_connected or not self._device_info:
            return 0
        return int(self._device_info.byChanNum) + self.get_ip_channel_count()

    def _get_channel_name_sdk(self, channel_id: int) -> Optional[str]:
        if not self._is_connected:
            return None

        try:
            chan_name = NET_DVR_CHANNAME()
            chan_name.dwSize = ctypes.sizeof(NET_DVR_CHANNAME)
            bytes_returned = ctypes.c_uint32(0)
            result = self._sdk.NET_DVR_GetDVRConfig(
                self.user_id,
                1064,
                channel_id,
                ctypes.byref(chan_name),
                ctypes.sizeof(NET_DVR_CHANNAME),
                ctypes.byref(bytes_returned),
            )
            if result:
                name = self._decode_sdk_text(chan_name.sChanName)
                if name:
                    return name
            else:
                error_code, error_msg = self._get_sdk_error()
                logger.debug(
                    "get_channel_name_failed channel=%s error=%s:%s",
                    channel_id,
                    error_code,
                    error_msg,
                )
        except Exception as exc:
            logger.debug("get_channel_name_exception channel=%s error=%s", channel_id, exc)

        return None

    def _load_channel_metadata(self):
        if self._ip_channel_metadata or not self._is_connected or not self._device_info:
            return

        info = self._device_info
        logger.info(
            "loading_channel_metadata ip=%s analog_channels=%s ip_channels=%s",
            self.ip,
            info.byChanNum,
            self.get_ip_channel_count(),
        )

        if not self._channel_names:
            for i in range(info.byChanNum):
                channel_id = info.byStartChan + i
                name = self._get_channel_name_sdk(channel_id)
                if name:
                    self._channel_names[channel_id] = name

        try:
            if self._isapi_client is None:
                self._isapi_client = ISAPIClient(
                    self.ip,
                    self.http_port,
                    self.username,
                    self.password,
                )

            if self._isapi_client.connect():
                start_dchan = int(info.byStartDChan) if int(info.byStartDChan) > 0 else 33
                proxy_channels = self._isapi_client.get_input_proxy_channels(start_dchan)
                if proxy_channels:
                    self._ip_channel_metadata = {
                        item["sdk_id"]: {**item, "status_source": "isapi"}
                        for item in proxy_channels
                        if item.get("enabled", True)
                    }
                    self._channel_names.update(
                        {
                            item["sdk_id"]: item["name"]
                            for item in proxy_channels
                            if item.get("enabled", True) and item.get("name")
                        }
                    )
                    return
        except Exception as exc:
            logger.warning("isapi_channel_query_failed ip=%s http_port=%s error=%s", self.ip, self.http_port, exc)

        logger.info("isapi_not_available_using_sdk_fallback ip=%s", self.ip)
        ip_channel_count = self.get_ip_channel_count()
        start_dchan = int(info.byStartDChan) if info.byStartDChan > 0 else 33

        for i in range(ip_channel_count):
            channel_id = start_dchan + i
            channel_name = self._get_channel_name_sdk(channel_id)
            if channel_name:
                self._ip_channel_metadata[channel_id] = {
                    "id": i + 1,
                    "sdk_id": channel_id,
                    "name": channel_name,
                    "enabled": True,
                    "configured": True,
                    "has_camera": None,
                    "online": None,
                    "status_source": "sdk-fallback",
                }
                self._channel_names[channel_id] = channel_name

    def _get_channel_display_name(self, channel_id: int) -> str:
        if not self._device_info:
            return f"CH{channel_id}"

        info = self._device_info
        start_dchan = int(info.byStartDChan) if info.byStartDChan > 0 else 33
        start_chan = int(info.byStartChan) if info.byStartChan > 0 else 1

        if info.byChanNum > 0 and channel_id < start_dchan:
            analog_index = channel_id - start_chan + 1
            return f"A{analog_index}" if analog_index > 0 else f"A{channel_id}"

        ip_index = channel_id - start_dchan + 1
        return f"D{ip_index}" if ip_index > 0 else f"D{channel_id}"

    def get_channel_list(self, filter_empty: bool = True) -> List[Dict]:
        channels: List[Dict] = []
        if not self._is_connected or not self._device_info:
            return channels

        self._load_channel_metadata()
        info = self._device_info

        for i in range(info.byChanNum):
            channel_id = info.byStartChan + i
            real_name = self._channel_names.get(channel_id) or f"模拟通道{i + 1}"
            channels.append(
                {
                    "id": channel_id,
                    "channel": channel_id,
                    "display_id": self._get_channel_display_name(channel_id),
                    "name": real_name,
                    "type": "analog",
                    "enabled": True,
                    "configured": True,
                    "has_camera": True,
                    "online": True,
                    "has_device": True,
                    "status_source": "analog",
                }
            )

        if self._ip_channel_metadata:
            for sdk_channel_id, metadata in sorted(self._ip_channel_metadata.items()):
                channel_name = metadata.get("name") or self._channel_names.get(sdk_channel_id)
                if not channel_name:
                    channel_name = self._get_channel_display_name(sdk_channel_id)

                has_camera = metadata.get("has_camera")
                online = metadata.get("online")
                is_enabled = metadata.get("enabled", True)
                configured = metadata.get("configured", is_enabled)
                status_source = metadata.get("status_source", "unknown")

                if filter_empty and has_camera is False:
                    continue

                if status_source == "isapi":
                    if online is True:
                        has_device = True
                    elif online is False:
                        has_device = False
                    else:
                        has_device = None
                else:
                    has_device = None

                channels.append(
                    {
                        "id": sdk_channel_id,
                        "channel": sdk_channel_id,
                        "display_id": self._get_channel_display_name(sdk_channel_id),
                        "name": channel_name,
                        "type": "ip",
                        "enabled": is_enabled,
                        "configured": configured,
                        "has_device": has_device,
                        "has_camera": has_camera,
                        "online": online,
                        "status_source": status_source,
                    }
                )
        else:
            ip_channel_count = self.get_ip_channel_count()
            start_dchan = int(info.byStartDChan)
            for i in range(ip_channel_count):
                channel_id = start_dchan + i
                channel_name = self._channel_names.get(channel_id) or self._get_channel_display_name(channel_id)
                channels.append(
                    {
                        "id": channel_id,
                        "channel": channel_id,
                        "display_id": self._get_channel_display_name(channel_id),
                        "name": channel_name,
                        "type": "ip",
                        "enabled": True,
                        "configured": True,
                        "has_device": None,
                        "has_camera": None,
                        "online": None,
                        "status_source": "sdk-count",
                    }
                )

        return channels

    def find_files(self, channel: int, start: datetime, end: datetime) -> List[Dict]:
        """
        查询指定时间段内的录像文件列表。

        Returns:
            [{"filename": str, "start": datetime, "end": datetime, "size": int}]
        """
        if not self._is_connected:
            raise RuntimeError("未连接到设备")

        from .video_searcher import VideoSearcher

        with VideoSearcher(self.user_id) as searcher:
            files = searcher.search_by_time_v40(channel, start, end)

        return [
            {
                "filename": file_info.filename,
                "start": file_info.start_time,
                "end": file_info.end_time,
                "size": file_info.size,
                "locked": file_info.locked,
            }
            for file_info in files
        ]

    def _wait_for_download(
        self,
        download_handle: int,
        save_path: str,
        progress_callback=None,
        stall_timeout: int = DOWNLOAD_STALL_TIMEOUT,
        timeout: Optional[int] = None,
    ) -> bool:
        last_progress = -1
        last_file_size = -1
        last_change_time = time.time()
        start_time = time.time()

        while True:
            if timeout is not None and time.time() - start_time > timeout:
                raise RuntimeError(f"下载超时，超过 {timeout} 秒")

            pos = int(self._sdk.NET_DVR_GetDownloadPos(download_handle))

            if pos == self.DOWNLOAD_FINISHED:
                time.sleep(1)
                if not os.path.exists(save_path):
                    raise RuntimeError("下载报告完成，但输出文件不存在")

                file_size = os.path.getsize(save_path)
                if file_size < 1024:
                    raise RuntimeError(f"下载文件过小: {file_size} 字节")

                if progress_callback:
                    progress_callback(100)
                return True

            if pos == self.DOWNLOAD_FAILED:
                error_code, error_msg = self._get_sdk_error()
                raise RuntimeError(f"下载失败 [{error_code}]: {error_msg}")

            if pos == self.DOWNLOAD_DISK_FULL:
                raise RuntimeError("下载失败，目标磁盘已满")

            if pos < 0:
                error_code, error_msg = self._get_sdk_error()
                raise RuntimeError(f"获取下载进度失败 [{error_code}]: {error_msg}")

            if pos > 100:
                raise RuntimeError(f"异常下载状态: {pos}")

            current_file_size = os.path.getsize(save_path) if os.path.exists(save_path) else 0
            if pos != last_progress or current_file_size != last_file_size:
                last_progress = pos
                last_file_size = current_file_size
                last_change_time = time.time()
            elif time.time() - last_change_time > stall_timeout:
                raise RuntimeError("下载长时间无进展，已判定为卡死")

            if progress_callback and progress_callback(pos) is False:
                return False

            time.sleep(0.5)

    def download_by_name(
        self,
        channel: int,
        filename: str,
        save_path: str,
        progress_callback=None,
        timeout: int = 3600,
    ) -> bool:
        """
        按设备录像文件名下载。
        """
        if not self._is_connected:
            raise RuntimeError("未连接到设备")

        os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
        path_bytes = self._encode_sdk_text(save_path)
        name_bytes = self._encode_sdk_text(filename)

        download_handle = self._sdk.NET_DVR_GetFileByName(
            self.user_id,
            name_bytes,
            path_bytes,
        )

        if download_handle < 0:
            error_code, error_msg = self._get_sdk_error()
            raise RuntimeError(f"启动下载失败 [{error_code}]: {error_msg}")

        try:
            if not self._sdk.NET_DVR_PlayBackControl(download_handle, self.NET_DVR_PLAYSTART, 0, None):
                error_code, error_msg = self._get_sdk_error()
                raise RuntimeError(f"启动下载播放失败 [{error_code}]: {error_msg}")

            return self._wait_for_download(
                download_handle,
                save_path,
                progress_callback=progress_callback,
                timeout=timeout,
            )
        finally:
            self._sdk.NET_DVR_StopGetFile(download_handle)

    def start_preview(self, channel_id: int, play_hwnd: int = 0) -> int:
        if not self._is_connected:
            if self._auto_reconnect_enabled:
                self._set_channel_status(channel_id, ChannelStatus.RECONNECTING)
                if self._reconnect_timer and not self._reconnect_timer.isActive():
                    self._reconnect_timer.start(self.RECONNECT_INTERVAL * 1000)
                raise RuntimeError("设备未连接，正在尝试重连...")
            raise RuntimeError("未连接到设备")

        if channel_id in self._preview_handles:
            self.stop_preview(channel_id)

        self._set_channel_status(channel_id, ChannelStatus.RECONNECTING)

        preview_info = NET_DVR_PREVIEWINFO()
        preview_info.lChannel = channel_id
        preview_info.dwStreamType = 0
        preview_info.dwLinkMode = 0
        preview_info.hPlayWnd = ctypes.c_void_p(play_hwnd)
        preview_info.bBlocked = True
        preview_info.bPassbackRecord = False
        preview_info.byPreviewMode = 0
        preview_info.dwDisplayBufNum = 15

        handle = self._sdk.NET_DVR_RealPlay_V40(
            self.user_id,
            ctypes.byref(preview_info),
            None,
            None,
        )

        if handle < 0:
            error_code, error_msg = self._get_sdk_error()
            if error_code == 4:
                detail = "通道号错误，该通道可能不存在"
            elif error_code == 19:
                detail = "通道资源已被占用"
            else:
                detail = error_msg

            self._set_channel_status(channel_id, ChannelStatus.ERROR)
            raise RuntimeError(f"启动预览失败 [{error_code}]: {detail}")

        self._preview_handles[channel_id] = handle
        if channel_id in self._channels_pending_restore:
            self._channels_pending_restore.remove(channel_id)
        self._set_channel_status(channel_id, ChannelStatus.PREVIEWING)
        return handle

    def stop_preview(self, channel_id: int):
        if channel_id in self._channels_pending_restore:
            self._channels_pending_restore.remove(channel_id)

        if channel_id not in self._preview_handles:
            return

        handle = self._preview_handles[channel_id]
        if not self._sdk.NET_DVR_StopRealPlay(handle):
            error_code, error_msg = self._get_sdk_error()
            logger.warning(
                "preview_stop_failed ip=%s channel=%s handle=%s error=%s:%s",
                self.ip,
                channel_id,
                handle,
                error_code,
                error_msg,
            )
            return

        self._preview_handles.pop(channel_id, None)
        if self._is_connected:
            self._set_channel_status(channel_id, ChannelStatus.ONLINE)
        else:
            self._set_channel_status(channel_id, ChannelStatus.OFFLINE)

    def stop_all_previews(self):
        for channel_id in list(self._preview_handles.keys()):
            self.stop_preview(channel_id)

    def get_device_info_dict(self) -> dict:
        if not self._device_info:
            return {}

        serial = bytes(self._device_info.sSerialNumber).decode("utf-8", errors="ignore").strip("\x00")

        device_types = {
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
        device_type = device_types.get(self._device_info.byDVRType, f"未知({self._device_info.byDVRType})")
        analog = int(self._device_info.byChanNum)
        ip = self.get_ip_channel_count()

        return {
            "ip": self.ip,
            "port": self.port,
            "http_port": self.http_port,
            "username": self.username,
            "serial": serial,
            "serial_number": serial,
            "device_type": device_type,
            "analog_channels": analog,
            "ip_channels": ip,
            "total_channels": analog + ip,
            "channels": self.get_channel_list(filter_empty=True),
        }
