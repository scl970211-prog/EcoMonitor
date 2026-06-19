# -*- coding: utf-8 -*-
"""
下载工作线程 - 双线程并行处理版本。
实现下载和转换并行执行，通过队列通信。
"""

import logging
import os
import shutil
import threading
import queue
import time
import weakref
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import List, Tuple, Optional, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot

from .device import Device
from .download_task import DownloadTask
from .format_converter import FormatConverter
from .path_resolver import get_temp_dir

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 状态管理 - Actor 模式
# ============================================================================

class SegmentStatus(Enum):
    """段状态枚举"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    CONVERTING = "converting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SegmentState:
    """
    段状态 - 不可变设计，天然线程安全。
    使用 frozen=True 创建后不可修改，只能通过创建新实例更新。
    """
    index: int
    status: SegmentStatus = SegmentStatus.PENDING
    temp_path: str = ""
    output_path: str = ""
    file_size: int = 0
    download_progress: float = 0.0
    convert_progress: float = 0.0
    error_msg: str = ""


class TaskStateManager(QObject):
    """
    任务状态管理器 - 采用 Actor 模式。
    
    核心设计：
    - 所有状态变更通过消息队列
    - 单线程（_state_thread）处理所有状态更新
    - 消除了多线程竞争，无需复杂锁
    - Qt 信号自动处理跨线程通信
    
    信号：
        segment_changed(task_id, segment_index, status) - 段状态变更
        progress_updated(task_id, overall_progress) - 整体进度更新
    """
    
    segment_changed = pyqtSignal(str, int, str)  # task_id, segment_index, status
    progress_updated = pyqtSignal(str, int)       # task_id, overall_progress
    
    def __init__(self, task: DownloadTask):
        super().__init__()
        self.task = task
        self._segments: Dict[int, SegmentState] = {}
        # 使用 threading.Lock 而不是 QMutex，因为我们在 Python 线程中使用
        self._lock = threading.Lock()
        
        # 性能优化：缓存已完成字节数和计数，避免O(n²)计算
        self._completed_bytes_cache = 0
        self._completed_count_cache = 0
        self._completed_indices: set = set()
        
        # Actor 模式：状态变更消息队列
        self._state_queue = queue.Queue()
        self._state_thread = threading.Thread(
            target=self._process_state_changes,
            name=f"StateManager-{task.task_id[:8]}",
            daemon=True
        )
        self._state_thread.start()
        logger.debug(f"[StateManager] 启动状态管理线程: {task.task_id}")
    
    def init_segments(self, count: int):
        """初始化所有段状态"""
        # 修复：确保 completed_segments 不超过 count
        completed = min(self.task.completed_segments, count)
        
        with self._lock:
            for i in range(count):
                self._segments[i] = SegmentState(index=i)
                # 恢复已完成的段状态
                if i < completed:
                    self._segments[i] = SegmentState(
                        index=i,
                        status=SegmentStatus.COMPLETED,
                        file_size=self.task.matched_files[i].get("size", 0) if i < len(self.task.matched_files) else 0
                    )
                    self._completed_indices.add(i)
            
            # 初始化缓存
            self._completed_count_cache = completed
            self._completed_bytes_cache = sum(
                self.task.matched_files[i].get("size", 0) 
                for i in range(completed) 
                if i < len(self.task.matched_files)
            )
        
        logger.debug(f"[StateManager] 初始化 {count} 个段，恢复 {completed} 个已完成")
    
    def update_segment(self, index: int, status: SegmentStatus, **kwargs):
        """
        发送状态更新消息（非阻塞）。
        实际更新在 _state_thread 单线程中执行。
        """
        self._state_queue.put(('update', index, status, kwargs))
    
    def update_progress(self, index: int, download_progress: float = None, 
                       convert_progress: float = None):
        """发送进度更新消息"""
        self._state_queue.put(('progress', index, download_progress, convert_progress))
    
    def _process_state_changes(self):
        """
        状态处理线程 - 单线程执行所有状态变更。
        这是 Actor 模式的核心，消除了多线程竞争。
        """
        while True:
            try:
                msg = self._state_queue.get(timeout=0.5)
                
                if msg is None:  # 结束标记
                    logger.debug("[StateManager] 状态管理线程结束")
                    break
                
                msg_type = msg[0]
                
                if msg_type == 'update':
                    _, index, status, kwargs = msg
                    self._do_update_segment(index, status, **kwargs)
                    
                elif msg_type == 'progress':
                    _, index, dl_prog, cv_prog = msg
                    self._do_update_progress(index, dl_prog, cv_prog)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[StateManager] 处理状态变更时出错: {e}")
    
    def _do_update_segment(self, index: int, new_status: SegmentStatus, **kwargs):
        """实际状态更新（单线程执行，安全）- 优化：O(1)缓存更新"""
        with self._lock:
            if index not in self._segments:
                return
            
            old_state = self._segments[index]
            # 创建新实例（不可变设计）
            new_state = SegmentState(
                index=index,
                status=new_status,
                temp_path=kwargs.get('temp_path', old_state.temp_path),
                output_path=kwargs.get('output_path', old_state.output_path),
                file_size=kwargs.get('file_size', old_state.file_size),
                download_progress=kwargs.get('download_progress', old_state.download_progress),
                convert_progress=kwargs.get('convert_progress', old_state.convert_progress),
                error_msg=kwargs.get('error_msg', old_state.error_msg),
            )
            self._segments[index] = new_state
            
            # 复制需要在锁外使用的数据
            task_id = self.task.task_id
            status_value = new_status.value
            output_path = new_state.output_path
            
            # 优化：O(1)更新完成计数和字节缓存
            if new_status == SegmentStatus.COMPLETED and old_state.status != SegmentStatus.COMPLETED:
                self._completed_count_cache += 1
                self._completed_bytes_cache += new_state.file_size
                self._completed_indices.add(index)
                self.task.completed_segments = self._completed_count_cache
                if output_path and output_path not in self.task.output_files:
                    self.task.output_files.append(output_path)
        
        # 锁外发射信号，避免死锁
        self.segment_changed.emit(task_id, index, status_value)
        self._recalculate_progress()
    
    def _do_update_progress(self, index: int, download_progress: float, 
                           convert_progress: float):
        """更新进度（单线程执行）"""
        with self._lock:
            if index not in self._segments:
                return
            
            segment = self._segments[index]
            kwargs = {'status': segment.status}
            if download_progress is not None:
                kwargs['download_progress'] = download_progress
            if convert_progress is not None:
                kwargs['convert_progress'] = convert_progress
            
            new_state = SegmentState(
                index=index,
                **kwargs,
                temp_path=segment.temp_path,
                output_path=segment.output_path,
                file_size=segment.file_size,
                error_msg=segment.error_msg,
            )
            self._segments[index] = new_state
        
        # 锁外重新计算进度
        self._recalculate_progress()
    
    def get_completed_bytes(self) -> int:
        """获取已完成字节数 - O(1)"""
        with self._lock:
            return self._completed_bytes_cache
    
    def _recalculate_progress(self):
        """重新计算整体进度和相关统计 - 优化：使用缓存"""
        with self._lock:
            total = len(self._segments)
            if total == 0:
                return
            
            # 优化：使用缓存的已完成字节数
            total_downloaded_bytes = self._completed_bytes_cache
            total_progress = self._completed_count_cache  # 已完成的是1.0
            current_phase = "download"
            
            # 只计算非完成状态的段
            for segment in self._segments.values():
                if segment.status == SegmentStatus.COMPLETED:
                    continue  # 已计算在缓存中
                elif segment.status == SegmentStatus.DOWNLOADING:
                    total_progress += 0.5 * (segment.download_progress / 100.0)
                    total_downloaded_bytes += int(segment.file_size * segment.download_progress / 100)
                    current_phase = "download"
                elif segment.status == SegmentStatus.DOWNLOADED:
                    total_progress += 0.5
                    total_downloaded_bytes += segment.file_size
                elif segment.status == SegmentStatus.CONVERTING:
                    total_progress += 0.5 + 0.5 * (segment.convert_progress / 100.0)
                    total_downloaded_bytes += segment.file_size
                    current_phase = "convert"
            
            overall = int((total_progress / total) * 100)
            
            # 更新任务对象（用于速度计算和显示）
            self.task.progress = overall
            self.task.phase = current_phase
            # 注意：downloaded_bytes 由回调直接更新，这里只更新缓存
            
            task_id = self.task.task_id
        
        # 锁外发射信号
        self.progress_updated.emit(task_id, overall)
    
    def get_segment(self, index: int) -> Optional[SegmentState]:
        """获取段状态（只读快照）"""
        with self._lock:
            return self._segments.get(index)
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        with self._lock:
            stats = {s.value: 0 for s in SegmentStatus}
            for seg in self._segments.values():
                stats[seg.status.value] += 1
            return stats
    
    def get_pending_convert(self) -> List[Tuple[int, str]]:
        """获取待转换的段（用于恢复）"""
        with self._lock:
            result = []
            for seg in self._segments.values():
                if seg.status == SegmentStatus.DOWNLOADED and seg.temp_path:
                    result.append((seg.index, seg.temp_path))
            return result
    
    def stop(self):
        """停止状态管理器"""
        self._state_queue.put(None)
        self._state_thread.join(timeout=5)
        if self._state_thread.is_alive():
            logger.warning("[StateManager] 状态线程未能在5秒内结束")
            # 强制清理队列
            while not self._state_queue.empty():
                try:
                    self._state_queue.get_nowait()
                except queue.Empty:
                    break


# ============================================================================
# 2. 临时文件管理 - 三级保障机制
# ============================================================================

class TempFileManager:
    """
    临时文件管理器 - 三级保障机制防止资源泄漏。
    
    保障机制：
    1. ExitStack: 确定性清理（上下文管理器）
    2. weakref.finalize: GC 安全网（垃圾回收时清理）
    3. atexit: 进程退出清理
    
    特点：
    - 自动磁盘空间检查
    - 任务专属临时目录
    - 崩溃后也能清理
    """
    
    def __init__(self, task_id: str, max_size_gb: float = 2.0):
        self.task_id = task_id
        self.max_size = int(max_size_gb * 1024 * 1024 * 1024)
        self._exit_stack = ExitStack()
        self._tracked_files: List[Tuple[int, str, int]] = []  # (index, path, size)
        self._total_size = 0
        
        # 创建任务专属临时目录
        base_temp = str(get_temp_dir())
        self.temp_dir = tempfile.mkdtemp(
            prefix=f"hikvision_{task_id[:8]}_",
            dir=base_temp
        )
        
        logger.debug(f"[TempManager] 创建临时目录: {self.temp_dir}")
        
        # 设置多级清理
        self._setup_cleanup()
    
    def _setup_cleanup(self):
        """设置多级清理机制"""
        # 1. ExitStack 上下文管理
        self._exit_stack.callback(self._cleanup_all)
        
        # 2. weakref.finalize（GC 安全网）
        self._finalizer = weakref.finalize(
            self, 
            self._cleanup_static,
            self.temp_dir
        )
        self._finalizer.atexit = True  # 进程退出时清理
    
    @staticmethod
    def _cleanup_static(temp_dir: str):
        """静态清理方法（weakref.finalize 需要）- 防止模块卸载问题"""
        try:
            import os as _os
            import shutil as _shutil
            
            if _os.path.exists(temp_dir):
                _shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass  # 静默失败，进程退出时无论如何都会释放
    
    def _cleanup_all(self):
        """清理所有资源"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.debug(f"[TempManager] ExitStack 清理: {self.temp_dir}")
    
    def create_temp_file(self, index: int, suffix: str = '.dav',
                        expected_size: int = 0) -> str:
        """创建受管理的临时文件"""
        if not self._check_space(expected_size):
            raise IOError(f"临时文件空间不足，需要 {expected_size} 字节")
        
        path = os.path.join(self.temp_dir, f"segment_{index:03d}{suffix}")
        self._tracked_files.append((index, path, expected_size))
        
        logger.debug(f"[TempManager] 创建临时文件: {path}")
        return path
    
    def _check_space(self, required_bytes: int) -> bool:
        """检查磁盘空间"""
        total, used, free = shutil.disk_usage(self.temp_dir)
        
        # 检查总限制
        if self._total_size + required_bytes > self.max_size:
            logger.warning(f"[TempManager] 超出最大限制 {self.max_size / 1024**3:.1f}GB")
            return False
        
        # 检查磁盘可用空间（保留 500MB）
        if free < required_bytes + 500 * 1024 * 1024:
            logger.warning(f"[TempManager] 磁盘空间不足，剩余 {free / 1024**3:.1f}GB")
            return False
        
        return True
    
    def update_file_size(self, index: int, actual_size: int):
        """更新文件实际大小"""
        for i, (idx, path, size) in enumerate(self._tracked_files):
            if idx == index:
                self._total_size += actual_size - size
                self._tracked_files[i] = (idx, path, actual_size)
                break
    
    def release_file(self, index: int):
        """释放临时文件 - 修复 TOCTOU 竞态条件"""
        for i, (idx, path, size) in enumerate(self._tracked_files):
            if idx == index:
                # 直接尝试删除，不预先检查存在性
                try:
                    os.remove(path)
                    self._total_size -= size
                    logger.debug(f"[TempManager] 删除临时文件: {path}")
                except FileNotFoundError:
                    pass  # 文件已被删除，忽略
                except OSError as e:
                    logger.warning(f"[TempManager] 删除失败: {e}")
                
                self._tracked_files.pop(i)
                break
    
    def get_temp_files_for_resume(self) -> List[Tuple[int, str, int]]:
        """获取可用于恢复的临时文件"""
        result = []
        for idx, path, size in self._tracked_files:
            if os.path.exists(path):
                actual_size = os.path.getsize(path)
                result.append((idx, path, actual_size))
        return result
    
    def close(self):
        """显式关闭，触发清理"""
        self._exit_stack.close()
        if self._finalizer.alive:
            self._finalizer()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# ============================================================================
