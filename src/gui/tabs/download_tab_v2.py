"""
批量下载标签页。
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Tuple

from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from core import Device, DownloadManager, DownloadTask, get_temp_dir
    from core.format_converter import FormatConverter
except ImportError:
    from src.core import Device, DownloadManager, DownloadTask, get_temp_dir
    from src.core.format_converter import FormatConverter

try:
    from ..theme import get_theme_manager, set_status_style, set_text_style, text_color
    from ...utils.config import get_config
    from ...utils.crypto import decrypt_password
except ImportError:
    from src.gui.theme import get_theme_manager, set_status_style, set_text_style, text_color
    from src.utils.config import get_config
    from src.utils.crypto import decrypt_password


logger = logging.getLogger(__name__)


class DownloadTabV2(QWidget):
    """批量下载标签页。"""

    log_message = pyqtSignal(str)
    CHANNEL_ID_ROLE = Qt.ItemDataRole.UserRole
    CHANNEL_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
    CHANNEL_STATS_ROLE = Qt.ItemDataRole.UserRole + 2
    _tc = get_theme_manager().colors()
    PRIMARY_BUTTON_STYLE = (
        "QPushButton{font-size: 14px; padding: 10px 30px;}"
        f"QPushButton:disabled{{background-color: {_tc.text_disabled}; color: {_tc.text_secondary};}}"
    )

    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self._download_manager = download_manager
        self._device: Device = None
        self._device_info: dict = None
        self._channel_file_cache: Dict[Tuple[int, str, str], List[dict]] = {}
        self._last_retrieval_result: Dict[str, object] = {}
        self._storage_ready = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        task_group = QGroupBox("下载参数")
        task_layout = QGridLayout(task_group)
        task_layout.setHorizontalSpacing(8)
        task_layout.setVerticalSpacing(6)
        task_layout.setColumnStretch(1, 1)
        task_layout.setColumnStretch(3, 1)

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

        task_layout.addWidget(QLabel("选择通道:"), 0, 0)

        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.channel_list.setMaximumHeight(180)

        channel_btn_widget = QWidget()
        channel_btn_layout = QHBoxLayout(channel_btn_widget)
        channel_btn_layout.setContentsMargins(0, 0, 0, 0)
        channel_btn_layout.setSpacing(4)

        select_all_btn = QPushButton("全选")
        select_all_btn.setObjectName("smallBtn")
        select_all_btn.setMinimumHeight(30)
        select_all_btn.setMinimumWidth(64)
        select_all_btn.clicked.connect(self.channel_list.selectAll)
        channel_btn_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.setObjectName("smallBtn")
        deselect_all_btn.setMinimumHeight(30)
        deselect_all_btn.setMinimumWidth(76)
        deselect_all_btn.clicked.connect(self.channel_list.clearSelection)
        channel_btn_layout.addWidget(deselect_all_btn)

        channel_btn_layout.addStretch()

        task_layout.addWidget(channel_btn_widget, 0, 1, 1, 3)
        task_layout.addWidget(self.channel_list, 1, 1, 1, 3)

        task_layout.addWidget(QLabel("开始时间:"), 2, 0)
        self.start_time = QDateTimeEdit()
        self.start_time.setCalendarPopup(True)
        self.start_time.setDateTime(QDateTime(today_start))
        self.start_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time.setCurrentSection(QDateTimeEdit.Section.HourSection)
        self.start_time.setWrapping(True)
        task_layout.addWidget(self.start_time, 2, 1)

        task_layout.addWidget(QLabel("结束时间:"), 2, 2)
        self.end_time = QDateTimeEdit()
        self.end_time.setCalendarPopup(True)
        self.end_time.setDateTime(QDateTime(today_end))
        self.end_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_time.setCurrentSection(QDateTimeEdit.Section.HourSection)
        self.end_time.setWrapping(True)
        task_layout.addWidget(self.end_time, 2, 3)

        task_layout.addWidget(QLabel("保存目录:"), 3, 0)
        self.save_dir_input = QLineEdit()
        self.save_dir_input.setPlaceholderText("请选择录像保存目录...")
        task_layout.addWidget(self.save_dir_input, 3, 1, 1, 2)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_save_dir)
        task_layout.addWidget(browse_btn, 3, 3)

        self.disk_space_label = QLabel("")
        self.disk_space_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 8pt; padding-left: 4px;")
        task_layout.addWidget(self.disk_space_label, 4, 1, 1, 3)
        layout.addWidget(task_group)

        options_group = QGroupBox("转换选项")
        options_layout = QVBoxLayout(options_group)
        self.converter = FormatConverter()
        self.ffmpeg_available = self.converter.is_available()

        self.convert_checkbox = QCheckBox("下载后自动转换为 MP4 格式")
        self.convert_checkbox.setChecked(self.ffmpeg_available)
        self.convert_checkbox.setEnabled(self.ffmpeg_available)
        if not self.ffmpeg_available:
            self.convert_checkbox.setToolTip("FFmpeg 未安装，请到连接页面安装")
        options_layout.addWidget(self.convert_checkbox)
        layout.addWidget(options_group)

        hint_layout = QHBoxLayout()
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.addStretch()
        self.storage_hint_label = QLabel("请先检索录像")
        self.storage_hint_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 10pt; padding: 0 8px;")
        hint_layout.addWidget(self.storage_hint_label)
        hint_layout.addStretch()
        layout.addLayout(hint_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        self.retrieve_btn = QPushButton("检索录像")
        self.retrieve_btn.setObjectName("largeSecondaryBtn")
        self.retrieve_btn.clicked.connect(self._retrieve_recordings)
        btn_layout.addWidget(self.retrieve_btn)
        self.add_task_btn = QPushButton("下载录像")
        self.add_task_btn.setStyleSheet(self.PRIMARY_BUTTON_STYLE)
        self.add_task_btn.clicked.connect(self._add_task)
        self.add_task_btn.setEnabled(False)
        btn_layout.addWidget(self.add_task_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        tips_text = (
            "提示:\n"
            "1. 先点击“检索录像”，确认所选通道命中的录像段数和总大小。\n"
            "2. 只有检索成功且保存目录剩余空间充足时，才允许开始下载。\n"
            "3. 下载时会按设备中命中的所有录像文件逐段导出。\n"
        )
        if self.ffmpeg_available:
            tips_text += "4. 转换开启时会逐段转为 MP4，保留原画质。"
        else:
            tips_text += "4. FFmpeg 未安装，当前仅导出 DAV 文件。"
        tips = QLabel(tips_text)
        tips.setStyleSheet(f"color: {text_color('disabled')}; font-size: 11px;")
        tips.setWordWrap(True)
        layout.addWidget(tips)

        self.save_dir_input.textChanged.connect(self._update_disk_space)
        self.start_time.dateTimeChanged.connect(self._on_time_range_changed)
        self.end_time.dateTimeChanged.connect(self._on_time_range_changed)
        self.channel_list.itemSelectionChanged.connect(self._on_channel_selection_changed)

        layout.addStretch()

    def set_device_info(self, device_info: dict):
        self._device_info = device_info
        self._clear_channel_cache()
        self._invalidate_retrieval()
        self._update_channel_list()

    def set_device(self, device: Device):
        self._device = device

    def light_init(self, device: Device, device_info: dict):
        """轻量初始化：仅保存设备引用并更新显示信息"""
        try:
            self._device = device
            self.set_device_info(device_info or {})
        except Exception:
            self.log_message.emit("[错误] DownloadTabV2 轻量初始化失败")

    def full_init(self, device: Device, device_info: dict):
        """完整初始化：确保设备引用和设备信息均同步"""
        try:
            self._device = device
            self.set_device_info(device_info or {})
        except Exception:
            self.log_message.emit("[错误] DownloadTabV2 全部初始化失败")

    def _get_device_password(self) -> str:
        """从加密配置中读取当前设备密码，避免在 device_info 中明文传播。"""
        try:
            encrypted = get_config().get("device.password")
            if encrypted:
                return decrypt_password(encrypted)
        except Exception:
            logger.exception("解密设备密码失败")
        return ""

    def _clear_channel_cache(self):
        self._channel_file_cache.clear()

    def _invalidate_retrieval(self):
        self._last_retrieval_result = {}
        self._storage_ready = False
        if hasattr(self, "add_task_btn"):
            self.add_task_btn.setEnabled(False)
        if hasattr(self, "storage_hint_label"):
            self.storage_hint_label.setText("请先检索录像")
            self.storage_hint_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 10pt; padding: 0 8px;")

    def _cache_key(self, channel_id: int, start_dt, end_dt) -> Tuple[int, str, str]:
        return (channel_id, start_dt.isoformat(), end_dt.isoformat())

    def _get_cached_files(self, channel_id: int, start_dt, end_dt):
        return self._channel_file_cache.get(self._cache_key(channel_id, start_dt, end_dt))

    def _set_cached_files(self, channel_id: int, start_dt, end_dt, files: List[dict]):
        self._channel_file_cache[self._cache_key(channel_id, start_dt, end_dt)] = list(files)

    def _update_channel_list(self):
        self.channel_list.clear()
        if not self._device_info:
            return

        channels = self._device_info.get("channels", [])
        for channel in channels:
            display_id = channel.get("display_id", channel["id"])
            item = QListWidgetItem(self._format_channel_text(display_id, channel["name"]))
            item.setData(self.CHANNEL_ID_ROLE, channel["id"])
            item.setData(Qt.ItemDataRole.UserRole + 10, display_id)
            item.setData(self.CHANNEL_NAME_ROLE, channel["name"])
            item.setData(self.CHANNEL_STATS_ROLE, None)
            self.channel_list.addItem(item)

        self._apply_cached_channel_stats()

    def _format_channel_text(self, channel_id: int, channel_name: str, stats: dict = None) -> str:
        base = f"通道{channel_id} {channel_name}"
        if not stats:
            return base
        return (
            f"{base}  |  已选择 {stats['count']} 个录像  |  "
            f"{stats['size_mb']:.1f} MB"
        )

    def _browse_save_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择保存目录",
            self.save_dir_input.text() or os.path.expanduser("~"),
        )
        if dir_path:
            self.save_dir_input.setText(dir_path)
            self._invalidate_retrieval()

    def _on_time_range_changed(self):
        self._clear_channel_cache()
        self._invalidate_retrieval()
        self._update_channel_list()
        self._update_disk_space()

    def _on_channel_selection_changed(self):
        self._invalidate_retrieval()
        self._update_disk_space()

    def _apply_cached_channel_stats(self):
        start_dt = self.start_time.dateTime().toPyDateTime()
        end_dt = self.end_time.dateTime().toPyDateTime()
        for row in range(self.channel_list.count()):
            item = self.channel_list.item(row)
            channel_id = item.data(self.CHANNEL_ID_ROLE)
            files = self._get_cached_files(channel_id, start_dt, end_dt)
            if files is None:
                continue
            self._apply_files_to_item(item, files)

    def _apply_files_to_item(self, item: QListWidgetItem, files: List[dict]):
        stats = {
            "count": len(files),
            "size_mb": sum(int(file_info.get("size", 0) or 0) for file_info in files) / (1024 * 1024),
        }
        item.setData(self.CHANNEL_STATS_ROLE, stats)
        item.setText(
            self._format_channel_text(
                item.data(Qt.ItemDataRole.UserRole + 10) or item.data(self.CHANNEL_ID_ROLE),
                item.data(self.CHANNEL_NAME_ROLE),
                stats,
            )
        )

    def _update_disk_space(self):
        import shutil

        save_dir = self.save_dir_input.text().strip()
        if not save_dir or not os.path.exists(save_dir):
            self.disk_space_label.setText("")
            self._storage_ready = False
            self.add_task_btn.setEnabled(False)
            if hasattr(self, "storage_hint_label"):
                self.storage_hint_label.setText("请先选择保存目录")
                self.storage_hint_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 10pt; padding: 0 8px;")
            return

        try:
            usage = shutil.disk_usage(save_dir)
            free_gb = usage.free / (1024 ** 3)
            start_dt = self.start_time.dateTime().toPyDateTime()
            end_dt = self.end_time.dateTime().toPyDateTime()
            selected_items = self.channel_list.selectedItems()
            cached_sizes = []
            for item in selected_items:
                channel_id = item.data(self.CHANNEL_ID_ROLE)
                files = self._get_cached_files(channel_id, start_dt, end_dt)
                if files is not None:
                    cached_sizes.append(sum(int(file_info.get("size", 0) or 0) for file_info in files))

            if cached_sizes:
                estimated_gb = sum(cached_sizes) / (1024 ** 3)
            else:
                hours = max((end_dt - start_dt).total_seconds() / 3600, 0)
                estimated_gb = hours * max(len(selected_items), 1) * 2.0

            has_retrieval = bool(self._last_retrieval_result)
            self._storage_ready = free_gb >= estimated_gb and has_retrieval

            self.disk_space_label.setText(f"当前目录可用空间: {free_gb:.1f} GB")
            self.disk_space_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 8pt; padding-left: 4px;")

            if has_retrieval:
                remaining_gb = free_gb - estimated_gb
                self.storage_hint_label.setText(
                    f"所需空间: {estimated_gb:.1f} GB   预计剩余: {remaining_gb:.1f} GB"
                )
                if free_gb < estimated_gb:
                    self.storage_hint_label.setStyleSheet(f"color: {text_color('error')}; font-size: 10pt; padding: 0 8px;")
                else:
                    self.storage_hint_label.setStyleSheet(f"color: {text_color('success')}; font-size: 10pt; padding: 0 8px;")
            else:
                self.storage_hint_label.setText("请先检索录像")
                self.storage_hint_label.setStyleSheet(f"color: {text_color('secondary')}; font-size: 10pt; padding: 0 8px;")
            self.add_task_btn.setEnabled(self._storage_ready)
        except Exception:
            self.disk_space_label.setText("")
            self._storage_ready = False
            self.add_task_btn.setEnabled(False)
            if hasattr(self, "storage_hint_label"):
                self.storage_hint_label.setText("空间信息获取失败")
                self.storage_hint_label.setStyleSheet(f"color: {text_color('error')}; font-size: 10pt; padding: 0 8px;")

    def _get_search_device(self):
        if self._device and self._device.is_connected:
            return self._device, False

        password = self._get_device_password()
        if not password:
            raise RuntimeError("未能从配置中读取设备密码，请重新连接设备")

        http_port = self._device_info.get("http_port", 80)
        search_device = Device(
            ip=self._device_info["ip"],
            port=self._device_info["port"],
            http_port=http_port,
            username=self._device_info["username"],
            password=password,
        )
        search_device.login()
        return search_device, True

    def _query_channel_files(self, search_device: Device, channel_id: int, start_dt, end_dt):
        cached = self._get_cached_files(channel_id, start_dt, end_dt)
        if cached is not None:
            return cached
        files = search_device.find_files(channel_id, start_dt, end_dt)
        self._set_cached_files(channel_id, start_dt, end_dt, files)
        return files

    def _retrieve_recordings(self):
        if not self._device_info:
            QMessageBox.warning(self, "提示", "请先连接设备")
            return

        selected_items = self.channel_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请至少选择一个通道")
            return

        save_dir = self.save_dir_input.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "提示", "请选择保存目录")
            return

        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except Exception as exc:
                QMessageBox.critical(self, "错误", f"创建目录失败: {exc}")
                return

        start_dt = self.start_time.dateTime().toPyDateTime()
        end_dt = self.end_time.dateTime().toPyDateTime()
        if end_dt <= start_dt:
            QMessageBox.warning(self, "提示", "结束时间必须大于开始时间")
            return

        search_device = None
        owns_device = False
        cursor_set = False

        try:
            search_device, owns_device = self._get_search_device()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            cursor_set = True
            self.add_task_btn.setEnabled(False)
            self.retrieve_btn.setEnabled(False)
            self.retrieve_btn.setText("检索中...")

            available_channels = []
            empty_channels = []
            error_channels = []

            for item in selected_items:
                QApplication.processEvents()
                channel_id = item.data(self.CHANNEL_ID_ROLE)
                channel_label = f"CH{channel_id:02d} - {item.data(self.CHANNEL_NAME_ROLE)}"
                try:
                    files = self._query_channel_files(search_device, channel_id, start_dt, end_dt)
                    self._apply_files_to_item(item, files)
                    if files:
                        available_channels.append(
                            {
                                "channel_id": channel_id,
                                "channel_label": channel_label,
                                "files": files,
                            }
                        )
                    else:
                        empty_channels.append(channel_label)
                except Exception as exc:
                    error_channels.append(f"{channel_label}: {exc}")

            self._last_retrieval_result = {
                "available_channels": available_channels,
                "empty_channels": empty_channels,
                "error_channels": error_channels,
                "start_dt": start_dt,
                "end_dt": end_dt,
            }
            self._update_disk_space()

            if not available_channels:
                message_parts = ["所选通道在当前时间范围内没有可下载的录像文件。"]
                if empty_channels:
                    message_parts.append("以下通道没有录像，已跳过：\n" + "\n".join(empty_channels))
                if error_channels:
                    message_parts.append("以下通道检索失败：\n" + "\n".join(error_channels))
                QMessageBox.information(self, "无可下载录像", "\n\n".join(message_parts))
                return

            total_segments = sum(len(channel["files"]) for channel in available_channels)
            total_bytes = sum(
                sum(int(file_info.get("size", 0) or 0) for file_info in channel["files"])
                for channel in available_channels
            )
            message_parts = [
                f"检索完成：命中 {len(available_channels)} 个通道，共 {total_segments} 段录像。",
                f"预计下载大小约 {total_bytes / (1024 * 1024):.1f} MB。",
            ]
            if empty_channels:
                message_parts.append("以下通道没有录像：\n" + "\n".join(empty_channels))
            if error_channels:
                message_parts.append("以下通道检索失败：\n" + "\n".join(error_channels))
            if self._storage_ready:
                message_parts.append("当前保存目录剩余空间充足，可以开始下载。")
            else:
                message_parts.append("当前保存目录剩余空间不足，暂时不能开始下载。")

            QMessageBox.information(self, "检索完成", "\n\n".join(message_parts))
            self.log_message.emit(f"[信息] 录像检索完成: 命中 {len(available_channels)} 个通道，共 {total_segments} 段")
        except Exception as exc:
            self._invalidate_retrieval()
            QMessageBox.critical(self, "错误", f"检索录像失败: {exc}")
            self.log_message.emit(f"[错误] 检索录像失败: {exc}")
        finally:
            if owns_device and search_device:
                try:
                    search_device.logout()
                except Exception:
                    pass
            if cursor_set:
                QApplication.restoreOverrideCursor()
            self.retrieve_btn.setEnabled(True)
            self.retrieve_btn.setText("检索录像")
            self._update_disk_space()

    def _add_task(self):
        if not self._device_info:
            QMessageBox.warning(self, "提示", "请先连接设备")
            return

        if not self._last_retrieval_result:
            QMessageBox.warning(self, "提示", "请先点击“检索录像”并确认录像段数")
            return

        if not self._storage_ready:
            QMessageBox.warning(self, "提示", "当前保存目录可用空间不足，请调整目录后重新检索录像")
            return

        save_dir = self.save_dir_input.text().strip()
        convert_to_mp4 = self.convert_checkbox.isChecked()
        available_channels = self._last_retrieval_result.get("available_channels", [])
        empty_channels = self._last_retrieval_result.get("empty_channels", [])
        error_channels = self._last_retrieval_result.get("error_channels", [])
        start_dt = self._last_retrieval_result.get("start_dt")
        end_dt = self._last_retrieval_result.get("end_dt")

        if not available_channels or not start_dt or not end_dt:
            QMessageBox.warning(self, "提示", "请重新检索录像后再下载")
            return

        password = self._get_device_password()
        if not password:
            QMessageBox.warning(self, "提示", "未能从配置中读取设备密码，请重新连接设备")
            return

        task_count = 0
        total_segments = 0
        total_bytes = 0

        for channel_info in available_channels:
            files = channel_info["files"]
            task = DownloadTask(
                device_ip=self._device_info["ip"],
                device_port=self._device_info["port"],
                device_username=self._device_info["username"],
                device_password=password,
                channel=channel_info["channel_id"],
                start_time=start_dt,
                end_time=end_dt,
                save_dir=save_dir,
                convert_to_mp4=convert_to_mp4,
                split_size_gb=0,
            )
            task.generate_temp_path(str(get_temp_dir()))
            task.set_matched_files(files)
            self._download_manager.add_task(None, task)
            task_count += 1
            total_segments += task.matched_file_count
            total_bytes += task.total_bytes

        message_parts = [
            f"已创建 {task_count} 个下载任务。",
            f"共命中 {total_segments} 段录像，约 {total_bytes / (1024 * 1024):.1f} MB。",
        ]
        if empty_channels:
            message_parts.append("以下通道在所选时间范围内没有录像，已跳过：\n" + "\n".join(empty_channels))
        if error_channels:
            message_parts.append("以下通道查询失败，未创建任务：\n" + "\n".join(error_channels))

        QMessageBox.information(self, "成功", "\n\n".join(message_parts))
        self._update_disk_space()
        self.log_message.emit(f"[信息] 已创建 {task_count} 个下载任务")
