"""
下载任务定义。
"""

import json
import os
import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class DownloadTask:
    """
    下载任务数据类。
    对应数据库中的一条记录。
    """

    STATUS_PENDING = "pending"
    STATUS_DOWNLOADING = "downloading"
    STATUS_DOWNLOADED = "downloaded"
    STATUS_CONVERTING = "converting"
    STATUS_RECONNECTING = "reconnecting"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_PAUSED = "paused"
    STATUS_CANCELLED = "cancelled"

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: Optional[str] = None

    device_ip: str = ""
    device_port: int = 8000
    device_username: str = ""
    device_password: str = ""
    channel: int = 1

    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)

    save_dir: str = ""
    temp_dav_path: Optional[str] = None
    output_files: List[str] = field(default_factory=list)

    convert_to_mp4: bool = True
    split_size_gb: float = 0.0

    status: str = STATUS_PENDING
    progress: int = 0
    phase: str = ""

    downloaded_bytes: int = 0
    total_bytes: int = 0
    retry_count: int = 0

    matched_files: List[dict] = field(default_factory=list)
    matched_file_count: int = 0
    current_file_index: int = -1
    current_file_name: str = ""
    completed_segments: int = 0
    failed_segment_index: int = -1
    last_error_stage: str = ""

    error_msg: str = ""

    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        self.start_time = self._parse_datetime(self.start_time)
        self.end_time = self._parse_datetime(self.end_time)
        self.created_at = self._parse_datetime(self.created_at)
        self.started_at = self._parse_datetime(self.started_at)
        self.completed_at = self._parse_datetime(self.completed_at)
        self.output_files = self._parse_output_files(self.output_files)
        self.matched_files = self._normalize_matched_files(self.matched_files)
        if not self.matched_file_count:
            self.matched_file_count = len(self.matched_files)
        if not self.total_bytes and self.matched_files:
            self.total_bytes = sum(int(file_info.get("size", 0) or 0) for file_info in self.matched_files)

    @staticmethod
    def _parse_datetime(value):
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    @staticmethod
    def _parse_output_files(value) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if item]
            except json.JSONDecodeError:
                pass
            return [item for item in value.split(",") if item]
        return []

    @classmethod
    def _normalize_matched_files(cls, value) -> List[dict]:
        if not value:
            return []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []

        normalized = []
        for item in value:
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            start = normalized_item.get("start")
            end = normalized_item.get("end")
            if isinstance(start, str):
                normalized_item["start"] = datetime.fromisoformat(start)
            if isinstance(end, str):
                normalized_item["end"] = datetime.fromisoformat(end)
            normalized.append(normalized_item)
        return normalized

    @staticmethod
    def _serialize_matched_files(value: List[dict]) -> str:
        serializable = []
        for item in value:
            serialized = dict(item)
            start = serialized.get("start")
            end = serialized.get("end")
            if isinstance(start, datetime):
                serialized["start"] = start.isoformat()
            if isinstance(end, datetime):
                serialized["end"] = end.isoformat()
            serializable.append(serialized)
        return json.dumps(serializable, ensure_ascii=False)

    @property
    def duration_hours(self) -> float:
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600

    @property
    def base_filename(self) -> str:
        unique_id = self.task_id[:8]
        return (
            f"ch{self.channel:02d}_"
            f"{self.start_time.strftime('%Y%m%d_%H%M%S')}_"
            f"{self.end_time.strftime('%Y%m%d_%H%M%S')}_"
            f"{unique_id}"
        )

    def generate_temp_path(self, temp_dir: str) -> str:
        self.temp_dav_path = os.path.join(temp_dir, f"{self.task_id}.dav")
        return self.temp_dav_path

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename or "").strip()
        sanitized = sanitized.rstrip(". ")
        return sanitized or "recording"

    def get_segment_base_filename(self, segment_index: int) -> str:
        """
        生成段文件名，格式：ch{通道号}_{开始时间}_{结束时间}
        示例：ch01_20250327_120000_20250327_123000
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if 0 <= segment_index < len(self.matched_files):
            file_info = self.matched_files[segment_index]
            start_time = file_info.get("start")
            end_time = file_info.get("end")
            
            if start_time and end_time:
                # 格式化时间：YYYYMMDD_HHMMSS
                start_str = start_time.strftime("%Y%m%d_%H%M%S")
                end_str = end_time.strftime("%Y%m%d_%H%M%S")
                
                # 格式：ch{通道号}_{开始时间}_{结束时间}
                filename = f"ch{self.channel:02d}_{start_str}_{end_str}"
                logger.debug(
                    f"[get_segment_base_filename] index={segment_index}, "
                    f"using format 'ch{{channel}}_{{start}}_{{end}}': '{filename}'"
                )
                return filename
            else:
                logger.warning(
                    f"[get_segment_base_filename] Missing start/end time for index={segment_index}, "
                    f"file_info={file_info}"
                )
        else:
            logger.warning(
                f"[get_segment_base_filename] Index {segment_index} out of range "
                f"(matched_files len={len(self.matched_files)})"
            )
        
        # 回退：使用任务级别的基本信息
        base_filename = self.base_filename
        if self.matched_file_count > 1:
            fallback = f"{base_filename}_part{segment_index + 1:03d}"
            logger.debug(f"[get_segment_base_filename] Using fallback: '{fallback}'")
            return fallback
        logger.debug(f"[get_segment_base_filename] Using base filename: '{base_filename}'")
        return base_filename

    def set_matched_files(self, files: List[dict]):
        self.matched_files = self._normalize_matched_files(files)
        self.matched_file_count = len(self.matched_files)
        self.total_bytes = sum(int(file_info.get("size", 0) or 0) for file_info in self.matched_files)
        if self.current_file_index >= self.matched_file_count:
            self.current_file_index = -1

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "device_ip": self.device_ip,
            "device_port": self.device_port,
            "device_username": self.device_username,
            "device_password": self.device_password,
            "channel": self.channel,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "save_dir": self.save_dir,
            "temp_dav_path": self.temp_dav_path,
            "output_files": json.dumps(self.output_files, ensure_ascii=False),
            "convert_to_mp4": 1 if self.convert_to_mp4 else 0,
            "split_size_gb": self.split_size_gb,
            "status": self.status,
            "progress": self.progress,
            "phase": self.phase,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "retry_count": self.retry_count,
            "matched_files": self._serialize_matched_files(self.matched_files),
            "matched_file_count": self.matched_file_count,
            "current_file_index": self.current_file_index,
            "current_file_name": self.current_file_name,
            "completed_segments": self.completed_segments,
            "failed_segment_index": self.failed_segment_index,
            "last_error_stage": self.last_error_stage,
            "error_msg": self.error_msg,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadTask":
        return cls(
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id"),
            device_ip=data.get("device_ip", ""),
            device_port=data.get("device_port", 8000),
            device_username=data.get("device_username", ""),
            device_password=data.get("device_password", ""),
            channel=data.get("channel", 1),
            start_time=data.get("start_time", datetime.now()),
            end_time=data.get("end_time", datetime.now()),
            save_dir=data.get("save_dir", ""),
            temp_dav_path=data.get("temp_dav_path"),
            output_files=data.get("output_files", []),
            convert_to_mp4=bool(data.get("convert_to_mp4", 1)),
            split_size_gb=data.get("split_size_gb", 0.0),
            status=data.get("status", cls.STATUS_PENDING),
            progress=data.get("progress", 0),
            phase=data.get("phase", ""),
            downloaded_bytes=data.get("downloaded_bytes", 0),
            total_bytes=data.get("total_bytes", 0),
            retry_count=data.get("retry_count", 0),
            matched_files=data.get("matched_files", []),
            matched_file_count=data.get("matched_file_count", 0),
            current_file_index=data.get("current_file_index", -1),
            current_file_name=data.get("current_file_name", ""),
            completed_segments=data.get("completed_segments", 0),
            failed_segment_index=data.get("failed_segment_index", -1),
            last_error_stage=data.get("last_error_stage", ""),
            error_msg=data.get("error_msg", ""),
            created_at=data.get("created_at", datetime.now()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )
