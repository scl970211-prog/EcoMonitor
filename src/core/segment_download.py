# -*- coding: utf-8 -*-
"""
段级下载管理模块
支持大文件分段下载和断点续传
"""

import os
import json
import shutil
import logging
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable, Tuple
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QWaitCondition

from .sdk_loader import SDKLoader
from .format_converter import FormatConverter
from .device import Device

logger = logging.getLogger(__name__)


class SegmentStatus(Enum):
    """段状态"""
    PENDING = "pending"         # 等待下载
    DOWNLOADING = "downloading" # 正在下载
    PAUSED = "paused"          # 已暂停
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    MERGING = "merging"        # 合并中


@dataclass
class DownloadSegment:
    """下载段定义"""
    index: int                  # 段索引
    start_time: datetime        # 开始时间
    end_time: datetime          # 结束时间
    temp_path: str             # 临时文件路径
    output_path: str           # 最终输出路径
    status: SegmentStatus = SegmentStatus.PENDING
    downloaded_bytes: int = 0   # 已下载字节
    total_bytes: int = 0        # 总字节数
    retry_count: int = 0        # 重试次数
    error_msg: str = ""         # 错误信息
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "index": self.index,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "temp_path": self.temp_path,
            "output_path": self.output_path,
            "status": self.status.value,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "retry_count": self.retry_count,
            "error_msg": self.error_msg,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DownloadSegment":
        """从字典创建"""
        return cls(
            index=data["index"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            temp_path=data["temp_path"],
            output_path=data["output_path"],
            status=SegmentStatus(data["status"]),
            downloaded_bytes=data.get("downloaded_bytes", 0),
            total_bytes=data.get("total_bytes", 0),
            retry_count=data.get("retry_count", 0),
            error_msg=data.get("error_msg", ""),
        )
    
    @property
    def progress(self) -> float:
        """下载进度 0-100"""
        if self.total_bytes <= 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100
    
    @property
    def duration_seconds(self) -> int:
        """段时长（秒）"""
        return int((self.end_time - self.start_time).total_seconds())


@dataclass
class SegmentTaskConfig:
    """段任务配置"""
    task_id: str
    device_ip: str
    device_port: int
    device_username: str
    device_password: str
    channel: int
    save_dir: str
    convert_to_mp4: bool = True
    max_segment_size_gb: float = 2.0  # 每段最大2GB
    max_retries: int = 3


class SegmentDownloadManager(QObject):
    """
    段级下载管理器
    管理分段下载的完整生命周期
    """
    
    # 信号
    segment_progress = pyqtSignal(str, int, int, int)  # task_id, segment_index, downloaded, total
    segment_status_changed = pyqtSignal(str, int, str)  # task_id, segment_index, status
    segment_completed = pyqtSignal(str, int)  # task_id, segment_index
    segment_failed = pyqtSignal(str, int, str)  # task_id, segment_index, error
    merge_started = pyqtSignal(str)  # task_id
    merge_progress = pyqtSignal(str, int, int)  # task_id, current, total
    task_completed = pyqtSignal(str, str)  # task_id, output_path
    task_failed = pyqtSignal(str, str)  # task_id, error_msg
    task_paused = pyqtSignal(str)  # task_id
    task_resumed = pyqtSignal(str)  # task_id
    
    def __init__(self):
        super().__init__()
        
        self._tasks: Dict[str, Dict] = {}  # task_id -> task_info
        self._segments: Dict[str, List[DownloadSegment]] = {}  # task_id -> segments
        self._workers: Dict[str, "SegmentDownloadWorker"] = {}
        self._mergers: Dict[str, "SegmentMerger"] = {}
        
        # 状态锁
        self._mutex = QMutex()
        
        # 恢复任务
        self._load_pending_tasks()
    
    def create_segments(self, config: SegmentTaskConfig, 
                       files: List[dict]) -> List[DownloadSegment]:
        """
        根据文件列表创建下载段
        
        Args:
            config: 任务配置
            files: 文件信息列表（来自录像检索）
        
        Returns:
            下载段列表
        """
        segments = []
        max_size_bytes = int(config.max_segment_size_gb * 1024 * 1024 * 1024)
        
        temp_dir = Path(config.save_dir) / ".temp" / config.task_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        current_segment_files = []
        current_segment_size = 0
        segment_index = 0
        segment_start_time = None
        
        for file_info in sorted(files, key=lambda x: x.get("start_time", "")):
            file_size = file_info.get("size", 0)
            file_start = datetime.fromisoformat(file_info.get("start_time")) \
                        if isinstance(file_info.get("start_time"), str) \
                        else file_info.get("start_time", datetime.now())
            file_end = datetime.fromisoformat(file_info.get("end_time")) \
                      if isinstance(file_info.get("end_time"), str) \
                      else file_info.get("end_time", datetime.now())
            
            # 如果添加此文件会超过大小限制，先创建当前段
            if current_segment_files and (current_segment_size + file_size) > max_size_bytes:
                segment = self._create_segment(
                    config, segment_index, temp_dir,
                    segment_start_time, 
                    current_segment_files[-1].get("end_time", file_end),
                    current_segment_files
                )
                segments.append(segment)
                
                # 开始新段
                segment_index += 1
                current_segment_files = [file_info]
                current_segment_size = file_size
                segment_start_time = file_start
            else:
                # 添加到当前段
                current_segment_files.append(file_info)
                current_segment_size += file_size
                if segment_start_time is None:
                    segment_start_time = file_start
        
        # 处理最后一个段
        if current_segment_files:
            segment = self._create_segment(
                config, segment_index, temp_dir,
                segment_start_time,
                current_segment_files[-1].get("end_time", datetime.now()),
                current_segment_files
            )
            segments.append(segment)
        
        logger.info(f"任务 {config.task_id}: 创建了 {len(segments)} 个下载段")
        return segments
    
    def _create_segment(self, config: SegmentTaskConfig, index: int, 
                       temp_dir: Path, start_time: datetime, 
                       end_time: datetime, files: List[dict]) -> DownloadSegment:
        """创建单个段"""
        # 生成临时文件名
        temp_filename = f"segment_{index:04d}.dav"
        temp_path = str(temp_dir / temp_filename)
        
        # 最终输出路径
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"ch{config.channel}_{timestamp}"
        if config.convert_to_mp4:
            output_filename += ".mp4"
        else:
            output_filename += ".dav"
        output_path = str(Path(config.save_dir) / output_filename)
        
        # 计算总大小
        total_bytes = sum(f.get("size", 0) for f in files)
        
        return DownloadSegment(
            index=index,
            start_time=start_time,
            end_time=end_time,
            temp_path=temp_path,
            output_path=output_path,
            total_bytes=total_bytes,
        )
    
    def start_download(self, config: SegmentTaskConfig, 
                      segments: List[DownloadSegment]) -> bool:
        """开始下载任务"""
        self._mutex.lock()
        try:
            self._tasks[config.task_id] = {
                "config": config,
                "start_time": datetime.now(),
                "status": "running",
            }
            self._segments[config.task_id] = segments
        
        finally:
            self._mutex.unlock()
        # 保存任务状态
        self._save_task_state(config.task_id)
        
        # 创建工作线程
        worker = SegmentDownloadWorker(config, segments, self)
        worker.segment_progress.connect(self.segment_progress)
        worker.segment_status_changed.connect(self.segment_status_changed)
        worker.segment_completed.connect(self._on_segment_completed)
        worker.segment_failed.connect(self.segment_failed)
        worker.task_completed.connect(self._on_task_completed)
        worker.task_failed.connect(self._on_task_failed)
        worker.task_failed.connect(self.task_failed)
        
        self._workers[config.task_id] = worker
        worker.start()
        
        logger.info(f"任务 {config.task_id} 开始下载，共 {len(segments)} 个段")
        return True
    
    def pause_download(self, task_id: str) -> bool:
        """暂停下载"""
        self._mutex.lock()
        try:
            if task_id in self._workers:
                self._workers[task_id].pause()
                self._tasks[task_id]["status"] = "paused"
                self.task_paused.emit(task_id)
                self._save_task_state(task_id)
                logger.info(f"任务 {task_id} 已暂停")
                return True
            return False
    
        finally:
            self._mutex.unlock()
    def resume_download(self, task_id: str) -> bool:
        """恢复下载"""
        self._mutex.lock()
        try:
            if task_id in self._workers:
                self._workers[task_id].resume()
                self._tasks[task_id]["status"] = "running"
                self.task_resumed.emit(task_id)
                self._save_task_state(task_id)
                logger.info(f"任务 {task_id} 已恢复")
                return True
        
        finally:
            self._mutex.unlock()
        # 如果worker已结束，尝试恢复
        return self._try_resume_task(task_id)
    
    def cancel_download(self, task_id: str, cleanup: bool = False) -> bool:
        """取消下载"""
        self._mutex.lock()
        try:
            if task_id in self._workers:
                self._workers[task_id].cancel()
                self._workers[task_id].wait(5000)
                del self._workers[task_id]
            
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "cancelled"
            
            if cleanup and task_id in self._segments:
                # 清理临时文件
                for segment in self._segments[task_id]:
                    try:
                        if os.path.exists(segment.temp_path):
                            os.remove(segment.temp_path)
                    except Exception as e:
                        logger.warning(f"清理临时文件失败: {e}")
                del self._segments[task_id]
        
        finally:
            self._mutex.unlock()
        # 删除状态文件
        self._remove_task_state(task_id)
        logger.info(f"任务 {task_id} 已取消")
        return True
    
    def shutdown(self):
        """关闭管理器，取消所有运行中任务"""
        self._mutex.lock()
        try:
            task_ids = list(self._workers.keys())
        
        finally:
            self._mutex.unlock()
        for task_id in task_ids:
            self.cancel_download(task_id, cleanup=False)
        
        logger.info("段级下载管理器已关闭")
    
    def get_task_progress(self, task_id: str) -> Tuple[int, int, int]:
        """
        获取任务进度
        
        Returns:
            (completed_segments, total_segments, total_progress_percent)
        """
        if task_id not in self._segments:
            return 0, 0, 0
        
        segments = self._segments[task_id]
        total = len(segments)
        completed = sum(1 for s in segments if s.status == SegmentStatus.COMPLETED)
        
        # 计算总体进度
        total_bytes = sum(s.total_bytes for s in segments)
        downloaded_bytes = sum(s.downloaded_bytes for s in segments)
        
        if total_bytes > 0:
            progress = int((downloaded_bytes / total_bytes) * 100)
        else:
            progress = 0
        
        return completed, total, progress
    
    def get_segment_status(self, task_id: str) -> List[dict]:
        """获取段状态列表"""
        if task_id not in self._segments:
            return []
        
        return [s.to_dict() for s in self._segments[task_id]]
    
    def _on_segment_completed(self, task_id: str, segment_index: int):
        """段下载完成"""
        self.segment_completed.emit(task_id, segment_index)
        self._save_task_state(task_id)
        
        # 检查是否全部完成
        if task_id in self._segments:
            segments = self._segments[task_id]
            if all(s.status == SegmentStatus.COMPLETED for s in segments):
                # 开始合并
                self._start_merge(task_id)
    
    def _start_merge(self, task_id: str):
        """开始合并段"""
        if task_id not in self._segments:
            return
        
        self.merge_started.emit(task_id)
        
        segments = self._segments[task_id]
        config = self._tasks[task_id]["config"]
        
        # 创建合并线程
        merger = SegmentMerger(task_id, segments, config, self)
        merger.merge_progress.connect(self.merge_progress)
        merger.merge_completed.connect(self._on_task_completed)
        merger.merge_completed.connect(self.task_completed)
        merger.merge_failed.connect(self._on_task_failed)
        merger.merge_failed.connect(self.task_failed)
        merger.finished.connect(lambda: self._cleanup_merger(task_id))
        self._mergers[task_id] = merger
        merger.start()
    
    def _on_task_completed(self, task_id: str, output_path: str):
        """任务完成"""
        self._mutex.lock()
        try:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["end_time"] = datetime.now()
                self._tasks[task_id]["output_path"] = output_path
        
        finally:
            self._mutex.unlock()
        self._remove_task_state(task_id)
        logger.info(f"任务 {task_id} 完成，输出: {output_path}")

    def _on_task_failed(self, task_id: str, error_msg: str):
        """任务失败"""
        self._mutex.lock()
        try:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["end_time"] = datetime.now()
                self._tasks[task_id]["error_msg"] = error_msg
        finally:
            self._mutex.unlock()

        self._save_task_state(task_id)
        logger.error(f"任务 {task_id} 失败: {error_msg}")

    def _cleanup_merger(self, task_id: str):
        """清理合并线程引用"""
        merger = self._mergers.pop(task_id, None)
        if merger is not None:
            merger.deleteLater()
    
    def _save_task_state(self, task_id: str):
        """保存任务状态（用于断点续传）"""
        if task_id not in self._segments:
            return
        
        try:
            state = {
                "task": self._tasks.get(task_id, {}),
                "segments": [s.to_dict() for s in self._segments[task_id]],
                "saved_at": datetime.now().isoformat(),
            }
            
            # 转换不可序列化的对象
            config = state["task"].get("config")
            if config:
                state["task"]["config"] = {
                    "task_id": config.task_id,
                    "device_ip": config.device_ip,
                    "device_port": config.device_port,
                    "device_username": config.device_username,
                    "device_password": config.device_password,
                    "channel": config.channel,
                    "save_dir": config.save_dir,
                    "convert_to_mp4": config.convert_to_mp4,
                    "max_segment_size_gb": config.max_segment_size_gb,
                }
            
            state_file = self._get_state_file_path(task_id)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"保存任务状态失败: {e}")
    
    def _load_pending_tasks(self):
        """加载待恢复的任务"""
        try:
            state_dir = self._get_state_dir()
            if not state_dir.exists():
                return
            
            for state_file in state_dir.glob("*.json"):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    
                    task_id = state["task"]["config"]["task_id"]
                    
                    # 恢复段列表
                    segments = [DownloadSegment.from_dict(s) for s in state["segments"]]
                    
                    # 检查是否有未完成的段
                    pending = [s for s in segments if s.status not in 
                              (SegmentStatus.COMPLETED, SegmentStatus.MERGING)]
                    
                    if pending:
                        self._segments[task_id] = segments
                        logger.info(f"加载到待恢复任务: {task_id}, {len(pending)} 个未完成段")
                        
                except Exception as e:
                    logger.warning(f"加载任务状态失败: {e}")
                    
        except Exception as e:
            logger.error(f"加载待恢复任务失败: {e}")
    
    def _try_resume_task(self, task_id: str) -> bool:
        """尝试恢复任务"""
        if task_id not in self._segments:
            return False
        
        # 重新创建worker继续下载
        # ... 实现恢复逻辑
        return False
    
    def _remove_task_state(self, task_id: str):
        """删除任务状态文件"""
        try:
            state_file = self._get_state_file_path(task_id)
            if state_file.exists():
                state_file.unlink()
        except Exception as e:
            logger.warning(f"删除状态文件失败: {e}")
    
    def _get_state_dir(self) -> Path:
        """获取状态目录"""
        state_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "HikvisionTool" / "tasks"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    
    def _get_state_file_path(self, task_id: str) -> Path:
        """获取状态文件路径"""
        return self._get_state_dir() / f"{task_id}.json"


