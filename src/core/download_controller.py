"""
下载任务编排，负责队列、重试、暂停恢复和持久化。
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QMutex, QMutexLocker, QThreadPool, pyqtSignal

from .database import Database
from .device import Device
from .download_task import DownloadTask
from .download_worker import DownloadWorker
from .path_resolver import get_temp_dir


class DownloadManager(QObject):
    task_added = pyqtSignal(str)
    task_started = pyqtSignal(str)
    task_progress = pyqtSignal(str, str, int)
    task_phase_changed = pyqtSignal(str, str)
    task_completed = pyqtSignal(str, bool, str)
    task_log = pyqtSignal(str)
    all_completed = pyqtSignal()

    def __init__(self, max_concurrent: int = 2):
        super().__init__()

        self.max_concurrent = max_concurrent
        self._db = Database()
        self._pending_tasks: List[DownloadTask] = []
        self._active_workers: Dict[str, DownloadWorker] = {}
        self._archived_tasks: Dict[str, DownloadTask] = {}
        self._is_running = True
        self._lock = QMutex()  # 使用 QMutex 替代 threading.Lock，与 Qt 线程兼容

        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(max_concurrent + 2)

        self._db_update_interval = 5
        self._db_progress_threshold = 5
        self._last_db_update: Dict[str, float] = {}
        self._last_db_progress: Dict[str, int] = {}

        self._restore_tasks()

    def _log(self, message: str):
        self.task_log.emit(message)

    def _restore_tasks(self):
        try:
            for task_data in self._db.get_tasks_by_statuses([DownloadTask.STATUS_PENDING]):
                self._pending_tasks.append(DownloadTask.from_dict(task_data))

            for task_data in self._db.get_tasks_by_statuses(
                [
                    DownloadTask.STATUS_PAUSED,
                    DownloadTask.STATUS_FAILED,
                    DownloadTask.STATUS_CANCELLED,
                    DownloadTask.STATUS_COMPLETED,
                ]
            ):
                task = DownloadTask.from_dict(task_data)
                self._archived_tasks[task.task_id] = task

            if self._pending_tasks:
                self._log(f"恢复 {len(self._pending_tasks)} 个待执行任务")
        except Exception as exc:
            self._log(f"[错误] 恢复任务失败: {exc}")

    def _archive_task(self, task: DownloadTask):
        self._archived_tasks[task.task_id] = task
        self._db.save_task(task.to_dict())

    def _pop_pending_task(self, task_id: str) -> Optional[DownloadTask]:
        for index, task in enumerate(self._pending_tasks):
            if task.task_id == task_id:
                return self._pending_tasks.pop(index)
        return None

    def add_task(self, device: Optional[Device] = None, task: Optional[DownloadTask] = None) -> str:
        if task is None:
            raise ValueError("task is required")

        task.status = DownloadTask.STATUS_PENDING
        task.phase = ""
        task.progress = 0 if task.completed_segments == 0 else task.progress
        task.error_msg = ""
        task.started_at = None
        task.completed_at = None
        task.retry_count = 0
        task.failed_segment_index = -1
        task.last_error_stage = ""
        task.current_file_name = ""
        if not task.temp_dav_path:
            task.generate_temp_path(str(get_temp_dir()))

        self._db.save_task(task.to_dict())

        with QMutexLocker(self._lock):
            self._archived_tasks.pop(task.task_id, None)
            self._pending_tasks.append(task)

        self.task_added.emit(task.task_id)
        self._log(
            f"任务已加入队列: CH{task.channel:02d} {task.start_time:%Y-%m-%d %H:%M:%S} "
            f"到 {task.end_time:%Y-%m-%d %H:%M:%S}"
        )
        self._process_queue()
        return task.task_id

    def add_batch_tasks(self, device: Optional[Device], tasks: List[DownloadTask]) -> List[str]:
        return [self.add_task(device, task) for task in tasks]

    def _process_queue(self):
        tasks_to_start: List[DownloadTask] = []
        with QMutexLocker(self._lock):
            if not self._is_running:
                return

            while len(self._active_workers) + len(tasks_to_start) < self.max_concurrent and self._pending_tasks:
                tasks_to_start.append(self._pending_tasks.pop(0))

        for task in tasks_to_start:
            self._start_task(task)

    def _start_task(self, task: DownloadTask):
        device = None
        try:
            device = Device(
                ip=task.device_ip,
                port=task.device_port,
                http_port=80,
                username=task.device_username,
                password=task.device_password,
            )

            if not device.login():
                raise RuntimeError("设备登录失败")

            worker = DownloadWorker(device, task)
            worker.signals.progress.connect(self._on_progress)
            worker.signals.phase_changed.connect(self._on_phase_changed)
            worker.signals.log.connect(self._log)

            def on_finished_wrapper(task_id, success, message):
                try:
                    device.logout()
                except Exception as exc:
                    self._log(f"[警告] 设备登出失败: {task.device_ip} {exc}")
                self._on_finished(task_id, success, message)

            worker.signals.finished.connect(on_finished_wrapper)

            with QMutexLocker(self._lock):
                self._active_workers[task.task_id] = worker

            self._thread_pool.start(worker)
            self.task_started.emit(task.task_id)
            self._db.save_task(task.to_dict())
            self._log(
                f"开始执行任务: CH{task.channel:02d}，已选择 {task.matched_file_count or '?'} 个录像"
            )
        except Exception as exc:
            # 确保设备连接被关闭
            if device:
                try:
                    device.logout()
                except Exception:
                    pass
            task.status = DownloadTask.STATUS_FAILED
            task.error_msg = str(exc)
            task.last_error_stage = "connect"
            task.completed_at = datetime.now()
            self._archive_task(task)
            self.task_completed.emit(task.task_id, False, str(exc))
            self._log(f"[错误] 启动任务失败: {task.task_id} {exc}")
            self._process_queue()

    def _on_progress(self, task_id: str, phase: str, progress: int):
        self.task_progress.emit(task_id, phase, progress)

        task = None
        if task_id in self._active_workers:
            task = self._active_workers[task_id].task
            task.progress = progress
            task.phase = phase

        current_time = time.time()
        last_time = self._last_db_update.get(task_id, 0)
        last_progress = self._last_db_progress.get(task_id, 0)
        should_update = (
            current_time - last_time >= self._db_update_interval
            or abs(progress - last_progress) >= self._db_progress_threshold
            or progress in (0, 100)
        )

        if should_update and task is not None:
            self._db.save_task(task.to_dict())
            self._last_db_update[task_id] = current_time
            self._last_db_progress[task_id] = progress

    def _on_phase_changed(self, task_id: str, phase: str):
        if task_id in self._active_workers:
            self._active_workers[task_id].task.phase = phase
        self.task_phase_changed.emit(task_id, phase)

    def _on_finished(self, task_id: str, success: bool, message: str):
        task = None
        with QMutexLocker(self._lock):
            worker = self._active_workers.pop(task_id, None)
            if worker is not None:
                task = worker.task

        if task is not None:
            self._archive_task(task)
            summary = (
                f"任务完成: CH{task.channel:02d}，"
                f"{'成功' if success else '失败'}，"
                f"已选择 {task.matched_file_count} 个录像，"
                f"已完成 {task.completed_segments}/{task.matched_file_count} 个"
            )
            if message:
                summary = f"{summary}，{message}"
            self._log(summary)

        self.task_completed.emit(task_id, success, message)
        self._process_queue()

        with QMutexLocker(self._lock):
            if not self._pending_tasks and not self._active_workers:
                self.all_completed.emit()

    def pause_task(self, task_id: str):
        with QMutexLocker(self._lock):
            task = self._pop_pending_task(task_id)
            worker = self._active_workers.get(task_id)

        if task is not None:
            task.status = DownloadTask.STATUS_PAUSED
            task.completed_at = datetime.now()
            self._archive_task(task)
            self.task_completed.emit(task.task_id, False, "已暂停")
            self._log(f"任务已暂停: {task.task_id}")
            return

        if worker is not None:
            worker.pause()

    def cancel_task(self, task_id: str):
        with QMutexLocker(self._lock):
            task = self._pop_pending_task(task_id)
            worker = self._active_workers.get(task_id)

        if task is not None:
            task.status = DownloadTask.STATUS_CANCELLED
            task.completed_at = datetime.now()
            self._archive_task(task)
            self.task_completed.emit(task.task_id, False, "已取消")
            self._log(f"任务已取消: {task.task_id}")
            return

        if worker is not None:
            worker.cancel()

    def resume_task(self, task_id: str) -> bool:
        task = self.get_task_status(task_id)
        if task is None:
            return False

        if task.status not in (DownloadTask.STATUS_PAUSED, DownloadTask.STATUS_FAILED):
            return False

        task.status = DownloadTask.STATUS_PENDING
        task.error_msg = ""
        task.started_at = None
        task.completed_at = None
        task.retry_count = 0
        task.failed_segment_index = -1
        task.last_error_stage = ""
        self._is_running = True
        if not task.temp_dav_path:
            task.generate_temp_path(str(get_temp_dir()))

        self.add_task(task=task)
        self._log(
            f"任务恢复: {task.task_id}，将从第 {task.completed_segments + 1}/{max(task.matched_file_count, 1)} 段继续"
        )
        return True

    def pause_all(self):
        self._is_running = False
        with QMutexLocker(self._lock):
            pending_tasks = list(self._pending_tasks)
            self._pending_tasks.clear()

        for task in pending_tasks:
            task.status = DownloadTask.STATUS_PAUSED
            task.completed_at = datetime.now()
            self._archive_task(task)
            self.task_completed.emit(task.task_id, False, "已暂停")

        for worker in list(self._active_workers.values()):
            worker.pause()

        self._log("已暂停所有任务")

    def resume_all(self):
        self._is_running = True
        resume_ids = [
            task_id
            for task_id, task in list(self._archived_tasks.items())
            if task.status in (DownloadTask.STATUS_PAUSED, DownloadTask.STATUS_FAILED)
        ]
        for task_id in resume_ids:
            self.resume_task(task_id)
        self._process_queue()

    def clear_finished(self, statuses: Optional[List[str]] = None) -> int:
        statuses = statuses or [
            DownloadTask.STATUS_COMPLETED,
            DownloadTask.STATUS_FAILED,
            DownloadTask.STATUS_CANCELLED,
        ]

        with QMutexLocker(self._lock):
            self._archived_tasks = {
                task_id: task
                for task_id, task in self._archived_tasks.items()
                if task.status not in statuses
            }

        return self._db.delete_tasks_by_statuses(statuses)

    def shutdown(self, timeout_ms: int = 5000):
        self._is_running = False
        for worker in list(self._active_workers.values()):
            worker.pause()
        self._thread_pool.waitForDone(timeout_ms)

    def get_task_status(self, task_id: str) -> Optional[DownloadTask]:
        with QMutexLocker(self._lock):
            if task_id in self._active_workers:
                return self._active_workers[task_id].task

            for task in self._pending_tasks:
                if task.task_id == task_id:
                    return task

            if task_id in self._archived_tasks:
                return self._archived_tasks[task_id]

        task_data = self._db.get_task(task_id)
        if task_data:
            return DownloadTask.from_dict(task_data)
        return None

    def get_all_tasks(self) -> List[DownloadTask]:
        task_map: Dict[str, DownloadTask] = {}

        with QMutexLocker(self._lock):
            for worker in self._active_workers.values():
                task_map[worker.task.task_id] = worker.task
            for task in self._pending_tasks:
                task_map[task.task_id] = task
            for task_id, task in self._archived_tasks.items():
                task_map[task_id] = task

        for task_data in self._db.get_recent_tasks(100):
            task = DownloadTask.from_dict(task_data)
            task_map.setdefault(task.task_id, task)

        return sorted(task_map.values(), key=lambda task: task.created_at, reverse=True)

    def get_stats(self) -> dict:
        tasks = self.get_all_tasks()
        completed = sum(1 for task in tasks if task.status == DownloadTask.STATUS_COMPLETED)
        return {
            "pending": sum(1 for task in tasks if task.status == DownloadTask.STATUS_PENDING),
            "active": sum(
                1
                for task in tasks
                if task.status in (
                    DownloadTask.STATUS_DOWNLOADING,
                    DownloadTask.STATUS_CONVERTING,
                    DownloadTask.STATUS_RECONNECTING,
                )
            ),
            "completed": completed,
            "max_concurrent": self.max_concurrent,
        }
