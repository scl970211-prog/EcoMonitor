# -*- coding: utf-8 -*-
"""
视频预览管理器 V2 - 支持实际视频渲染
整合 SDK 预览和视频解码显示
"""

import ctypes
import logging
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QImage

from ..sdk_loader import SDKLoader
from .video_decoder import VideoDecoder, VideoFrame

logger = logging.getLogger(__name__)


class PreviewState(Enum):
    """预览状态"""
    IDLE = "idle"
    CONNECTING = "connecting"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class PreviewContext:
    """预览上下文"""
    channel: int
    user_id: int
    real_handle: int
    decoder: Optional[VideoDecoder] = None
    state: PreviewState = PreviewState.IDLE
    error_msg: str = ""


class RealDataCallback(QThread):
    """
    实时数据接收线程
    SDK 预览数据回调在独立线程中处理
    """
    
    data_received = pyqtSignal(int, bytes)  # channel, data
    
    def __init__(self, channel: int):
        super().__init__()
        self.channel = channel
        self._running = False
        self._buffer = bytearray()
        
    def run(self):
        """线程运行"""
        self._running = True
        logger.debug(f"数据接收线程启动: 通道{self.channel}")
        
        # 这个线程主要用于信号处理
        # 实际数据通过 SDK 回调接收
        while self._running:
            self.msleep(10)
        
        logger.debug(f"数据接收线程结束: 通道{self.channel}")
    
    def stop(self):
        """停止线程"""
        self._running = False
        self.wait(1000)
    
    def on_data(self, data: bytes):
        """接收到数据"""
        self.data_received.emit(self.channel, data)


