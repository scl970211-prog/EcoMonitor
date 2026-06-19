# -*- coding: utf-8 -*-
"""
下载任务模型测试
"""

from datetime import datetime

from src.core.download_task import DownloadTask


class TestDownloadTask:
    def test_default_task_id(self):
        task = DownloadTask()
        assert len(task.task_id) == 12

    def test_set_matched_files(self):
        task = DownloadTask()
        files = [
            {
                "filename": "test.dav",
                "start": datetime(2024, 1, 1, 0, 0, 0),
                "end": datetime(2024, 1, 1, 1, 0, 0),
                "size": 1024 * 1024,
            }
        ]
        task.set_matched_files(files)
        assert task.matched_file_count == 1
        assert task.total_bytes == 1024 * 1024

    def test_to_dict_roundtrip(self):
        task = DownloadTask()
        task.set_matched_files(
            [
                {
                    "filename": "test.dav",
                    "start": datetime(2024, 1, 1, 0, 0, 0),
                    "end": datetime(2024, 1, 1, 1, 0, 0),
                    "size": 1024 * 1024,
                }
            ]
        )
        task.save_dir = "/tmp/output"
        data = task.to_dict()
        restored = DownloadTask.from_dict(data)
        assert restored.task_id == task.task_id
        assert restored.total_bytes == task.total_bytes
        assert restored.matched_file_count == task.matched_file_count
        assert restored.save_dir == task.save_dir

    def test_sanitize_filename(self):
        assert DownloadTask.sanitize_filename("a<b>c:d|e*f?g") == "a_b_c_d_e_f_g"
        assert DownloadTask.sanitize_filename("") == "recording"
