"""
录像下载模块 - 设备 SDK 录像下载封装
"""

import os
import ctypes
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from .sdk_loader import SDKLoader, NET_DVR_PLAYCOND, NET_DVR_TIME, NET_DVR_FINDDATA_V30

logger = logging.getLogger(__name__)


class VideoDownloadWorker(QObject):
    """录像下载工作器"""
    
    # 信号
    started = pyqtSignal()
    progress = pyqtSignal(int)     # 进度 0-100
    completed = pyqtSignal(bool, str)  # success, message
    stopped = pyqtSignal()
    
    def __init__(self, user_id: int, channel: int, 
                 start_time: datetime, end_time: datetime,
                 output_path: str):
        super().__init__()
        self._user_id = user_id
        self._channel = channel
        self._start_time = start_time
        self._end_time = end_time
        self._output_path = output_path
        self._sdk = SDKLoader()
        
        self._handle: int = -1
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> bool:
        """开始下载"""
        if self._handle >= 0:
            logger.warning("下载已在进行中")
            return False
        
        # 确保输出目录存在
        Path(self._output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 创建下载条件
        play_cond = NET_DVR_PLAYCOND()
        play_cond.dwSize = ctypes.sizeof(NET_DVR_PLAYCOND)
        play_cond.dwChannel = self._channel
        
        # 设置开始时间
        play_cond.struStartTime.dwYear = self._start_time.year
        play_cond.struStartTime.dwMonth = self._start_time.month
        play_cond.struStartTime.dwDay = self._start_time.day
        play_cond.struStartTime.dwHour = self._start_time.hour
        play_cond.struStartTime.dwMinute = self._start_time.minute
        play_cond.struStartTime.dwSecond = self._start_time.second
        
        # 设置结束时间
        play_cond.struStopTime.dwYear = self._end_time.year
        play_cond.struStopTime.dwMonth = self._end_time.month
        play_cond.struStopTime.dwDay = self._end_time.day
        play_cond.struStopTime.dwHour = self._end_time.hour
        play_cond.struStopTime.dwMinute = self._end_time.minute
        play_cond.struStopTime.dwSecond = self._end_time.second
        
        play_cond.byDrawFrame = 0
        play_cond.byStreamType = 0  # 主码流
        
        # 开始下载
        handle = self._sdk.get_file_by_time(self._user_id, self._output_path, play_cond)
        
        if handle < 0:
            error_code = self._sdk.get_last_error()
            error_msg = f"开始下载失败，错误码: {error_code}"
            logger.error(error_msg)
            self.completed.emit(False, error_msg)
            return False
        
        self._handle = handle
        self._stop_flag.clear()
        
        # 控制开始播放/下载
        if not self._sdk.play_back_control(handle, 1):  # 1 = 开始
            error_msg = "启动下载控制失败"
            logger.error(error_msg)
            self._sdk.stop_get_file(handle)
            self._handle = -1
            self.completed.emit(False, error_msg)
            return False
        
        # 启动进度监控线程
        self._thread = threading.Thread(target=self._download_worker)
        self._thread.daemon = True
        self._thread.start()
        
        logger.info(f"开始下载通道 {self._channel} 录像到 {self._output_path}")
        self.started.emit()
        return True
    
    def _download_worker(self):
        """下载工作线程 - 监控进度"""
        last_progress = -1
        
        try:
            while not self._stop_flag.is_set() and self._handle >= 0:
                # 获取下载进度
                pos = self._sdk.get_download_pos(self._handle)
                
                if pos == 100:  # 完成
                    logger.info(f"下载完成: {self._output_path}")
                    self.progress.emit(100)
                    self.completed.emit(True, "下载完成")
                    break
                elif pos == 200:  # 异常
                    logger.error("下载异常")
                    self.completed.emit(False, "下载异常")
                    break
                elif pos < 0:  # 失败
                    error_code = self._sdk.get_last_error()
                    error_msg = f"下载失败，错误码: {error_code}"
                    logger.error(error_msg)
                    self.completed.emit(False, error_msg)
                    break
                elif pos != last_progress:
                    self.progress.emit(pos)
                    last_progress = pos
                
                time.sleep(0.5)
        except Exception as e:
            logger.exception(f"下载线程异常: {e}")
            self.completed.emit(False, str(e))
        finally:
            # 确保资源释放
            if self._handle >= 0:
                try:
                    self._sdk.stop_get_file(self._handle)
                except Exception as e:
                    logger.error(f"停止下载失败: {e}")
                finally:
                    self._handle = -1
            self.stopped.emit()
    
    def stop(self):
        """停止下载"""
        logger.info("停止下载")
        self._stop_flag.set()
        
        if self._handle >= 0:
            self._sdk.play_back_control(self._handle, 2)  # 2 = 停止
            self._sdk.stop_get_file(self._handle)
            self._handle = -1
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._handle >= 0


def convert_hik_to_mp4(input_path: str, output_path: str) -> bool:
    """
    使用 FFmpeg 转换视频格式到 MP4
    
    Args:
        input_path: 输入文件路径 (.hik 或 .dav)
        output_path: 输出文件路径 (.mp4)
    
    Returns:
        是否成功
    """
    import subprocess
    import shutil
    from .path_resolver import get_format_convert_path, get_app_dir
    
    # 查找 FFmpeg
    # get_format_convert_path 返回 FormatConverter.exe 路径，取其父目录找 ffmpeg.exe
    format_convert_dir = get_format_convert_path().parent
    ffmpeg_path = format_convert_dir / "ffmpeg.exe"
    if not ffmpeg_path.exists():
        # 再尝试直接相对于程序目录的标准位置
        ffmpeg_path = get_app_dir() / "sdk" / "tools" / "FormatConvert" / "ffmpeg.exe"
    if not ffmpeg_path.exists():
        # 尝试系统 PATH
        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            logger.error("未找到 FFmpeg")
            return False
        ffmpeg_path = Path(ffmpeg_exe)
    
    try:
        cmd = [
            str(ffmpeg_path),
            '-y',  # 覆盖输出文件
            '-i', input_path,  # 输入
            '-c:v', 'copy',  # 视频直接复制
            '-c:a', 'aac',   # 音频转 AAC
            '-movflags', '+faststart',  # 优化网页播放
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1小时超时
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode == 0:
            logger.info(f"转换成功: {output_path}")
            return True
        else:
            logger.error(f"转换失败: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("转换超时")
        return False
    except Exception as e:
        logger.error(f"转换异常: {e}")
        return False


# VideoSearcher 已迁移至 video_searcher.py
# 请使用: from src.core.video_searcher import VideoSearcher
