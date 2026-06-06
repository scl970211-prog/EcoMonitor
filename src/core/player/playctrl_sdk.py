# -*- coding: utf-8 -*-
"""
PlayCtrl SDK 播放控制库封装
实现视频解码和播放控制
"""

import ctypes
import os
import platform
import logging
from ctypes import c_int, c_void_p, c_char_p, c_ulong, POINTER, Structure
from enum import IntEnum
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class PlayError(IntEnum):
    """播放错误码"""
    OK = 0
    NOFILE = 1          # 没有文件
    NOMEM = 2           # 内存不足
    ALREADY_OPEN = 3    # 已经打开
    NOT_OPEN = 4        # 没有打开
    BUFFER_OVERFLOW = 5 # 缓存溢出
    BUFFER_EMPTY = 6    # 缓存为空
    PLAYING = 7         # 正在播放
    NOT_PLAYING = 8     # 没有播放
    OPEN_FILE_ERROR = 9 # 打开文件失败
    CREATE_THREAD_ERROR = 10  # 创建线程失败


class FrameType(IntEnum):
    """帧类型"""
    VIDEO = 1           # 视频帧
    AUDIO = 2           # 音频帧


class FrameInfo(Structure):
    """帧信息结构体"""
    _fields_ = [
        ("nWidth", c_int),
        ("nHeight", c_int),
        ("nStamp", c_int),
        ("nType", c_int),
        ("nFrameRate", c_int),
        ("dwFrameNum", c_ulong),
    ]


