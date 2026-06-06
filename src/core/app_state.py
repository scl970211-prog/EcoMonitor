# -*- coding: utf-8 -*-
"""
全局状态管理模块
集中管理应用状态，实现跨模块状态共享
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from PyQt6.QtCore import QObject, pyqtSignal

from .device import Device

logger = logging.getLogger(__name__)


class DeviceState(Enum):
    """设备状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class DownloadTaskState(Enum):
    """下载任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PreviewState(Enum):
    """预览状态。"""

    IDLE = "idle"
    CONNECTING = "connecting"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class ChannelInfo:
    """通道信息"""
    channel_id: int
    name: str = ""
    is_online: bool = True
    is_recording: bool = False
    preview_state: PreviewState = PreviewState.IDLE
    

@dataclass
class DownloadTaskInfo:
    """下载任务信息"""
    task_id: str
    channel: int
    start_time: Any  # datetime
    end_time: Any    # datetime
    state: DownloadTaskState = DownloadTaskState.PENDING
    progress: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: int = 0  # bytes/s
    error_msg: str = ""


class AppState(QObject):
    """
    应用全局状态管理器（单例）
    集中管理所有模块共享的状态
    """
    
    # ========== 设备相关信号 ==========
    device_state_changed = pyqtSignal(str)  # new_state
    device_connected = pyqtSignal(dict)     # device_info
    device_disconnected = pyqtSignal()
    device_error = pyqtSignal(str)          # error_msg
    
    # ========== 通道相关信号 ==========
    channel_list_updated = pyqtSignal(list)  # List[ChannelInfo]
    channel_state_changed = pyqtSignal(int, str)  # channel_id, state
    
    # ========== 预览相关信号 ==========
    preview_started = pyqtSignal(int)       # channel_id
    preview_stopped = pyqtSignal(int)       # channel_id
    preview_error = pyqtSignal(int, str)    # channel_id, error
    
    # ========== 下载相关信号 ==========
    download_task_added = pyqtSignal(str)   # task_id
    download_task_removed = pyqtSignal(str) # task_id
    download_task_state_changed = pyqtSignal(str, str)  # task_id, state
    download_progress_updated = pyqtSignal(str, int, int, int)  # task_id, progress, speed, eta
    
    # ========== 系统信号 ==========
    error_occurred = pyqtSignal(str, str)   # source, message
    notification = pyqtSignal(str, str)     # level, message
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        super().__init__()
        
        if hasattr(self, '_initialized'):
            return
        
        # 设备状态
        self._device: Optional[Device] = None
        self._device_info: Dict = {}
        self._device_state = DeviceState.DISCONNECTED
        
        # 通道状态
        self._channels: Dict[int, ChannelInfo] = {}
        
        # 预览状态
        self._active_previews: Dict[int, dict] = {}  # channel_id -> preview_info
        
        # 下载状态
        self._download_tasks: Dict[str, DownloadTaskInfo] = {}
        
        # 状态监听器
        self._listeners: Dict[str, List[Callable]] = {}
        
        self._initialized = True
        logger.info("AppState 初始化完成")
    
    # ========== 设备状态管理 ==========
    
    @property
    def device(self) -> Optional[Device]:
        """获取当前设备"""
        return self._device
    
    @property
    def device_info(self) -> Dict:
        """获取设备信息"""
        return self._device_info.copy()
    
    @property
    def device_state(self) -> DeviceState:
        """获取设备状态"""
        return self._device_state
    
    @property
    def is_device_connected(self) -> bool:
        """设备是否已连接"""
        return self._device_state == DeviceState.CONNECTED and self._device is not None
    
    def set_device(self, device: Optional[Device], device_info: Dict = None):
        """
        设置当前设备
        
        Args:
            device: 设备实例或 None（断开）
            device_info: 设备信息字典
        """
        old_device = self._device
        
        if device is None:
            # 断开设备
            self._device = None
            self._device_info = {}
            self._device_state = DeviceState.DISCONNECTED
            self._channels.clear()
            self._active_previews.clear()
            
            if old_device is not None:
                self.device_disconnected.emit()
                self.device_state_changed.emit(DeviceState.DISCONNECTED.value)
                logger.info("设备已断开")
        else:
            # 连接新设备
            self._device = device
            self._device_info = device_info or {}
            self._device_state = DeviceState.CONNECTED
            
            self.device_connected.emit(self._device_info)
            self.device_state_changed.emit(DeviceState.CONNECTED.value)
            logger.info(f"设备已连接: {device_info.get('ip', 'Unknown')}")
    
    def set_device_state(self, state: DeviceState, error_msg: str = ""):
        """设置设备状态"""
        old_state = self._device_state
        self._device_state = state
        
        if old_state != state:
            self.device_state_changed.emit(state.value)
            
            if state == DeviceState.ERROR:
                self.device_error.emit(error_msg)
                self.error_occurred.emit("device", error_msg)
    
    # ========== 通道状态管理 ==========
    
    def update_channel_list(self, channels: List[Dict]):
        """
        更新通道列表
        
        Args:
            channels: 通道信息列表，每个通道包含 id, name, online 等
        """
        self._channels.clear()
        
        for ch in channels:
            channel_id = ch.get("id", 0)
            self._channels[channel_id] = ChannelInfo(
                channel_id=channel_id,
                name=ch.get("name", f"通道{channel_id}"),
                is_online=ch.get("online", True),
                is_recording=ch.get("recording", False),
            )
        
        self.channel_list_updated.emit(list(self._channels.values()))
        logger.info(f"通道列表已更新: {len(channels)} 个通道")
    
    def get_channel_info(self, channel_id: int) -> Optional[ChannelInfo]:
        """获取通道信息"""
        return self._channels.get(channel_id)
    
    def set_channel_preview_state(self, channel_id: int, state: PreviewState):
        """设置通道预览状态"""
        if channel_id in self._channels:
            self._channels[channel_id].preview_state = state
            self.channel_state_changed.emit(channel_id, state.value)
    
    # ========== 预览状态管理 ==========
    
    def start_preview(self, channel_id: int, preview_handle: int = -1,
                     stream_type: int = 0):
        """开始预览"""
        self._active_previews[channel_id] = {
            "handle": preview_handle,
            "stream_type": stream_type,
            "start_time": None,  # 可添加时间戳
        }
        
        self.set_channel_preview_state(channel_id, PreviewState.PLAYING)
        self.preview_started.emit(channel_id)
        logger.debug(f"预览开始: 通道 {channel_id}")
    
    def stop_preview(self, channel_id: int):
        """停止预览"""
        if channel_id in self._active_previews:
            del self._active_previews[channel_id]
        
        self.set_channel_preview_state(channel_id, PreviewState.IDLE)
        self.preview_stopped.emit(channel_id)
        logger.debug(f"预览停止: 通道 {channel_id}")
    
    def set_preview_error(self, channel_id: int, error_msg: str):
        """设置预览错误"""
        self.set_channel_preview_state(channel_id, PreviewState.ERROR)
        self.preview_error.emit(channel_id, error_msg)
    
    def is_previewing(self, channel_id: int) -> bool:
        """通道是否正在预览"""
        return channel_id in self._active_previews
    
    def get_active_preview_channels(self) -> List[int]:
        """获取所有正在预览的通道"""
        return list(self._active_previews.keys())
    
    # ========== 下载状态管理 ==========
    
    def add_download_task(self, task_info: DownloadTaskInfo):
        """添加下载任务"""
        self._download_tasks[task_info.task_id] = task_info
        self.download_task_added.emit(task_info.task_id)
        logger.info(f"下载任务已添加: {task_info.task_id}")
    
    def remove_download_task(self, task_id: str):
        """移除下载任务"""
        if task_id in self._download_tasks:
            del self._download_tasks[task_id]
            self.download_task_removed.emit(task_id)
    
    def get_download_task(self, task_id: str) -> Optional[DownloadTaskInfo]:
        """获取下载任务信息"""
        return self._download_tasks.get(task_id)
    
    def get_all_download_tasks(self) -> List[DownloadTaskInfo]:
        """获取所有下载任务"""
        return list(self._download_tasks.values())
    
    def update_download_state(self, task_id: str, state: DownloadTaskState):
        """更新下载状态"""
        if task_id in self._download_tasks:
            self._download_tasks[task_id].state = state
            self.download_task_state_changed.emit(task_id, state.value)
    
    def update_download_progress(self, task_id: str, progress: int,
                                  speed: int = 0, eta: int = 0):
        """更新下载进度"""
        if task_id in self._download_tasks:
            task = self._download_tasks[task_id]
            task.progress = progress
            task.speed = speed
            self.download_progress_updated.emit(task_id, progress, speed, eta)
    
    def pause_download(self, task_id: str):
        """暂停下载"""
        self.update_download_state(task_id, DownloadTaskState.PAUSED)
    
    def resume_download(self, task_id: str):
        """恢复下载"""
        self.update_download_state(task_id, DownloadTaskState.RUNNING)
    
    # ========== 监听器管理 ==========
    
    def add_listener(self, event: str, callback: Callable):
        """
        添加状态监听器
        
        Args:
            event: 事件名称，如 'device_connected', 'preview_started'
            callback: 回调函数
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
    
    def remove_listener(self, event: str, callback: Callable):
        """移除监听器"""
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)
    
    def notify_listeners(self, event: str, *args, **kwargs):
        """通知监听器"""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"监听器回调错误: {e}")
    
    # ========== 便捷方法 ==========
    
    def show_notification(self, message: str, level: str = "info"):
        """显示通知"""
        self.notification.emit(level, message)
    
    def show_error(self, source: str, message: str):
        """显示错误"""
        self.error_occurred.emit(source, message)
        logger.error(f"[{source}] {message}")
    
    def reset(self):
        """重置所有状态（用于退出登录等）"""
        self._device = None
        self._device_info = {}
        self._device_state = DeviceState.DISCONNECTED
        self._channels.clear()
        self._active_previews.clear()
        self._download_tasks.clear()
        
        logger.info("AppState 已重置")


# 全局实例获取函数
_app_state = None

def get_app_state() -> AppState:
    """获取全局状态实例"""
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state