# 3. 错误处理和执行器
# ============================================================================

class ErrorSeverity(Enum):
    """错误严重程度"""
    WARNING = "warning"
    RETRYABLE = "retryable"
    FATAL = "fatal"


class TaskError(Exception):
    """任务错误基类"""
    def __init__(
        self,
        message: str,
        severity: ErrorSeverity,
        segment_index: int = -1
    ):
        super().__init__(message)
        self.severity = severity
        self.segment_index = segment_index
        self.traceback_str = __import__('traceback').format_exc()


class CooperativeExecutor:
    """
    协作式执行器 - 管理下载和转换线程。
    
    特点：
    - 使用 ThreadPoolExecutor 管理线程
    - 统一的错误传播机制
    - 协作式取消支持
    """
    
    def __init__(self, task_id: str, max_workers: int = 2):
        self.task_id = task_id
        self.max_workers = max_workers
        self._shutdown_event = threading.Event()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._error_queue = queue.Queue()
    
    def __enter__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=f"Worker-{self.task_id[:8]}"
        )
        return self
    
    def __exit__(self, *args):
        self.shutdown()
    
    def submit(self, fn: Callable, *args, **kwargs):
        """提交任务，包装错误处理"""
        def wrapped():
            try:
                return fn(*args, **kwargs)
            except TaskError:
                raise
            except Exception as e:
                raise TaskError(f"Unexpected error: {e}", ErrorSeverity.FATAL) from e
        
        return self._executor.submit(wrapped)
    
    def post_error(self, error: TaskError):
        """发布错误"""
        self._error_queue.put(error)
    
    def check_should_stop(self) -> Optional[TaskError]:
        """检查是否应该停止 - 不丢弃非 FATAL 错误"""
        if self._shutdown_event.is_set():
            return TaskError("Shutdown requested", ErrorSeverity.FATAL)
        
        # 只查看错误，不取出，避免丢弃非 FATAL 错误
        # 实际错误处理在 _monitor_tasks 中通过 future.result() 完成
        return None
    
    def has_errors(self) -> bool:
        """检查是否有错误"""
        return not self._error_queue.empty()
    
    def shutdown(self, wait: bool = True, timeout: Optional[float] = None):
        """关闭执行器 - 支持超时避免永久阻塞"""
        self._shutdown_event.set()
        if self._executor:
            if timeout and timeout > 0:
                # 使用超时避免永久阻塞
                self._executor.shutdown(wait=False)
                # 等待任务完成，但最多等待 timeout 秒
                done, not_done = self._executor.wait(timeout=timeout)
                if not_done:
                    logger.warning(f"[CooperativeExecutor] {len(not_done)} 个任务未能在 {timeout}s 内完成")
            else:
                self._executor.shutdown(wait=wait)