class PlayCtrlSDK:
    """
    PlayCtrl SDK 封装类
    支持视频解码和播放控制
    """
    
    # 颜色格式
    COLOR_FORMAT_RGB24 = 7
    COLOR_FORMAT_BGR24 = 8
    COLOR_FORMAT_YUV420P = 19
    
    # 流类型
    STREAM_TYPE_RTP = 0
    STREAM_TYPE_TS = 1
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_sdk'):
            return
            
        self._sdk = None
        self._port = -1
        self._decode_callback: Optional[Callable] = None
        self._display_callback: Optional[Callable] = None
        
    def load(self) -> bool:
        """加载 PlayCtrl SDK"""
        if self._initialized:
            return True
            
        try:
            # 查找 SDK 路径
            sdk_paths = self._find_sdk_paths()
            
            for path in sdk_paths:
                if not path.exists():
                    continue
                    
                try:
                    # 切换工作目录以加载依赖
                    original_dir = os.getcwd()
                    os.chdir(path.parent)
                    
                    self._sdk = ctypes.WinDLL(str(path))
                    os.chdir(original_dir)
                    
                    # 初始化 SDK
                    result = self._sdk.PlayM4_GetLastError()
                    logger.info(f"PlayCtrl SDK 加载成功: {path}")
                    
                    self._setup_api()
                    self._initialized = True
                    return True
                    
                except Exception as e:
                    logger.warning(f"从 {path} 加载失败: {e}")
                    continue
                    
            logger.error("无法加载 PlayCtrl SDK")
            return False
            
        except Exception as e:
            logger.error(f"加载 PlayCtrl SDK 失败: {e}")
            return False
    
    def _find_sdk_paths(self):
        """查找 SDK 库文件路径"""
        from pathlib import Path
        
        base_dirs = [
            Path("sdk/win64"),
            Path("../sdk/win64"),
            Path("../../sdk/win64"),
            Path("./"),
        ]
        
        paths = []
        for base in base_dirs:
            paths.extend([
                base / "PlayCtrl.dll",
                base / "PlayCtrl.dll",
            ])
        
        return [p for p in paths]
    
    def _setup_api(self):
        """设置 API 函数原型"""
        if not self._sdk:
            return
            
        # 获取空闲端口
        self._sdk.PlayM4_GetPort.argtypes = [POINTER(c_int)]
        self._sdk.PlayM4_GetPort.restype = c_int
        
        # 释放端口
        self._sdk.PlayM4_FreePort.argtypes = [c_int]
        self._sdk.PlayM4_FreePort.restype = c_int
        
        # 打开流
        self._sdk.PlayM4_OpenStream.argtypes = [c_int, POINTER(ctypes.c_ubyte), c_int, c_int]
        self._sdk.PlayM4_OpenStream.restype = c_int
        
        # 关闭流
        self._sdk.PlayM4_CloseStream.argtypes = [c_int]
        self._sdk.PlayM4_CloseStream.restype = c_int
        
        # 开始播放
        self._sdk.PlayM4_Play.argtypes = [c_int, c_void_p]
        self._sdk.PlayM4_Play.restype = c_int
        
        # 停止播放
        self._sdk.PlayM4_Stop.argtypes = [c_int]
        self._sdk.PlayM4_Stop.restype = c_int
        
        # 输入数据
        self._sdk.PlayM4_InputData.argtypes = [c_int, POINTER(ctypes.c_ubyte), c_int]
        self._sdk.PlayM4_InputData.restype = c_int
        
        # 设置解码回调
        self._DECODE_CALLBACK = ctypes.WINFUNCTYPE(None, c_int, POINTER(ctypes.c_ubyte), 
                                                    c_int, POINTER(FrameInfo), c_void_p)
        self._sdk.PlayM4_SetDecCallBackExMend.argtypes = [c_int, c_void_p, c_void_p, c_int, c_void_p]
        self._sdk.PlayM4_SetDecCallBackExMend.restype = c_int
        
        # 获取最后错误
        self._sdk.PlayM4_GetLastError.argtypes = []
        self._sdk.PlayM4_GetLastError.restype = c_int
        
        # 刷新缓冲区
        self._sdk.PlayM4_RefreshPlay.argtypes = [c_int]
        self._sdk.PlayM4_RefreshPlay.restype = c_int
        
        # 设置流播放模式
        self._sdk.PlayM4_SetStreamOpenMode.argtypes = [c_int, c_int]
        self._sdk.PlayM4_SetStreamOpenMode.restype = c_int
        
    def get_port(self) -> int:
        """获取空闲播放端口"""
        if not self._sdk:
            raise RuntimeError("SDK 未加载")
            
        port = c_int()
        result = self._sdk.PlayM4_GetPort(ctypes.byref(port))
        
        if result != PlayError.OK:
            error = self._sdk.PlayM4_GetLastError()
            raise RuntimeError(f"获取端口失败，错误码: {error}")
            
        self._port = port.value
        logger.debug(f"获取播放端口: {self._port}")
        return self._port
    
    def free_port(self, port: int = None):
        """释放播放端口"""
        if not self._sdk:
            return
            
        p = port if port is not None else self._port
        if p < 0:
            return
            
        self._sdk.PlayM4_FreePort(p)
        logger.debug(f"释放播放端口: {p}")
        
        if p == self._port:
            self._port = -1
    
    def open_stream(self, buffer_size: int = 1024 * 1024, port: int = None) -> bool:
        """
        打开视频流
        
        Args:
            buffer_size: 缓冲区大小，默认 1MB
            port: 播放端口，None 使用当前端口
        """
        if not self._sdk:
            raise RuntimeError("SDK 未加载")
            
        p = port if port is not None else self._port
        if p < 0:
            raise RuntimeError("未获取播放端口")
        
        # 设置流播放模式为实时模式
        self._sdk.PlayM4_SetStreamOpenMode(p, 0)
        
        # 打开流
        result = self._sdk.PlayM4_OpenStream(p, None, 0, buffer_size)
        if result != PlayError.OK:
            error = self._sdk.PlayM4_GetLastError()
            raise RuntimeError(f"打开流失败，错误码: {error}")
            
        logger.debug(f"端口 {p} 流已打开")
        return True
    
    def close_stream(self, port: int = None):
        """关闭视频流"""
        if not self._sdk:
            return
            
        p = port if port is not None else self._port
        if p < 0:
            return
            
        self._sdk.PlayM4_CloseStream(p)
        logger.debug(f"端口 {p} 流已关闭")
    
    def start_play(self, hwnd: int = 0, port: int = None) -> bool:
        """
        开始播放
        
        Args:
            hwnd: 窗口句柄，0 表示只解码不显示
            port: 播放端口
        """
        if not self._sdk:
            raise RuntimeError("SDK 未加载")
            
        p = port if port is not None else self._port
        if p < 0:
            raise RuntimeError("未获取播放端口")
        
        result = self._sdk.PlayM4_Play(p, hwnd)
        if result != PlayError.OK:
            error = self._sdk.PlayM4_GetLastError()
            raise RuntimeError(f"开始播放失败，错误码: {error}")
            
        logger.debug(f"端口 {p} 开始播放")
        return True
    
    def stop_play(self, port: int = None):
        """停止播放"""
        if not self._sdk:
            return
            
        p = port if port is not None else self._port
        if p < 0:
            return
            
        self._sdk.PlayM4_Stop(p)
        logger.debug(f"端口 {p} 停止播放")
    
    def input_data(self, data: bytes, port: int = None) -> bool:
        """
        输入视频数据
        
        Args:
            data: 视频数据
            port: 播放端口
        """
        if not self._sdk:
            return False
            
        p = port if port is not None else self._port
        if p < 0:
            return False
        
        if not data:
            return True
            
        # 转换为 ctypes 数组
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        result = self._sdk.PlayM4_InputData(p, buf, len(data))
        
        return result == PlayError.OK
    
    def set_decode_callback(self, callback: Callable, port: int = None, user_data=None):
        """
        设置解码回调函数
        
        Args:
            callback: 回调函数 fn(port, frame_data, frame_size, frame_info, user_data)
            port: 播放端口
            user_data: 用户数据
        """
        if not self._sdk:
            return
            
        p = port if port is not None else self._port
        if p < 0:
            return
        
        self._decode_callback = callback
        
        # 创建回调包装器
        def wrapper(nPort, pBuf, nSize, pFrameInfo, nUser):
            try:
                # 复制帧数据
                frame_data = ctypes.string_at(pBuf, nSize)
                frame_info = pFrameInfo.contents
                
                callback(nPort, frame_data, nSize, frame_info, nUser)
            except Exception as e:
                logger.error(f"解码回调错误: {e}")
        
        self._callback_ref = self._DECODE_CALLBACK(wrapper)
        
        result = self._sdk.PlayM4_SetDecCallBackExMend(
            p, self._callback_ref, None, 0, ctypes.c_void_p(user_data)
        )
        
        if result != PlayError.OK:
            error = self._sdk.PlayM4_GetLastError()
            logger.warning(f"设置解码回调失败，错误码: {error}")
    
    def refresh(self, port: int = None):
        """刷新播放缓冲区"""
        if not self._sdk:
            return
            
        p = port if port is not None else self._port
        if p < 0:
            return
            
        self._sdk.PlayM4_RefreshPlay(p)
    
    def get_last_error(self) -> int:
        """获取最后错误码"""
        if not self._sdk:
            return -1
        return self._sdk.PlayM4_GetLastError()


# 全局实例
_playctrl_sdk = None

def get_playctrl_sdk() -> PlayCtrlSDK:
    """获取 PlayCtrl SDK 全局实例"""
    global _playctrl_sdk
    if _playctrl_sdk is None:
        _playctrl_sdk = PlayCtrlSDK()
    return _playctrl_sdk
