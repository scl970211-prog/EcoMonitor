"""
数据库模块，使用 SQLite 持久化下载任务。
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .path_resolver import get_db_path

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库管理。"""

    TASK_COLUMNS = {
        "task_id": "TEXT PRIMARY KEY",
        "session_id": "TEXT",
        "device_ip": "TEXT NOT NULL",
        "device_port": "INTEGER DEFAULT 8000",
        "device_username": "TEXT",
        "device_password": "TEXT",
        "channel": "INTEGER NOT NULL",
        "start_time": "TEXT NOT NULL",
        "end_time": "TEXT NOT NULL",
        "save_dir": "TEXT NOT NULL",
        "temp_dav_path": "TEXT",
        "output_files": "TEXT",
        "convert_to_mp4": "INTEGER DEFAULT 1",
        "split_size_gb": "REAL DEFAULT 0.0",
        "status": "TEXT DEFAULT 'pending'",
        "progress": "INTEGER DEFAULT 0",
        "phase": "TEXT",
        "downloaded_bytes": "INTEGER DEFAULT 0",
        "total_bytes": "INTEGER DEFAULT 0",
        "retry_count": "INTEGER DEFAULT 0",
        "matched_files": "TEXT",
        "matched_file_count": "INTEGER DEFAULT 0",
        "current_file_index": "INTEGER DEFAULT -1",
        "current_file_name": "TEXT",
        "completed_segments": "INTEGER DEFAULT 0",
        "failed_segment_index": "INTEGER DEFAULT -1",
        "last_error_stage": "TEXT",
        "error_msg": "TEXT",
        "created_at": "TEXT NOT NULL",
        "started_at": "TEXT",
        "completed_at": "TEXT",
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(get_db_path())
        self._use_uri = False
        self._memory_anchor: Optional[sqlite3.Connection] = None
        try:
            self._init_db()
        except sqlite3.Error as exc:
            logger.warning("文件数据库初始化失败，回退到内存数据库: %s", exc)
            self.db_path = "file:hikvision_downloader?mode=memory&cache=shared"
            self._use_uri = True
            self._memory_anchor = sqlite3.connect(self.db_path, timeout=30, uri=True)
            self._memory_anchor.row_factory = sqlite3.Row
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not self._use_uri:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30, uri=self._use_uri)
        conn.row_factory = sqlite3.Row
        return conn

    def close(self):
        """显式关闭数据库连接，应在程序退出时调用"""
        if self._memory_anchor is not None:
            try:
                self._memory_anchor.close()
            except Exception:
                pass
            finally:
                self._memory_anchor = None

    def __del__(self):
        """析构函数，作为 close() 的后备"""
        self.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS download_tasks (
                    task_id TEXT PRIMARY KEY
                )
                """
            )
            self._ensure_task_columns(cursor)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS download_sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    device_ip TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    save_dir TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_status
                ON download_tasks(status)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_session
                ON download_tasks(session_id)
                """
            )
            conn.commit()
            logger.info("数据库初始化完成: %s", self.db_path)

    def _ensure_task_columns(self, cursor: sqlite3.Cursor):
        cursor.execute("PRAGMA table_info(download_tasks)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column_name, column_type in self.TASK_COLUMNS.items():
            if column_name in existing_columns:
                continue
            # 使用参数化查询防止 SQL 注入
            # 列名来自内部常量，但仍进行安全检查
            safe_column = ''.join(c for c in column_name if c.isalnum() or c == '_')
            safe_type = ''.join(c for c in column_type if c.isalnum() or c in ' _()')
            if not safe_column or not safe_type:
                continue
            cursor.execute(
                f"ALTER TABLE download_tasks ADD COLUMN {safe_column} {safe_type}"
            )

    def save_task(self, task: Dict) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                columns = list(self.TASK_COLUMNS.keys())
                placeholders = ", ".join("?" for _ in columns)
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO download_tasks ({", ".join(columns)})
                    VALUES ({placeholders})
                    """,
                    tuple(task.get(column) for column in columns),
                )
                conn.commit()
                return True
        except Exception as exc:
            logger.error("保存任务失败: %s", exc)
            return False

    def get_task(self, task_id: str) -> Optional[Dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM download_tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.error("获取任务失败: %s", exc)
            return None

    def get_tasks_by_status(self, status: str) -> List[Dict]:
        return self.get_tasks_by_statuses([status])

    def get_tasks_by_statuses(self, statuses: Iterable[str]) -> List[Dict]:
        status_list = list(statuses)
        if not status_list:
            return []

        placeholders = ",".join("?" for _ in status_list)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT * FROM download_tasks
                    WHERE status IN ({placeholders})
                    ORDER BY created_at DESC
                    """,
                    status_list,
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("获取任务列表失败: %s", exc)
            return []

    def get_recent_tasks(self, limit: int = 10) -> List[Dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM download_tasks
                    WHERE status IN ('completed', 'failed', 'cancelled', 'paused')
                    ORDER BY COALESCE(completed_at, created_at) DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("获取历史任务失败: %s", exc)
            return []

    def update_task_progress(
        self,
        task_id: str,
        progress: int,
        phase: str = None,
        downloaded_bytes: Optional[int] = None,
    ):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                updates = ["progress = ?"]
                values = [progress]
                if phase is not None:
                    updates.append("phase = ?")
                    values.append(phase)
                if downloaded_bytes is not None:
                    updates.append("downloaded_bytes = ?")
                    values.append(downloaded_bytes)
                values.append(task_id)
                cursor.execute(
                    f"""
                    UPDATE download_tasks
                    SET {", ".join(updates)}
                    WHERE task_id = ?
                    """,
                    values,
                )
                conn.commit()
        except Exception as exc:
            logger.error("更新进度失败: %s", exc)

    def delete_task(self, task_id: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM download_tasks WHERE task_id = ?", (task_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("删除任务失败: %s", exc)
            return False

    def delete_tasks_by_statuses(self, statuses: Iterable[str]) -> int:
        status_list = list(statuses)
        if not status_list:
            return 0

        placeholders = ",".join("?" for _ in status_list)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    DELETE FROM download_tasks
                    WHERE status IN ({placeholders})
                    """,
                    status_list,
                )
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            logger.error("批量删除任务失败: %s", exc)
            return 0

    def save_session(self, session: Dict) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO download_sessions (
                        session_id, name, device_ip, start_time, end_time,
                        channels, save_dir, status, created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.get("session_id"),
                        session.get("name"),
                        session.get("device_ip"),
                        session.get("start_time"),
                        session.get("end_time"),
                        json.dumps(session.get("channels", []), ensure_ascii=False),
                        session.get("save_dir"),
                        session.get("status", "running"),
                        session.get("created_at"),
                        session.get("completed_at"),
                    ),
                )
                conn.commit()
                return True
        except Exception as exc:
            logger.error("保存会话失败: %s", exc)
            return False
