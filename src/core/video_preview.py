"""
视频预览模块 - 设备 SDK 实时预览封装
"""

import ctypes
import ctypes.wintypes
import logging
import threading
from typing import Optional, Callable, Dict, List
from PyQt6.QtCore import QObject, pyqtSignal

from .sdk_loader import SDKLoader, NET_DVR_PREVIEWINFO, NET_DVR_TIME

logger = logging.getLogger(__name__)


class VideoPreview(QObject):
    """视频预览控制器"""
    
    # 信号
    started = pyqtSignal(int)      # channel
    stopped = pyqtSignal(int)      # channel
    error = pyqtSignal(str)        # error message
    frame_received = pyqtSignal(bytes)  # video frame data
    
    def __init__(self, user_id: int):
        super().__init__()
        self._user_id = user_id
        self._sdk = SDKLoader()
        self._handle: int = -1
        self._channel: int = 0
        self._lock = threading.Lock()
        self._callback = None
    
    def start_preview(self, channel: int, hwnd: int = 0, stream_type: int = 0) -> bool:
        """
        开始实时预览
        
        Args:
            channel: 通道号
            hwnd: 窗口句柄（0 表示只回调不显示）
            stream_type: 0-主码流, 1-子码流, 2-三码流
        
        Returns:
            是否成功
        """
        with self._lock:
            if self._handle >= 0:
                logger.warning(f"预览已在运行，通道: {self._channel}")
                return False
            
            if not self._sdk.is_loaded:
                logger.error("SDK 未加载")
                return False
            
            # 创建预览参数
            preview_info = NET_DVR_PREVIEWINFO()
            preview_info.lChannel = channel
            preview_info.dwStreamType = stream_type
            preview_info.dwLinkMode = 0  # TCP
            preview_info.hPlayWnd = ctypes.c_void_p(hwnd) if hwnd else None
            preview_info.bBlocked = True
            preview_info.bPassbackRecord = False
            preview_info.byPreviewMode = 0
            preview_info.dwDisplayBufNum = 15
            
            # 开始预览
            handle = self._sdk.real_play(self._user_id, preview_info)
            
            if handle < 0:
                error_code = self._sdk.get_last_error()
                error_msg = f"开始预览失败，错误码: {error_code}"
                logger.error(error_msg)
                self.error.emit(error_msg)
                return False
            
            self._handle = handle
            self._channel = channel
            
            logger.info(f"开始预览通道 {channel}，句柄: {handle}")
            self.started.emit(channel)
            return True
    
    def stop_preview(self) -> bool:
        """停止预览"""
        with self._lock:
            if self._handle < 0:
                return True
            
            success = self._sdk.stop_real_play(self._handle)
            
            if success:
                logger.info(f"停止预览通道 {self._channel}")
                self.stopped.emit(self._channel)
                self._handle = -1
                self._channel = 0
            else:
                error_code = self._sdk.get_last_error()
                logger.error(f"停止预览失败，错误码: {error_code}")
            
            return success
    
    def is_previewing(self) -> bool:
        """是否正在预览"""
        return self._handle >= 0
    
    @property
    def channel(self) -> int:
        """当前通道"""
        return self._channel
    
    @property
    def handle(self) -> int:
        """预览句柄"""
        return self._handle


class PreviewManager(QObject):
    """预览管理器 - 管理多个通道预览"""
    
    preview_started = pyqtSignal(int)   # channel
    preview_stopped = pyqtSignal(int)   # channel
    preview_error = pyqtSignal(int, str)  # channel, error
    
    def __init__(self, user_id: int, max_previews: int = 4):
        super().__init__()
        self._user_id = user_id
        self._max_previews = max_previews
        self._previews: Dict[int, 'VideoPreview'] = {}  # channel -> preview
        self._lock = threading.Lock()
    
    def start_preview(self, channel: int, hwnd: int = 0) -> bool:
        """开始预览"""
        with self._lock:
            # 检查是否已存在
            if channel in self._previews:
                preview = self._previews[channel]
                if preview.is_previewing():
                    logger.warning(f"通道 {channel} 已在预览中")
                    return True
                else:
                    del self._previews[channel]
            
            # 检查最大数量
            if len(self._previews) >= self._max_previews:
                logger.warning(f"已达到最大预览数量: {self._max_previews}")
                return False
            
            # 创建新预览
            preview = VideoPreview(self._user_id)
            preview.started.connect(self.preview_started.emit)
            preview.stopped.connect(lambda ch: self._on_preview_stopped(ch))
            preview.error.connect(lambda msg: self.preview_error.emit(channel, msg))
            
            if preview.start_preview(channel, hwnd):
                self._previews[channel] = preview
                return True
            return False
    
    def stop_preview(self, channel: int) -> bool:
        """停止预览"""
        with self._lock:
            preview = self._previews.get(channel)
            if preview:
                success = preview.stop_preview()
                if success:
                    del self._previews[channel]
                return success
            return True
    
    def stop_all(self):
        """停止所有预览"""
        with self._lock:
            channels = list(self._previews.keys())
        
        for channel in channels:
            self.stop_preview(channel)
    
    def _on_preview_stopped(self, channel: int):
        """预览停止回调"""
        with self._lock:
            if channel in self._previews:
                del self._previews[channel]
        self.preview_stopped.emit(channel)
    
    def is_previewing(self, channel: int) -> bool:
        """指定通道是否在预览"""
        preview = self._previews.get(channel)
        return preview.is_previewing() if preview else False
    
    def get_previewing_channels(self) -> List[int]:
        """获取正在预览的通道列表"""
        with self._lock:
            return [ch for ch, p in self._previews.items() if p.is_previewing()]
    
    def get_preview_count(self) -> int:
        """获取预览数量"""
        with self._lock:
            return len(self._previews)