# ============================================================================
# 4. 暂停控制器
# ============================================================================

class PauseState(Enum):
    """暂停状态"""
    RUNNING = auto()
    PAUSE_REQUESTED = auto()
    PAUSED = auto()


class PauseController:
    """
    暂停控制器 - 实现优雅暂停。
    
    流程：
    RUNNING → PAUSE_REQUESTED → PAUSED → RUNNING
    
    特点：
    - 当前段完成后再暂停
    - 状态机确保一致性
    """
    
    def __init__(self):
        self._state = PauseState.RUNNING
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()
    
    def request_pause(self) -> bool:
        """请求暂停"""
        with self._lock:
            if self._state != PauseState.RUNNING:
                return False
            self._state = PauseState.PAUSE_REQUESTED
            self._pause_event.clear()
            self._resume_event.clear()
            logger.debug("[PauseController] 暂停请求")
            return True
    
    def acknowledge_pause(self):
        """确认暂停（由工作线程调用）"""
        with self._lock:
            if self._state == PauseState.PAUSE_REQUESTED:
                self._state = PauseState.PAUSED
                self._pause_event.set()
                logger.debug("[PauseController] 已暂停")
    
    def request_resume(self) -> bool:
        """请求恢复"""
        with self._lock:
            if self._state != PauseState.PAUSED:
                return False
            self._state = PauseState.RUNNING
            self._resume_event.set()
            self._pause_event.clear()
            logger.debug("[PauseController] 恢复请求")
            return True
    
    def check_should_pause(self) -> bool:
        """检查是否应该暂停"""
        with self._lock:
            return self._state == PauseState.PAUSE_REQUESTED
    
    def is_running(self) -> bool:
        """检查是否正在运行（公共方法）"""
        with self._lock:
            return self._state == PauseState.RUNNING
    
    def wait_while_paused(self, timeout: Optional[float] = None):
        """在暂停状态下等待 - 使用事件而非忙等待"""
        # 如果当前是运行状态，立即返回
        with self._lock:
            if self._state == PauseState.RUNNING:
                return
        # 否则等待恢复事件
        self._resume_event.wait(timeout)


