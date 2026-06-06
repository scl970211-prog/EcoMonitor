# -*- coding: utf-8 -*-
"""
视频解码器 - 将设备视频流转换为可显示的帧
"""

import ctypes
import logging
import numpy as np
from typing import Optional, Callable
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

logger = logging.getLogger(__name__)


class VideoFrame:
    """视频帧数据"""
    
    def __init__(self, width: int, height: int, data: bytes, timestamp: int = 0):
        self.width = width
        self.height = height
        self.data = data
        self.timestamp = timestamp
        self._image = None
    
    def to_qimage(self) -> QImage:
        """转换为 QImage"""
        if self._image is None:
            # YUV420P 格式转换为 RGB
            rgb_data = self._yuv420p_to_rgb(self.data, self.width, self.height)
            self._image = QImage(rgb_data, self.width, self.height, 
                                self.width * 3, QImage.Format.Format_RGB888)
        return self._image
    
    def to_numpy(self) -> np.ndarray:
        """转换为 numpy 数组 (RGB)"""
        rgb_data = self._yuv420p_to_rgb(self.data, self.width, self.height)
        return np.frombuffer(rgb_data, dtype=np.uint8).reshape((self.height, self.width, 3))
    
    @staticmethod
    def _yuv420p_to_rgb(yuv_data: bytes, width: int, height: int) -> bytes:
        """
        YUV420P 格式转换为 RGB24
        
        YUV420P 布局:
        - Y: width * height
        - U: (width//2) * (height//2)
        - V: (width//2) * (height//2)
        """
        try:
            frame_size = width * height
            uv_size = frame_size // 4
            
            if len(yuv_data) < frame_size + 2 * uv_size:
                # 数据不足，返回黑色帧
                return b'\x00' * (width * height * 3)
            
            y = np.frombuffer(yuv_data[0:frame_size], dtype=np.uint8).reshape((height, width))
            u = np.frombuffer(yuv_data[frame_size:frame_size + uv_size], dtype=np.uint8).reshape((height // 2, width // 2))
            v = np.frombuffer(yuv_data[frame_size + uv_size:], dtype=np.uint8).reshape((height // 2, width // 2))
            
            # 上采样 U, V 到完整分辨率
            u_full = np.repeat(np.repeat(u, 2, axis=0), 2, axis=1)
            v_full = np.repeat(np.repeat(v, 2, axis=0), 2, axis=1)
            
            # YUV 到 RGB 转换
            y = y.astype(np.int32)
            u_full = u_full.astype(np.int32) - 128
            v_full = v_full.astype(np.int32) - 128
            
            r = np.clip(y + 1.402 * v_full, 0, 255).astype(np.uint8)
            g = np.clip(y - 0.344136 * u_full - 0.714136 * v_full, 0, 255).astype(np.uint8)
            b = np.clip(y + 1.772 * u_full, 0, 255).astype(np.uint8)
            
            # 合并 RGB
            rgb = np.stack([r, g, b], axis=-1)
            return rgb.tobytes()
            
        except Exception as e:
            logger.error(f"YUV 转换失败: {e}")
            return b'\x00' * (width * height * 3)


class VideoDecoder(QObject):
    """
    视频解码器
    接收设备视频流并解码为可显示的帧
    """
    
    # 信号
    frame_decoded = pyqtSignal(object)  # VideoFrame
    decode_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._playctrl = None
        self._port = -1
        self._is_running = False
        self._frame_callback: Optional[Callable] = None
        
    def initialize(self) -> bool:
        """初始化解码器"""
        try:
            from .playctrl_sdk import get_playctrl_sdk
            
            self._playctrl = get_playctrl_sdk()
            if not self._playctrl.load():
                self.decode_error.emit("PlayCtrl SDK 加载失败")
                return False
            
            # 获取播放端口
            self._port = self._playctrl.get_port()
            
            # 打开流
            self._playctrl.open_stream(port=self._port)
            
            # 设置解码回调
            self._playctrl.set_decode_callback(self._on_frame_decoded, port=self._port)
            
            logger.info(f"视频解码器初始化成功，端口: {self._port}")
            return True
            
        except Exception as e:
            logger.error(f"视频解码器初始化失败: {e}")
            self.decode_error.emit(f"初始化失败: {e}")
            return False
    
    def shutdown(self):
        """关闭解码器"""
        self._is_running = False
        
        if self._playctrl:
            try:
                self._playctrl.stop_play(port=self._port)
                self._playctrl.close_stream(port=self._port)
                self._playctrl.free_port(self._port)
            except Exception as e:
                logger.warning(f"关闭解码器时出错: {e}")
        
        self._port = -1
        logger.info("视频解码器已关闭")
    
    def start(self) -> bool:
        """开始解码（只解码，不显示到窗口）"""
        if self._port < 0:
            return False
            
        try:
            # hwnd=0 表示只解码，不显示
            self._playctrl.start_play(hwnd=0, port=self._port)
            self._is_running = True
            logger.info("视频解码已开始")
            return True
        except Exception as e:
            logger.error(f"开始解码失败: {e}")
            self.decode_error.emit(f"开始解码失败: {e}")
            return False
    
    def stop(self):
        """停止解码"""
        if self._playctrl and self._port >= 0:
            self._playctrl.stop_play(port=self._port)
        self._is_running = False
    
    def input_data(self, data: bytes) -> bool:
        """输入视频数据"""
        if not self._is_running or self._port < 0:
            return False
        
        try:
            return self._playctrl.input_data(data, port=self._port)
        except Exception as e:
            logger.error(f"输入数据失败: {e}")
            return False
    
    def _on_frame_decoded(self, port, frame_data, frame_size, frame_info, user_data):
        """帧解码回调"""
        try:
            # 只处理我们关注的端口
            if port != self._port:
                return
            
            # 创建视频帧
            frame = VideoFrame(
                width=frame_info.nWidth,
                height=frame_info.nHeight,
                data=frame_data,
                timestamp=frame_info.nStamp
            )
            
            # 发射信号
            self.frame_decoded.emit(frame)
            
            # 调用回调
            if self._frame_callback:
                self._frame_callback(frame)
                
        except Exception as e:
            logger.error(f"处理解码帧时出错: {e}")
    
    def set_frame_callback(self, callback: Callable):
        """设置帧回调函数"""
        self._frame_callback = callback
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def port(self) -> int:
        return self._port
