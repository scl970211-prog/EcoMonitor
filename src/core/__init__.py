"""
核心模块 - SDK 封装和业务逻辑 (PyQt6 整合版)

说明：
- 本包默认只导出不依赖 PyQt6 的基础工具（如 path_resolver）。
- 依赖 PyQt6 的模块（Device、DownloadManager 等）采用延迟导入，
  避免在仅需要基础工具时强制加载 Qt 运行时。
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
    check_ffmpeg_exists,
)

# 延迟加载的模块映射：名称 -> (模块路径, 导出名称)
_LAZY_IMPORTS = {
    "SDKLoader": (".sdk_loader", "SDKLoader"),
    "get_error_message": (".sdk_loader", "get_error_message"),
    "NET_DVR_DEVICEINFO_V30": (".sdk_loader", "NET_DVR_DEVICEINFO_V30"),
    "NET_DVR_TIME": (".sdk_loader", "NET_DVR_TIME"),
    "Device": (".device", "Device"),
    "DeviceStatus": (".device", "DeviceStatus"),
    "ChannelStatus": (".device", "ChannelStatus"),
    "DeviceInfo": (".device", "DeviceInfo"),
    "DownloadManager": (".download_manager", "DownloadManager"),
    "DownloadTask": (".download_task", "DownloadTask"),
    "VideoPreview": (".video_preview", "VideoPreview"),
    "PreviewManager": (".video_preview", "PreviewManager"),
    "VideoDownloadWorker": (".video_download", "VideoDownloadWorker"),
    "convert_hik_to_mp4": (".video_download", "convert_hik_to_mp4"),
    "VideoSearcher": (".video_searcher", "VideoSearcher"),
    "RecordFile": (".video_searcher", "RecordFile"),
    "search_device_recordings": (".video_searcher", "search_device_recordings"),
    "FormatConverter": (".format_converter", "FormatConverter"),
    "SegmentDownloadManager": (".segment_download", "SegmentDownloadManager"),
    "SegmentTaskConfig": (".segment_download", "SegmentTaskConfig"),
    "DownloadSegment": (".segment_download", "DownloadSegment"),
    "SegmentStatus": (".segment_download", "SegmentStatus"),
    "get_segment_manager": (".segment_download", "get_segment_manager"),
    "AppState": (".app_state", "AppState"),
    "DeviceState": (".app_state", "DeviceState"),
    "DownloadTaskState": (".app_state", "DownloadTaskState"),
    "ChannelInfo": (".app_state", "ChannelInfo"),
    "DownloadTaskInfo": (".app_state", "DownloadTaskInfo"),
    "get_app_state": (".app_state", "get_app_state"),
    "EventBus": (".event_bus", "EventBus"),
    "Event": (".event_bus", "Event"),
    "EventType": (".event_bus", "EventType"),
    "get_event_bus": (".event_bus", "get_event_bus"),
}


def __getattr__(name: str):
    """延迟加载依赖 PyQt6 的核心类，降低导入开销。"""
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module 'src.core' has no attribute '{name}'")
    module_path, attr_name = _LAZY_IMPORTS[name]
    import importlib

    full_module_path = f"src.core{module_path}"
    module = importlib.import_module(full_module_path)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "PathResolver",
    "get_base_dir",
    "get_sdk_path",
    "get_db_path",
    "get_temp_dir",
    "get_config_path",
    "get_log_dir",
    "check_sdk_exists",
    "check_ffmpeg_exists",
    "SDKLoader",
    "get_error_message",
    "NET_DVR_DEVICEINFO_V30",
    "NET_DVR_TIME",
    "Device",
    "DeviceStatus",
    "ChannelStatus",
    "DeviceInfo",
    "DownloadManager",
    "DownloadTask",
    "VideoPreview",
    "PreviewManager",
    "VideoDownloadWorker",
    "convert_hik_to_mp4",
    "VideoSearcher",
    "RecordFile",
    "search_device_recordings",
    "FormatConverter",
    "SegmentDownloadManager",
    "SegmentTaskConfig",
    "DownloadSegment",
    "SegmentStatus",
    "get_segment_manager",
    "AppState",
    "DeviceState",
    "DownloadTaskState",
    "ChannelInfo",
    "DownloadTaskInfo",
    "get_app_state",
    "EventBus",
    "Event",
    "EventType",
    "get_event_bus",
]
