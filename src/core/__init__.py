"""
核心模块 - SDK 封装和业务逻辑 (PyQt6 整合版)
"""

from .path_resolver import (
    PathResolver, 
    get_base_dir, 
    get_sdk_path, 
    get_db_path, 
    get_temp_dir,
    get_config_path,
    get_log_dir,
    check_sdk_exists,
    check_ffmpeg_exists
)
from .sdk_loader import SDKLoader, get_error_message, NET_DVR_DEVICEINFO_V30, NET_DVR_TIME
from .device import Device, DeviceStatus, ChannelStatus, DeviceInfo
from .download_manager import DownloadManager
from .download_task import DownloadTask
from .video_preview import VideoPreview, PreviewManager
from .video_download import VideoDownloadWorker, convert_hik_to_mp4
from .video_searcher import VideoSearcher, RecordFile, search_device_recordings
from .format_converter import FormatConverter

# 新增模块
from .segment_download import (
    SegmentDownloadManager,
    SegmentTaskConfig,
    DownloadSegment,
    SegmentStatus,
    get_segment_manager,
)
from .app_state import (
    AppState,
    DeviceState,
    DownloadTaskState,
    ChannelInfo,
    DownloadTaskInfo,
    get_app_state,
)
from .event_bus import (
    EventBus,
    Event,
    EventType,
    get_event_bus,
)

__all__ = [
    'PathResolver',
    'get_base_dir',
    'get_sdk_path',
    'get_db_path',
    'get_temp_dir',
    'get_config_path',
    'get_log_dir',
    'check_sdk_exists',
    'check_ffmpeg_exists',
    'SDKLoader',
    'get_error_message',
    'NET_DVR_DEVICEINFO_V30',
    'NET_DVR_TIME',
    'Device',
    'DeviceStatus',
    'ChannelStatus',
    'DeviceInfo',
    'DownloadManager',
    'DownloadTask',
    'VideoPreview',
    'PreviewManager',
    'VideoDownloadWorker',
    'convert_hik_to_mp4',
    'VideoSearcher',
    'RecordFile',
    'search_device_recordings',
    'FormatConverter',
    # 新增导出
    'SegmentDownloadManager',
    'SegmentTaskConfig',
    'DownloadSegment',
    'SegmentStatus',
    'get_segment_manager',
    'AppState',
    'DeviceState',
    'DownloadTaskState',
    'ChannelInfo',
    'DownloadTaskInfo',
    'get_app_state',
    'EventBus',
    'Event',
    'EventType',
    'get_event_bus',
]