class SegmentDownloadWorker(QThread):
    """段下载工作线程"""
    
    segment_progress = pyqtSignal(str, int, int, int)  # task_id, index, downloaded, total
    segment_status_changed = pyqtSignal(str, int, str)  # task_id, index, status
    segment_completed = pyqtSignal(str, int)  # task_id, index
    segment_failed = pyqtSignal(str, int, str)  # task_id, index, error
    task_completed = pyqtSignal(str, str)  # task_id, output_path
    task_failed = pyqtSignal(str, str)  # task_id, error
    
    def __init__(self, config: SegmentTaskConfig, 
                 segments: List[DownloadSegment],
                 manager: SegmentDownloadManager):
        super().__init__()
        
        self._config = config
        self._segments = segments
        self._manager = manager
        
        self._paused = False
        self._cancelled = False
        self._pause_condition = QWaitCondition()
        self._pause_mutex = QMutex()
        
        self._sdk = SDKLoader()
        self._device: Optional[Device] = None
        self._current_handle = -1
        self._current_segment_index: Optional[int] = None
    
    def pause(self):
        """暂停"""
        self._pause_mutex.lock()
        self._paused = True
        self._pause_mutex.unlock()
        if self._current_handle >= 0:
            self._sdk.play_back_control(self._current_handle, 3)
        if self._current_segment_index is not None:
            self.segment_status_changed.emit(
                self._config.task_id,
                self._current_segment_index,
                SegmentStatus.PAUSED.value,
            )
    
    def resume(self):
        """恢复"""
        self._pause_mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()  # 在锁内唤醒避免竞态条件
        self._pause_mutex.unlock()
        if self._current_handle >= 0:
            self._sdk.play_back_control(self._current_handle, 4)
        if self._current_segment_index is not None:
            self.segment_status_changed.emit(
                self._config.task_id,
                self._current_segment_index,
                SegmentStatus.DOWNLOADING.value,
            )
    
    def cancel(self):
        """取消"""
        self._cancelled = True
        self.resume()  # 唤醒线程
    
    def run(self):
        """执行下载"""
        try:
            # 登录设备
            user_id = self._login_device()
            if user_id < 0:
                self.task_failed.emit(self._config.task_id, "设备登录失败")
                return
            
            try:
                # 下载每个段
                for segment in self._segments:
                    if self._cancelled:
                        break
                    
                    # 跳过已完成的段
                    if segment.status == SegmentStatus.COMPLETED:
                        continue
                    
                    # 检查暂停
                    self._check_pause()
                    
                    # 下载段
                    self._download_segment(user_id, segment)
                    if segment.status == SegmentStatus.FAILED:
                        self.task_failed.emit(
                            self._config.task_id,
                            segment.error_msg or f"段 {segment.index} 下载失败",
                        )
                        return
                
                if self._cancelled:
                    return
                
                # 检查是否全部完成
                if all(s.status == SegmentStatus.COMPLETED for s in self._segments):
                    # 任务完成，等待合并
                    pass
                
            finally:
                # 注销设备（仅在登录成功时）
                if self._device:
                    self._device.logout()
                    self._device = None
                
        except Exception as e:
            logger.exception(f"段下载异常: {e}")
            self.task_failed.emit(self._config.task_id, str(e))
    
    def _login_device(self) -> int:
        """登录设备"""
        self._device = Device(
            self._config.device_ip,
            self._config.device_port,
            self._config.device_username,
            self._config.device_password,
        )
        if not self._device.login():
            return -1
        return self._device.user_id
    
    def _check_pause(self):
        """检查暂停"""
        self._pause_mutex.lock()
        try:
            while self._paused and not self._cancelled:
                self._pause_condition.wait(self._pause_mutex)
        finally:
            self._pause_mutex.unlock()
    
    def _download_segment(self, user_id: int, segment: DownloadSegment):
        """下载单个段"""
        self._current_segment_index = segment.index
        segment.status = SegmentStatus.DOWNLOADING
        self.segment_status_changed.emit(
            self._config.task_id, segment.index, SegmentStatus.DOWNLOADING.value
        )
        
        # 如果文件已存在且完整，跳过
        if os.path.exists(segment.temp_path):
            file_size = os.path.getsize(segment.temp_path)
            if file_size >= segment.total_bytes:
                segment.downloaded_bytes = file_size
                segment.status = SegmentStatus.COMPLETED
                self.segment_completed.emit(self._config.task_id, segment.index)
                return
            # 断点续传：从已有大小继续
            segment.downloaded_bytes = file_size
        
        # 准备下载条件
        play_cond = self._sdk.NET_DVR_PLAYCOND()
        play_cond.dwSize = ctypes.sizeof(self._sdk.NET_DVR_PLAYCOND)
        play_cond.dwChannel = self._config.channel
        play_cond.struStartTime = self._datetime_to_net_time(segment.start_time)
        play_cond.struStopTime = self._datetime_to_net_time(segment.end_time)
        
        # 开始下载
        handle = self._sdk.get_file_by_time(user_id, segment.temp_path, play_cond)
        
        if handle < 0:
            error = self._sdk.get_last_error()
            segment.status = SegmentStatus.FAILED
            segment.error_msg = f"启动下载失败: {error}"
            self.segment_failed.emit(self._config.task_id, segment.index, segment.error_msg)
            return
        
        self._current_handle = handle
        try:
            # 开始播放（即开始下载）
            if not self._sdk.play_back_control(handle, 1, 0):
                segment.status = SegmentStatus.FAILED
                segment.error_msg = "启动下载控制失败"
                self.segment_failed.emit(self._config.task_id, segment.index, segment.error_msg)
                return
            
            # 监控下载进度
            while not self._cancelled:
                self._check_pause()
                
                progress = self._sdk.get_download_pos(handle)
                
                if progress == 100:  # 完成
                    segment.status = SegmentStatus.COMPLETED
                    segment.downloaded_bytes = segment.total_bytes
                    self.segment_completed.emit(self._config.task_id, segment.index)
                    break
                elif progress > 100:  # 错误
                    segment.status = SegmentStatus.FAILED
                    segment.error_msg = f"下载错误: {progress}"
                    self.segment_failed.emit(
                        self._config.task_id, segment.index, segment.error_msg
                    )
                    break
                elif progress < 0:
                    segment.status = SegmentStatus.FAILED
                    segment.error_msg = "获取进度失败"
                    self.segment_failed.emit(
                        self._config.task_id, segment.index, segment.error_msg
                    )
                    break
                
                # 更新进度
                segment.downloaded_bytes = int(segment.total_bytes * progress / 100)
                self.segment_progress.emit(
                    self._config.task_id, segment.index,
                    segment.downloaded_bytes, segment.total_bytes
                )
                
                self.msleep(500)  # 500ms 检查一次
                
        finally:
            self._sdk.stop_get_file(handle)
            self._current_handle = -1
            self._current_segment_index = None
    
    def _datetime_to_net_time(self, dt: datetime):
        """转换为 SDK 时间结构"""
        return self._sdk.NET_DVR_TIME(
            dwYear=dt.year,
            dwMonth=dt.month,
            dwDay=dt.day,
            dwHour=dt.hour,
            dwMinute=dt.minute,
            dwSecond=dt.second
        )