class PreviewManagerV2(QObject):
    """
    视频预览管理器 V2
    支持多通道预览和实际视频渲染
    """
    
    # 信号
    frame_ready = pyqtSignal(int, object)  # channel, QImage
    preview_started = pyqtSignal(int)       # channel
    preview_stopped = pyqtSignal(int)       # channel
    preview_error = pyqtSignal(int, str)    # channel, error_msg
    state_changed = pyqtSignal(int, str)    # channel, state
    
    def __init__(self):
        super().__init__()
        
        self._sdk = None
        self._previews: Dict[int, PreviewContext] = {}  # channel -> context
        self._real_data_callbacks: Dict[int, Callable] = {}  # channel -> callback
        
        # 定时器用于更新状态
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._check_previews_status)
        self._status_timer.start(1000)  # 每秒检查一次
        
    def initialize(self) -> bool:
        """初始化管理器"""
        try:
            self._sdk = SDKLoader()
            if not self._sdk.load():
                logger.error("SDK 加载失败")
                return False
            
            logger.info("预览管理器 V2 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"预览管理器初始化失败: {e}")
            return False
    
    def start_preview(self, user_id: int, channel: int, stream_type: int = 0,
                     hwnd: int = 0) -> bool:
        """
        开始预览
        
        Args:
            user_id: SDK 用户 ID
            channel: 通道号
            stream_type: 码流类型 (0=主, 1=子, 2=三)
            hwnd: 窗口句柄 (保留兼容，实际不使用)
        """
        if channel in self._previews:
            logger.warning(f"通道 {channel} 已经在预览中")
            return False
        
        try:
            # 创建解码器
            decoder = VideoDecoder()
            if not decoder.initialize():
                raise RuntimeError("解码器初始化失败")
            
            # 连接帧解码信号
            decoder.frame_decoded.connect(
                lambda frame: self._on_frame_decoded(channel, frame)
            )
            
            # 设置预览参数
            preview_info = self._sdk.NET_DVR_PREVIEWINFO()
            preview_info.lChannel = channel
            preview_info.dwStreamType = stream_type
            preview_info.dwLinkMode = 0  # TCP
            preview_info.hPlayWnd = 0    # 不使用 SDK 显示
            
            # 创建实时数据回调
            callback = self._create_real_data_callback(channel, decoder)
            self._real_data_callbacks[channel] = callback
            
            # 开始预览
            real_handle = self._sdk.NET_DVR_RealPlay_V40(
                user_id,
                ctypes.byref(preview_info),
                callback,
                None,
                0
            )
            
            if real_handle < 0:
                error_code = self._sdk.NET_DVR_GetLastError()
                decoder.shutdown()
                raise RuntimeError(f"开始预览失败，错误码: {error_code}")
            
            # 开始解码
            decoder.start()
            
            # 保存上下文
            context = PreviewContext(
                channel=channel,
                user_id=user_id,
                real_handle=real_handle,
                decoder=decoder,
                state=PreviewState.PLAYING
            )
            self._previews[channel] = context
            
            logger.info(f"通道 {channel} 预览已开始，句柄: {real_handle}")
            self.preview_started.emit(channel)
            self.state_changed.emit(channel, PreviewState.PLAYING.value)
            
            return True
            
        except Exception as e:
            logger.error(f"开始预览失败: {e}")
            self.preview_error.emit(channel, str(e))
            return False
    
    def stop_preview(self, channel: int):
        """停止预览"""
        if channel not in self._previews:
            return
        
        context = self._previews[channel]
        
        try:
            # 停止解码
            if context.decoder:
                context.decoder.stop()
                context.decoder.shutdown()
            
            # 停止预览
            if context.real_handle >= 0:
                self._sdk.NET_DVR_StopRealPlay(context.real_handle)
            
            # 清理回调
            if channel in self._real_data_callbacks:
                del self._real_data_callbacks[channel]
            
            # 移除上下文
            del self._previews[channel]
            
            logger.info(f"通道 {channel} 预览已停止")
            self.preview_stopped.emit(channel)
            self.state_changed.emit(channel, PreviewState.IDLE.value)
            
        except Exception as e:
            logger.error(f"停止预览时出错: {e}")
    
    def stop_all_previews(self):
        """停止所有预览"""
        channels = list(self._previews.keys())
        for channel in channels:
            self.stop_preview(channel)
    
    def pause_preview(self, channel: int) -> bool:
        """暂停预览"""
        if channel not in self._previews:
            return False
        
        context = self._previews[channel]
        
        # 使用 SDK 暂停
        result = self._sdk.NET_DVR_RealPlayPause(context.real_handle, 1)
        if result:
            context.state = PreviewState.PAUSED
            self.state_changed.emit(channel, PreviewState.PAUSED.value)
        
        return result
    
    def resume_preview(self, channel: int) -> bool:
        """恢复预览"""
        if channel not in self._previews:
            return False
        
        context = self._previews[channel]
        
        # 使用 SDK 恢复
        result = self._sdk.NET_DVR_RealPlayPause(context.real_handle, 0)
        if result:
            context.state = PreviewState.PLAYING
            self.state_changed.emit(channel, PreviewState.PLAYING.value)
        
        return result
    
    def get_preview_state(self, channel: int) -> PreviewState:
        """获取预览状态"""
        if channel not in self._previews:
            return PreviewState.IDLE
        return self._previews[channel].state
    
    def is_previewing(self, channel: int) -> bool:
        """是否正在预览"""
        return channel in self._previews and \
               self._previews[channel].state == PreviewState.PLAYING
    
    def get_active_channels(self) -> List[int]:
        """获取所有活动通道"""
        return list(self._previews.keys())
    
    def _create_real_data_callback(self, channel: int, decoder: VideoDecoder):
        """创建实时数据回调函数"""
        
        @ctypes.WINFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte),
                           ctypes.c_uint, ctypes.c_void_p)
        def callback(real_handle, data_ptr, data_len, user_data):
            try:
                # 复制数据
                data = ctypes.string_at(data_ptr, data_len)
                
                # 输入到解码器
                decoder.input_data(data)
                
            except Exception as e:
                logger.error(f"实时数据回调处理错误: {e}")
        
        return callback
    
    def _on_frame_decoded(self, channel: int, frame: VideoFrame):
        """帧解码完成"""
        try:
            # 转换为 QImage
            image = frame.to_qimage()
            
            # 发射信号
            self.frame_ready.emit(channel, image)
            
        except Exception as e:
            logger.error(f"处理解码帧失败: {e}")
    
    def _check_previews_status(self):
        """检查预览状态"""
        for channel, context in list(self._previews.items()):
            # 检查是否连接正常
            if context.real_handle >= 0:
                # 这里可以添加更多的状态检查
                pass


# 全局实例
_preview_manager_v2 = None

def get_preview_manager_v2() -> PreviewManagerV2:
    """获取预览管理器 V2 全局实例"""
    global _preview_manager_v2
    if _preview_manager_v2 is None:
        _preview_manager_v2 = PreviewManagerV2()
    return _preview_manager_v2
