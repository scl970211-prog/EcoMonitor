"""
下载管理标签页。
"""

import os
import subprocess
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

try:
    from core import DownloadManager, DownloadTask
except ImportError:
    from src.core import DownloadManager, DownloadTask

try:
    from ..theme import task_status_color, task_status_surface
except ImportError:
    from src.gui.theme import task_status_color, task_status_surface


class DownloadManagerTabV2(QWidget):
    """下载管理标签页。"""

    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self._download_manager = download_manager
        self._speed_samples = {}
        self._task_rows: dict[str, dict] = {}
        self._init_ui()
        self._connect_signals()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_table)
        self._timer.start(1000)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        stats_group = QGroupBox("统计信息")
        stats_layout = QHBoxLayout(stats_group)
        self.pending_label = QLabel("等待中: 0")
        self.active_label = QLabel("执行中: 0")
        self.completed_label = QLabel("已完成: 0")
        self.failed_label = QLabel("失败: 0")
        self.speed_label = QLabel("速度: 0.0 MB/s")
        for label in (
            self.pending_label,
            self.active_label,
            self.completed_label,
            self.failed_label,
            self.speed_label,
        ):
            stats_layout.addWidget(label)
        stats_layout.addStretch()
        self.total_progress = QProgressBar()
        self.total_progress.setMaximumWidth(220)
        stats_layout.addWidget(self.total_progress)
        layout.addWidget(stats_group)

        self.task_table = QTableWidget()
        self.task_table.setColumnCount(9)
        self.task_table.setHorizontalHeaderLabels(
            ["任务ID", "通道", "时间范围", "录像", "总大小", "状态", "进度", "速度", "操作"]
        )
        self.task_table.hideColumn(0)
        self.task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.task_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.task_table.setColumnWidth(1, 90)
        self.task_table.setColumnWidth(3, 150)
        self.task_table.setColumnWidth(4, 90)
        self.task_table.setColumnWidth(5, 110)
        self.task_table.setColumnWidth(6, 150)
        self.task_table.setColumnWidth(7, 90)
        self.task_table.setColumnWidth(8, 190)
        self.task_table.verticalHeader().setDefaultSectionSize(60)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.task_table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.clicked.connect(self._refresh_table)
        btn_layout.addWidget(refresh_btn)
        pause_all_btn = QPushButton("全部停止")
        pause_all_btn.clicked.connect(self._pause_all)
        btn_layout.addWidget(pause_all_btn)
        resume_all_btn = QPushButton("恢复/重试任务")
        resume_all_btn.clicked.connect(self._resume_all)
        btn_layout.addWidget(resume_all_btn)
        clear_btn = QPushButton("清理已完成")
        clear_btn.clicked.connect(self._clear_completed)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        self._download_manager.task_added.connect(self._on_task_added)
        self._download_manager.task_started.connect(self._on_task_started)
        self._download_manager.task_progress.connect(self._on_task_progress)
        self._download_manager.task_phase_changed.connect(self._on_phase_changed)
        self._download_manager.task_completed.connect(self._on_task_completed)

    @pyqtSlot(str)
    def _on_task_added(self, task_id: str):
        self._refresh_table()

    @pyqtSlot(str)
    def _on_task_started(self, task_id: str):
        self._refresh_table()

    @pyqtSlot(str, str, int)
    def _on_task_progress(self, task_id: str, phase: str, progress: int):
        self._update_task_row(task_id, progress)

    @pyqtSlot(str, str)
    def _on_phase_changed(self, task_id: str, phase: str):
        self._refresh_table()

    @pyqtSlot(str, bool, str)
    def _on_task_completed(self, task_id: str, success: bool, message: str):
        self._refresh_table()

    def _refresh_table(self):
        tasks = self._download_manager.get_all_tasks()

        if not hasattr(self, "_last_bytes"):
            self._last_bytes = 0
            self._last_time = 0

        now = time.time()
        active_tasks = [
            task for task in tasks
            if task.status in (DownloadTask.STATUS_DOWNLOADING, DownloadTask.STATUS_RECONNECTING)
        ]
        current_bytes = sum(getattr(task, "downloaded_bytes", 0) or 0 for task in active_tasks)
        elapsed = now - self._last_time if self._last_time else 1
        if elapsed > 0 and self._last_time > 0:
            speed_bps = (current_bytes - self._last_bytes) / elapsed
            self.speed_label.setText(f"速度: {max(speed_bps, 0) / (1024 * 1024):.1f} MB/s")
        else:
            self.speed_label.setText("速度: 0.0 MB/s")
        self._last_bytes = current_bytes
        self._last_time = now

        active_task_ids = {task.task_id for task in active_tasks}
        self._speed_samples = {
            task_id: sample for task_id, sample in self._speed_samples.items() if task_id in active_task_ids
        }

        desired_ids = [task.task_id for task in tasks]
        current_ids = set(self._task_rows.keys())
        desired_set = set(desired_ids)

        # 删除已不存在的任务行（从后往前删，避免索引变化）
        rows_to_remove = sorted(
            (tid for tid in current_ids if tid not in desired_set),
            key=lambda tid: self._task_rows[tid]["row"],
            reverse=True,
        )
        for tid in rows_to_remove:
            old_widget = self.task_table.cellWidget(self._task_rows[tid]["row"], 8)
            if old_widget is not None:
                old_widget.deleteLater()
            self.task_table.removeRow(self._task_rows[tid]["row"])
            del self._task_rows[tid]
        self._rebuild_row_indices()

        # 新增任务行（追加到末尾）
        for task in tasks:
            if task.task_id not in self._task_rows:
                row = self.task_table.rowCount()
                self.task_table.insertRow(row)
                self._create_task_row(row, task)
                self._task_rows[task.task_id] = {"row": row, "last_status": task.status}
        self._rebuild_row_indices()

        # 增量更新已有行
        pending = active = completed = failed = 0
        total_progress_sum = 0
        for task in tasks:
            row_info = self._task_rows[task.task_id]
            row = row_info["row"]
            self._update_task_row_data(row, task, now, row_info)
            row_info["last_status"] = task.status

            if task.status == DownloadTask.STATUS_PENDING:
                pending += 1
            elif task.status in (
                DownloadTask.STATUS_DOWNLOADING,
                DownloadTask.STATUS_CONVERTING,
                DownloadTask.STATUS_RECONNECTING,
            ):
                active += 1
                total_progress_sum += task.progress
            elif task.status == DownloadTask.STATUS_COMPLETED:
                completed += 1
                total_progress_sum += 100
            elif task.status == DownloadTask.STATUS_FAILED:
                failed += 1

        self.pending_label.setText(f"等待中: {pending}")
        self.active_label.setText(f"执行中: {active}")
        self.completed_label.setText(f"已完成: {completed}")
        self.failed_label.setText(f"失败: {failed}")
        self.total_progress.setValue((total_progress_sum // len(tasks)) if tasks else 0)

    def _rebuild_row_indices(self):
        """根据当前表格行顺序重建 task_id -> row 映射。"""
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item is not None:
                tid = item.text()
                if tid in self._task_rows:
                    self._task_rows[tid]["row"] = row

    def _create_task_row(self, row: int, task: DownloadTask):
        """创建新任务行控件（仅首次插入时调用）。"""
        self.task_table.setItem(row, 0, QTableWidgetItem(task.task_id))
        self.task_table.setItem(row, 1, QTableWidgetItem(f"CH{task.channel:02d}"))
        self.task_table.setItem(row, 2, QTableWidgetItem(self._format_time_range(task)))
        self.task_table.setItem(row, 3, QTableWidgetItem(self._format_segment_info(task)))
        self.task_table.setItem(row, 4, QTableWidgetItem(self._format_total_size(task.total_bytes)))

        status_item = QTableWidgetItem(self._get_status_text(task))
        status_item.setForeground(QColor(self._get_status_color(task.status)))
        self.task_table.setItem(row, 5, status_item)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(task.progress or 0))
        progress_bar.setFormat(f"{int(task.progress or 0)}%")
        self.task_table.setCellWidget(row, 6, progress_bar)

        speed_item = QTableWidgetItem("-")
        self.task_table.setItem(row, 7, speed_item)

        self.task_table.setCellWidget(row, 8, self._build_action_widget(task))

    def _update_task_row_data(self, row: int, task: DownloadTask, now: float, row_info: dict):
        """更新已有任务行数据，仅在状态变化时重建操作按钮。"""
        self.task_table.item(row, 1).setText(f"CH{task.channel:02d}")
        self.task_table.item(row, 2).setText(self._format_time_range(task))
        self.task_table.item(row, 3).setText(self._format_segment_info(task))
        self.task_table.item(row, 4).setText(self._format_total_size(task.total_bytes))

        status_item = self.task_table.item(row, 5)
        status_item.setText(self._get_status_text(task))
        status_item.setForeground(QColor(self._get_status_color(task.status)))

        progress_bar = self.task_table.cellWidget(row, 6)
        if isinstance(progress_bar, QProgressBar):
            progress_bar.setValue(int(task.progress or 0))
            progress_bar.setFormat(f"{int(task.progress or 0)}%")

        speed_text = "-"
        if task.status == DownloadTask.STATUS_DOWNLOADING:
            speed_text = self._format_task_speed(task.task_id, task.downloaded_bytes, now)
        self.task_table.item(row, 7).setText(speed_text)

        if row_info.get("last_status") != task.status:
            old_widget = self.task_table.cellWidget(row, 8)
            if old_widget is not None:
                old_widget.deleteLater()
            self.task_table.setCellWidget(row, 8, self._build_action_widget(task))

    def _format_time_range(self, task: DownloadTask) -> str:
        return (
            f"{task.start_time.strftime('%m-%d %H:%M')} ~ "
            f"{task.end_time.strftime('%m-%d %H:%M')}"
        )

    def _build_action_widget(self, task: DownloadTask):
        widget = QWidget()
        btn_layout = QGridLayout(widget)
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setHorizontalSpacing(4)
        btn_layout.setVerticalSpacing(4)
        column = 0
        row = 0

        def add_button(button: QPushButton):
            nonlocal column, row
            btn_layout.addWidget(button, row, column)
            column += 1
            if column >= 2:
                column = 0
                row += 1

        if task.status in (
            DownloadTask.STATUS_DOWNLOADING,
            DownloadTask.STATUS_CONVERTING,
            DownloadTask.STATUS_RECONNECTING,
        ):
            stop_btn = QPushButton("停止")
            stop_btn.setFixedSize(72, 24)
            stop_btn.clicked.connect(lambda checked=False, tid=task.task_id: self._pause_task(tid))
            add_button(stop_btn)
        elif task.status in (DownloadTask.STATUS_PAUSED, DownloadTask.STATUS_FAILED):
            resume_btn = QPushButton("重试")
            resume_btn.setFixedSize(72, 24)
            resume_btn.clicked.connect(lambda checked=False, tid=task.task_id: self._resume_task(tid))
            add_button(resume_btn)

        if task.status in (
            DownloadTask.STATUS_PENDING,
            DownloadTask.STATUS_DOWNLOADING,
            DownloadTask.STATUS_CONVERTING,
            DownloadTask.STATUS_RECONNECTING,
        ):
            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedSize(72, 24)
            cancel_btn.clicked.connect(lambda checked=False, tid=task.task_id: self._cancel_task(tid))
            add_button(cancel_btn)

        dir_btn = QPushButton("目录")
        dir_btn.setFixedSize(72, 24)
        dir_btn.clicked.connect(lambda checked=False, tid=task.task_id: self._open_task_output(tid))
        add_button(dir_btn)

        segments_btn = QPushButton("下载详情")
        segments_btn.setFixedSize(72, 24)
        segments_btn.clicked.connect(lambda checked=False, tid=task.task_id: self._show_segment_list(tid))
        segments_btn.setEnabled(bool(task.matched_file_count))
        add_button(segments_btn)

        return widget

    def _update_task_row(self, task_id: str, progress: int):
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.text() == task_id:
                progress_bar = self.task_table.cellWidget(row, 6)
                if progress_bar:
                    progress_bar.setValue(progress)
                    progress_bar.setFormat(f"{progress}%")
                break

    def _format_segment_info(self, task: DownloadTask) -> str:
        if not task.matched_file_count:
            return "-"
        parts = [f"{task.completed_segments}/{task.matched_file_count} 已下载"]
        if task.current_file_index >= 0 and task.status in (
            DownloadTask.STATUS_DOWNLOADING,
            DownloadTask.STATUS_CONVERTING,
            DownloadTask.STATUS_RECONNECTING,
        ):
            parts.append(f"当前 {task.current_file_index + 1}/{task.matched_file_count}")
        return " | ".join(parts)

    def _format_total_size(self, total_bytes: int) -> str:
        if not total_bytes:
            return "-"
        return f"{total_bytes / (1024 * 1024):.1f} MB"

    def _get_status_text(self, task: DownloadTask) -> str:
        status_map = {
            DownloadTask.STATUS_PENDING: "等待中",
            DownloadTask.STATUS_DOWNLOADING: "下载中",
            DownloadTask.STATUS_DOWNLOADED: "已下载",
            DownloadTask.STATUS_CONVERTING: "后处理中",
            DownloadTask.STATUS_RECONNECTING: "重连中",
            DownloadTask.STATUS_COMPLETED: "已完成",
            DownloadTask.STATUS_FAILED: "失败",
            DownloadTask.STATUS_PAUSED: "已暂停",
            DownloadTask.STATUS_CANCELLED: "已取消",
        }
        base = status_map.get(task.status, task.status)
        if task.status == DownloadTask.STATUS_FAILED and task.failed_segment_index >= 0:
            return f"{base}（第 {task.failed_segment_index + 1} 段）"
        return base

    def _get_status_color(self, status: str) -> str:
        return task_status_color(status)

    def _show_context_menu(self, position):
        row = self.task_table.rowAt(position.y())
        if row < 0:
            return

        self.task_table.selectRow(row)
        task_id = self.task_table.item(row, 0).text()
        menu = QMenu()

        open_folder_action = QAction("打开输出目录", self)
        open_folder_action.triggered.connect(lambda: self._open_task_output(task_id))
        menu.addAction(open_folder_action)

        segment_action = QAction("查看下载详情", self)
        segment_action.triggered.connect(lambda: self._show_segment_list(task_id))
        menu.addAction(segment_action)

        task = self._download_manager.get_task_status(task_id)
        if task and task.status == DownloadTask.STATUS_FAILED:
            error_action = QAction("查看错误详情", self)
            error_action.triggered.connect(lambda: self._show_error_detail(task_id))
            menu.addAction(error_action)

        menu.exec(self.task_table.viewport().mapToGlobal(position))

    def _show_error_detail(self, task_id: str):
        task = self._download_manager.get_task_status(task_id)
        if not task:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("错误详情")
        dialog.setMinimumSize(480, 280)
        layout = QVBoxLayout(dialog)
        info = QLabel(
            f"任务ID: {task.task_id}\n"
            f"通道: CH{task.channel:02d}\n"
            f"失败阶段: {task.last_error_stage or '未知'}"
        )
        layout.addWidget(info)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(task.error_msg or "无错误信息")
        layout.addWidget(text)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _show_segment_list(self, task_id: str):
        task = self._download_manager.get_task_status(task_id)
        if not task:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("下载详情")
        dialog.setMinimumSize(900, 450)
        layout = QVBoxLayout(dialog)
        
        # 计算各状态数量
        completed = task.completed_segments
        current = 1 if (task.current_file_index >= 0 and task.current_file_index < task.matched_file_count and 
                       task.status in [DownloadTask.STATUS_DOWNLOADING, DownloadTask.STATUS_CONVERTING, DownloadTask.STATUS_RECONNECTING]) else 0
        pending = max(task.matched_file_count - completed - current, 0)
        
        summary = QLabel(
            f"总计 {task.matched_file_count} 个录像 | "
            f"<span style='color:green'>已完成: {completed}</span> | "
            f"<span style='color:blue'>进行中: {current}</span> | "
            f"<span style='color:gray'>排队中: {pending}</span> | "
            f"总大小: {self._format_total_size(task.total_bytes)}"
        )
        summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(summary)

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["序号", "文件名", "文件大小", "开始时间", "结束时间", "状态"])
        table.setRowCount(len(task.matched_files))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 60)
        table.setColumnWidth(2, 90)
        table.setColumnWidth(3, 150)
        table.setColumnWidth(4, 150)
        table.setColumnWidth(5, 80)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        for index, file_info in enumerate(task.matched_files):
            size_mb = int(file_info.get("size", 0) or 0) / (1024 * 1024)
            start = file_info.get("start")
            end = file_info.get("end")
            filename = file_info.get("filename", "")
            start_text = start.strftime("%Y-%m-%d %H:%M:%S") if hasattr(start, "strftime") else str(start or "-")
            end_text = end.strftime("%Y-%m-%d %H:%M:%S") if hasattr(end, "strftime") else str(end or "-")
            
            # 确定状态
            if index < task.completed_segments:
                status = "已完成"
                segment_status = "completed"
                status_color = QColor(task_status_color(segment_status))
            elif index == task.current_file_index and task.status in [
                DownloadTask.STATUS_DOWNLOADING,
                DownloadTask.STATUS_CONVERTING,
                DownloadTask.STATUS_RECONNECTING
            ]:
                if task.status == DownloadTask.STATUS_DOWNLOADING:
                    status = "下载中"
                    segment_status = "downloading"
                elif task.status == DownloadTask.STATUS_CONVERTING:
                    status = "转换中"
                    segment_status = "converting"
                elif task.status == DownloadTask.STATUS_RECONNECTING:
                    status = "重连中"
                    segment_status = "reconnecting"
                else:
                    status = "进行中"
                    segment_status = "downloading"
                status_color = QColor(task_status_color(segment_status))
            else:
                status = "排队中"
                segment_status = "pending"
                status_color = QColor(task_status_color(segment_status))

            # 创建状态项（带颜色）
            status_item = QTableWidgetItem(status)
            status_item.setForeground(status_color)
            status_item.setFont(QFont("Microsoft YaHei", 9, QFont.Bold if status in ["下载中", "转换中", "重连中"] else QFont.Normal))

            table.setItem(index, 0, QTableWidgetItem(str(index + 1)))
            table.setItem(index, 1, QTableWidgetItem(filename))
            table.setItem(index, 2, QTableWidgetItem(f"{size_mb:.2f} MB"))
            table.setItem(index, 3, QTableWidgetItem(start_text))
            table.setItem(index, 4, QTableWidgetItem(end_text))
            table.setItem(index, 5, status_item)

            # 根据状态设置行背景色
            for col in range(6):
                item = table.item(index, col)
                if item:
                    item.setBackground(QColor(task_status_surface(segment_status)))
        layout.addWidget(table)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _pause_task(self, task_id: str):
        self._download_manager.pause_task(task_id)

    def _resume_task(self, task_id: str):
        self._download_manager.resume_task(task_id)

    def _cancel_task(self, task_id: str):
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要取消这个任务吗？已下载的临时分段会被清理。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_manager.cancel_task(task_id)

    def _open_task_output(self, task_id: str):
        task = self._download_manager.get_task_status(task_id)
        if not task:
            return

        import platform
        system = platform.system()

        for output_path in task.output_files:
            if output_path and os.path.exists(output_path):
                if system == "Windows":
                    subprocess.run(["explorer", "/select,", os.path.normpath(output_path)])
                elif system == "Darwin":  # macOS
                    subprocess.run(["open", "-R", output_path])
                else:  # Linux
                    subprocess.run(["xdg-open", os.path.dirname(output_path)])
                return

        folder = task.save_dir
        if folder and os.path.exists(folder):
            if system == "Windows":
                subprocess.run(["explorer", os.path.normpath(folder)])
            elif system == "Darwin":  # macOS
                subprocess.run(["open", folder])
            else:  # Linux
                subprocess.run(["xdg-open", folder])

    def _pause_all(self):
        self._download_manager.pause_all()

    def _resume_all(self):
        self._download_manager.resume_all()

    def _clear_completed(self):
        removed = self._download_manager.clear_finished()
        self._refresh_table()
        QMessageBox.information(self, "提示", f"已清理 {removed} 个历史任务")

    def _format_task_speed(self, task_id: str, downloaded_bytes: int, now: float) -> str:
        last_bytes, last_time = self._speed_samples.get(task_id, (downloaded_bytes, now))
        self._speed_samples[task_id] = (downloaded_bytes, now)
        elapsed = now - last_time
        if elapsed <= 0:
            return "0.0 MB/s"
        speed_bps = max(downloaded_bytes - last_bytes, 0) / elapsed
        return f"{speed_bps / (1024 * 1024):.1f} MB/s"