# ============================================================================
# 5. 信号定义
# ============================================================================

class WorkerSignals(QObject):
    """工作线程信号定义"""
    progress = pyqtSignal(str, str, int)      # task_id, phase, progress
    phase_changed = pyqtSignal(str, str)       # task_id, phase
    finished = pyqtSignal(str, bool, str)      # task_id, success, message
    log = pyqtSignal(str)                      # log_message
    segment_status_changed = pyqtSignal(str, int, str)  # task_id, index, status


# ============================================================================
# 6. 主工作类 - 并行下载器
# ============================================================================

class DownloadWorker(QRunnable):
    """
    下载工作线程 - 双线程并行处理版本。
    
    架构：
    - DownloadWorker (QRunnable): 主控，运行在 Qt 线程池
      - Download Thread: 持续下载，生产者
      - Convert Thread: 持续转换，消费者
      - Queue(maxsize=2): 下载→转换缓冲区
    
    特点：
    - 下载和转换并行执行
    - 使用 Actor 模式管理状态，无锁竞争
    - 三级保障防止临时文件泄漏
    - 优雅暂停/恢复
    """
    
    def __init__(self, task: DownloadTask):
        super().__init__()
        self.task = task
        self.device: Optional[Device] = None

        # 核心组件
        self._state_manager = TaskStateManager(task)
        self._temp_manager: Optional[TempFileManager] = None
        self._pause_controller = PauseController()
        self._executor: Optional[CooperativeExecutor] = None

        # 队列（下载→转换）
        self._convert_queue = queue.Queue(maxsize=2)

        # 信号
        self.signals = WorkerSignals()

        # 取消标志
        self._cancelled = threading.Event()

        # 统计
        self._download_count = 0
        self._convert_count = 0

        # 连接状态管理器信号
        self._state_manager.segment_changed.connect(
            lambda tid, idx, st: self.signals.segment_status_changed.emit(tid, idx, st)
        )
        self._state_manager.progress_updated.connect(
            lambda tid, prog: self.signals.progress.emit(tid, self.task.phase, prog)
        )
    
    def _emit_log(self, message: str):
        """发射日志"""
        self.signals.log.emit(message)
        logger.info(message)
    
    @pyqtSlot()
    def run(self):
        """主执行入口 - 添加详细日志"""
        logger.info(f"[DownloadWorker] 任务启动: {self.task.task_id}, "
                   f"通道: {self.task.channel}, "
                   f"段数: {self.task.matched_file_count}, "
                   f"转换: {self.task.convert_to_mp4}")
        
        try:
            # 检查是否已完成
            if self._check_already_completed():
                logger.info(f"[DownloadWorker] 任务已存在完整输出，跳过: {self.task.task_id}")
                self._finalize_success("已存在完整输出文件")
                return
            
            self.task.started_at = datetime.now()
            self.task.status = DownloadTask.STATUS_DOWNLOADING
            self.task.phase = "download"
            self.signals.phase_changed.emit(self.task.task_id, "download")

            # 在工作线程中创建设备并登录，避免阻塞 UI 主线程
            self.device = Device(
                ip=self.task.device_ip,
                port=self.task.device_port,
                http_port=80,
                username=self.task.device_username,
                password=self.task.device_password,
            )
            # 下载任务不需要自动重连/心跳，关闭以避免依赖工作线程事件循环
            self.device.enable_auto_reconnect(False)
            if not self.device.login():
                raise TaskError("设备登录失败", ErrorSeverity.FATAL)

            # 使用上下文管理器确保资源清理
            with TempFileManager(self.task.task_id) as temp_mgr:
                self._temp_manager = temp_mgr
                
                with CooperativeExecutor(self.task.task_id, max_workers=2) as executor:
                    self._executor = executor
                    
                    # 启动下载线程
                    logger.debug(f"[DownloadWorker] 启动下载线程: {self.task.task_id}")
                    download_future = executor.submit(self._download_loop)
                    
                    # 启动转换线程（如果启用转换）
                    if self.task.convert_to_mp4:
                        logger.debug(f"[DownloadWorker] 启动转换线程: {self.task.task_id}")
                        convert_future = executor.submit(self._convert_loop)
                    else:
                        # 不转换，转换线程直接结束
                        self._convert_queue.put(None)
                        convert_future = executor.submit(lambda: None)
                    
                    # 监控任务执行
                    self._monitor_tasks(download_future, convert_future)
                
                # 检查是否有错误
                if executor.has_errors():
                    error = executor.check_should_stop()
                    if error:
                        raise error
                
                self._finalize_success()
                
        except TaskError as e:
            logger.warning(f"[DownloadWorker] 任务错误: {self.task.task_id}, {e}")
            self._finalize_failure(str(e), e.segment_index)
        except Exception as e:
            logger.exception(f"[DownloadWorker] 任务异常: {self.task.task_id}, {e}")
            self._finalize_failure(str(e))
        finally:
            logger.info(f"[DownloadWorker] 任务结束，清理资源: {self.task.task_id}")
            if self.device is not None:
                try:
                    self.device.logout()
                except Exception:
                    pass
            self._state_manager.stop()
    
    def _monitor_tasks(self, download_future, convert_future):
        """监控任务执行，处理错误"""
        # as_completed 返回 Future 对象，不是 (name, future) 元组
        futures_map = {download_future: 'download', convert_future: 'convert'}
        
        for future in as_completed(futures_map):
            name = futures_map[future]
            
            # 检查是否应该停止
            error = self._executor.check_should_stop()
            if error:
                # 触发协作式取消
                self._cancelled.set()
                self._executor._shutdown_event.set()
                raise error
            
            # 获取结果（会抛出异常）
            try:
                # 不设置超时，等待任务自然完成
                future.result()
            except TaskError as e:
                self._executor.post_error(e)
                raise
            except Exception as e:
                error = TaskError(str(e), ErrorSeverity.FATAL)
                self._executor.post_error(error)
                raise error from e
    
    # _calculate_completed_bytes 已删除，使用 state_manager.get_completed_bytes() 替代
    
    def _download_loop(self):
        """下载循环 - 生产者"""
        files = self._load_matched_files()
        if not files:
            raise TaskError("所选时间范围内没有录像文件", ErrorSeverity.FATAL)
        
        self._state_manager.init_segments(len(files))
        self._emit_log(
            f"任务已选择 {len(files)} 个录像，总大小 "
            f"{self.task.total_bytes / (1024*1024):.2f} MB"
        )
        
        start_index = self.task.completed_segments
        
        for index in range(start_index, len(files)):
            # 检查取消
            if self._cancelled.is_set():
                self._emit_log(f"下载循环被取消，已处理 {index} 段")
                break
            
            # 检查暂停
            if self._pause_controller.check_should_pause():
                self._pause_controller.acknowledge_pause()
                self._emit_log(f"下载在第 {index} 段暂停")
                # 等待恢复
                while not self._cancelled.is_set():
                    if self._pause_controller.is_running():
                        break
                    self._pause_controller.wait_while_paused(timeout=0.1)
                if self._cancelled.is_set():
                    break
            
            # 执行下载
            # 修复：检查 files[index] 是否存在
            if index >= len(files) or files[index] is None:
                raise TaskError(f"第 {index} 段文件信息不存在", ErrorSeverity.FATAL, index)
            
            self._state_manager.update_segment(index, SegmentStatus.DOWNLOADING)
            self.task.current_file_index = index
            self.task.current_file_name = files[index].get("filename", "")
            
            temp_path = self._temp_manager.create_temp_file(index)
            
            try:
                success = self._download_segment(index, files[index], temp_path)
                
                if success:
                    file_size = os.path.getsize(temp_path)
                    self._temp_manager.update_file_size(index, file_size)
                    
                    self._state_manager.update_segment(
                        index, SegmentStatus.DOWNLOADED,
                        temp_path=temp_path, file_size=file_size
                    )
                    
                    # 放入转换队列
                    if self.task.convert_to_mp4:
                        try:
                            self._convert_queue.put((index, temp_path), block=True, timeout=30)
                            self._download_count += 1
                        except queue.Full:
                            raise TaskError(
                                f"转换队列已满，第 {index} 段无法入队",
                                ErrorSeverity.FATAL, index
                            )
                    else:
                        # 不转换，直接移动文件
                        output_path = self._segment_output_path(index, ".dav")
                        
                        # 修复：检查输出目录磁盘空间
                        import shutil as _shutil
                        file_size = os.path.getsize(temp_path)
                        output_dir = os.path.dirname(output_path) or "."
                        _, _, free = _shutil.disk_usage(output_dir)
                        if free < file_size + 100 * 1024 * 1024:  # 保留 100MB
                            raise TaskError(
                                f"输出目录磁盘空间不足，需要 {file_size/1024/1024:.2f}MB，"
                                f"剩余 {free/1024/1024:.2f}MB",
                                ErrorSeverity.FATAL, index
                            )
                        
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        shutil.move(temp_path, output_path)
                        self._state_manager.update_segment(
                            index, SegmentStatus.COMPLETED,
                            output_path=output_path
                        )
                        self._download_count += 1
                else:
                    self._state_manager.update_segment(index, SegmentStatus.FAILED)
                    raise TaskError(
                        f"下载第 {index} 段失败", ErrorSeverity.FATAL, index
                    )
                    
            except Exception as e:
                # 确保在异常时也发送结束标记，避免转换线程无限等待
                if self.task.convert_to_mp4:
                    self._emit_log("下载异常，发送结束标记到转换队列")
                    try:
                        self._convert_queue.put(None, timeout=1)
                    except queue.Full:
                        pass
                
                if isinstance(e, TaskError):
                    raise
                raise TaskError(
                    f"下载第 {index} 段时出错: {e}",
                    ErrorSeverity.FATAL, index
                ) from e
        
        # 发送结束标记
        if self.task.convert_to_mp4:
            self._emit_log("下载完成，发送结束标记到转换队列")
            self._convert_queue.put(None)
    
    def _convert_loop(self):
        """转换循环 - 消费者"""
        if not self.task.convert_to_mp4:
            return
        
        self.task.phase = "convert"
        self.signals.phase_changed.emit(self.task.task_id, "convert")
        
        while True:
            try:
                # 获取任务（带超时检查）
                item = self._convert_queue.get(timeout=0.5)
                
                # 结束标记
                if item is None:
                    self._emit_log("转换循环收到结束标记")
                    break
                
                index, temp_path = item
                
                # 检查取消 - 不处理此段，但记录以便恢复
                if self._cancelled.is_set():
                    # 记录未完成的段用于恢复
                    logger.info(f"[DownloadWorker] 取消时跳过段 {index}")
                    break
                
                # 检查暂停
                self._pause_controller.wait_while_paused(timeout=0.1)
                
                # 执行转换
                self._state_manager.update_segment(index, SegmentStatus.CONVERTING)
                
                output_path = self._segment_output_path(index, ".mp4")
                
                self._convert_segment(temp_path, output_path, index)
                
                # 标记完成
                self._state_manager.update_segment(
                    index, SegmentStatus.COMPLETED,
                    output_path=output_path
                )
                
                # 清理临时文件
                self._temp_manager.release_file(index)
                
                self._convert_count += 1
                self._emit_log(f"第 {index+1} 段转换完成")
                
            except queue.Empty:
                # 检查是否被取消或下载线程已结束
                if self._cancelled.is_set():
                    logger.info("[DownloadWorker] 转换线程检测到取消，退出")
                    break
                # 继续等待
                continue
            except Exception as e:
                if isinstance(e, TaskError):
                    raise
                raise TaskError(
                    f"转换时出错: {e}", ErrorSeverity.FATAL
                ) from e
    
    def _download_segment(self, index: int, file_info: dict, temp_path: str) -> bool:
        """下载单个段"""
        max_retries = 3
        
        # 使用弱引用避免闭包循环引用
        file_size_ref = file_info.get("size", 0) if file_info else 0
        
        for attempt in range(max_retries):
            if self._cancelled.is_set():
                return False
            
            try:
                filename = file_info.get("filename", "")
                self._emit_log(f"开始下载第 {index+1} 段: {filename}")
                
                # 修复：确保 file_size_ref 有效
                total_size = file_size_ref
                if not isinstance(total_size, (int, float)) or total_size < 0:
                    total_size = 0
                
                # 创建进度回调 - 优化：避免闭包循环引用
                # 使用局部变量捕获，避免直接引用 self
                state_mgr = self._state_manager
                cancel_event = self._cancelled
                task_ref = self.task
                completed_bytes_cache = state_mgr.get_completed_bytes
                current_index = index  # 捕获当前索引
                current_total_size = total_size  # 捕获当前文件大小
                
                def progress_callback(progress: int) -> bool:
                    # 修复：确保 progress 有效
                    if not isinstance(progress, (int, float)):
                        progress = 0
                    progress = max(0, min(100, progress))
                    
                    # 同步更新 downloaded_bytes 用于速度计算
                    if current_total_size > 0:
                        current_bytes = int(current_total_size * progress / 100)
                        completed = completed_bytes_cache()  # O(1) 获取缓存值
                        # 直接更新，不经过状态管理器队列，确保速度计算实时
                        task_ref.downloaded_bytes = completed + current_bytes
                    
                    # 异步更新状态管理器
                    state_mgr.update_progress(current_index, download_progress=progress)
                    return not cancel_event.is_set()
                
                success = self.device.download_by_name(
                    channel=self.task.channel,
                    filename=filename,
                    save_path=temp_path,
                    progress_callback=progress_callback,
                )
                
                if success and os.path.exists(temp_path):
                    file_size = os.path.getsize(temp_path)
                    if file_size >= 1024:  # 至少 1KB
                        self._emit_log(
                            f"第 {index+1} 段下载完成: {file_size/(1024*1024):.2f} MB"
                        )
                        return True
                    else:
                        raise RuntimeError(f"文件大小异常: {file_size} 字节")
                
                if attempt < max_retries - 1:
                    self._emit_log(f"第 {attempt+1} 次重试...")
                    time.sleep(1 * (attempt + 1))
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    self._emit_log(f"下载出错，准备重试: {e}")
                    time.sleep(1 * (attempt + 1))
                else:
                    raise
        
        return False
    
    def _convert_segment(self, input_path: str, output_path: str, index: int = 0):
        """转换单个段"""
        # 修复文件名冲突 - 使用循环确保唯一性
        original_path = output_path
        counter = 0
        while os.path.exists(output_path):
            if counter > 100:
                raise IOError(f"无法找到可用的文件名: {original_path}")
            
            base, ext = os.path.splitext(original_path)
            task_suffix = self.task.task_id[:8]
            output_path = f"{base}_{task_suffix}_{counter}{ext}"
            counter += 1
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            self._emit_log(f"跳过已存在的输出: {os.path.basename(output_path)}")
            return
        
        converter = FormatConverter()
        
        def progress_callback(progress: int) -> bool:
            self._state_manager.update_progress(index, convert_progress=progress)
            return not self._cancelled.is_set()
        
        converter.convert(
            input_path=input_path,
            output_path=output_path,
            progress_callback=progress_callback,
        )
    
    def _load_matched_files(self) -> List[dict]:
        """加载匹配的录像文件"""
        if self.task.matched_files:
            return list(self.task.matched_files)
        
        files = self.device.find_files(
            channel=self.task.channel,
            start=self.task.start_time,
            end=self.task.end_time,
        )
        self.task.set_matched_files(files)
        return files
    
    def _check_already_completed(self) -> bool:
        """检查任务是否已完成"""
        if not self.task.output_files:
            return False
        
        # 修复：正确处理 matched_file_count 为 0 的情况
        expected_count = self.task.matched_file_count
        if expected_count is None:
            expected_count = len(self.task.output_files)
        
        # 如果预期为 0，表示没有文件需要下载，不算完成
        if expected_count == 0:
            return False
        
        existing = [p for p in self.task.output_files if p and os.path.exists(p)]
        
        if len(existing) == expected_count:
            self.task.output_files = existing
            self.task.completed_segments = expected_count
            return True
        return False
    
    def _segment_output_path(self, segment_index: int, suffix: str) -> str:
        """生成段输出路径"""
        # 修复：检查 save_dir 有效性
        if not self.task.save_dir:
            raise ValueError("保存目录未设置")
        
        base_filename = self.task.get_segment_base_filename(segment_index)
        if not base_filename:
            base_filename = f"segment_{segment_index:03d}"
        
        output_path = os.path.join(self.task.save_dir, f"{base_filename}{suffix}")
        return output_path
    
    def _finalize_success(self, message: str = "完成"):
        """任务成功完成"""
        self.task.status = DownloadTask.STATUS_COMPLETED
        self.task.completed_at = datetime.now()
        self.task.progress = 100
        self.task.error_msg = ""
        
        logger.info(
            f"[DownloadWorker] 任务完成: {self.task.task_id}, "
            f"下载 {self._download_count} 段，转换 {self._convert_count} 段"
        )
        
        # 确保在主线程发射信号
        try:
            self.signals.finished.emit(self.task.task_id, True, message)
            logger.info(f"[DownloadWorker] finished 信号已发射")
        except Exception as e:
            logger.error(f"[DownloadWorker] 发射 finished 信号失败: {e}")
    
    def _finalize_cancelled(self):
        """任务被取消"""
        self.task.status = DownloadTask.STATUS_CANCELLED
        self.task.completed_at = datetime.now()
        self.task.error_msg = "用户取消"
        
        logger.info(f"[DownloadWorker] 任务已取消: {self.task.task_id}")
        self.signals.finished.emit(self.task.task_id, False, "已取消")
    
    def _finalize_failure(self, error_msg: str, segment_index: int = -1):
        """任务失败 - 记录详细错误信息"""
        # 修复：检查是否是被取消的任务
        if self.task.status == DownloadTask.STATUS_CANCELLED or self._cancelled.is_set():
            self._finalize_cancelled()
            return
            
        self.task.status = DownloadTask.STATUS_FAILED
        self.task.completed_at = datetime.now()
        self.task.error_msg = error_msg
        
        if segment_index >= 0:
            self.task.failed_segment_index = segment_index
        
        # 修复：记录详细错误信息和堆栈跟踪
        logger.error(
            f"[DownloadWorker] 任务失败: {self.task.task_id}, "
            f"错误: {error_msg}, 段: {segment_index}",
            exc_info=True  # 记录堆栈跟踪
        )
        
        if segment_index >= 0:
            self.task.failed_segment_index = segment_index
        
        logger.info(f"[DownloadWorker] 任务失败: {self.task.task_id} {error_msg}")
        self.signals.finished.emit(self.task.task_id, False, error_msg)
    
    def pause(self):
        """暂停任务"""
        self._pause_controller.request_pause()
        self._emit_log(f"任务暂停请求: {self.task.task_id}")
    
    def resume(self):
        """恢复任务"""
        self._pause_controller.request_resume()
        self._emit_log(f"任务恢复请求: {self.task.task_id}")
    
    def cancel(self):
        """取消任务"""
        self._cancelled.set()
        self.task.status = DownloadTask.STATUS_CANCELLED
        self._pause_controller.request_resume()  # 确保从暂停中恢复以便退出
        
        # 清空转换队列 - 不检查empty，直接尝试清空
        while True:
            try:
                self._convert_queue.get_nowait()
            except queue.Empty:
                break
        
        self._emit_log(f"任务已取消: {self.task.task_id}")


# 保持向后兼容
WorkerSignals = WorkerSignals