class SegmentMerger(QThread):
    """段合并线程"""
    
    merge_progress = pyqtSignal(str, int, int)  # task_id, current, total
    merge_completed = pyqtSignal(str, str)  # task_id, output_path
    merge_failed = pyqtSignal(str, str)  # task_id, error
    
    def __init__(self, task_id: str, segments: List[DownloadSegment],
                 config: SegmentTaskConfig, manager: SegmentDownloadManager):
        super().__init__()
        
        self._task_id = task_id
        self._segments = [s for s in segments if s.status == SegmentStatus.COMPLETED]
        self._config = config
        self._manager = manager
    
    def run(self):
        """执行合并"""
        try:
            if not self._segments:
                self.merge_failed.emit(self._task_id, "没有可合并的段")
                return
            
            # 按索引排序
            self._segments.sort(key=lambda s: s.index)
            
            # 确定输出路径（使用第一个段的输出路径）
            output_path = self._segments[0].output_path
            
            # 如果需要转换，先生成合并的 DAV 文件
            if self._config.convert_to_mp4:
                merged_dav = output_path.replace(".mp4", "_merged.dav")
            else:
                merged_dav = output_path
            
            # 合并文件
            total_size = sum(s.downloaded_bytes for s in self._segments)
            merged_size = 0
            
            with open(merged_dav, "wb") as outfile:
                for i, segment in enumerate(self._segments):
                    self.merge_progress.emit(self._task_id, i + 1, len(self._segments))
                    
                    if not os.path.exists(segment.temp_path):
                        raise FileNotFoundError(f"段文件不存在: {segment.temp_path}")
                    
                    with open(segment.temp_path, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)
                        merged_size += os.path.getsize(segment.temp_path)
                    
                    # 删除临时文件
                    try:
                        os.remove(segment.temp_path)
                    except Exception as e:
                        logger.warning(f"删除临时文件失败: {e}")
            
            logger.info(f"任务 {self._task_id}: 文件合并完成，大小: {merged_size / 1024 / 1024:.2f} MB")
            
            # 转换为 MP4
            if self._config.convert_to_mp4:
                self.merge_progress.emit(self._task_id, len(self._segments), len(self._segments) + 1)
                
                converter = FormatConverter()
                success = converter.convert(merged_dav, output_path)
                
                if success:
                    # 删除中间 DAV 文件
                    try:
                        os.remove(merged_dav)
                    except Exception as e:
                        logger.warning(f"删除中间文件失败: {e}")
                    
                    self.merge_completed.emit(self._task_id, output_path)
                    logger.info(f"任务 {self._task_id}: 转换完成，输出: {output_path}")
                else:
                    self.merge_failed.emit(self._task_id, "MP4 转换失败")
            else:
                self.merge_completed.emit(self._task_id, merged_dav)
                
        except Exception as e:
            logger.exception(f"合并失败: {e}")
            self.merge_failed.emit(self._task_id, str(e))


# 导入 ctypes 用于类型提示
import ctypes


# 全局单例
_segment_manager = None

def get_segment_manager() -> SegmentDownloadManager:
    """获取段级下载管理器全局实例"""
    global _segment_manager
    if _segment_manager is None:
        _segment_manager = SegmentDownloadManager()
    return _segment_manager
