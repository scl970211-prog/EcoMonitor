# -*- coding: utf-8 -*-
"""
应用全局状态管理单元测试
"""

import pytest
from src.core.app_state import AppState, DeviceState, PreviewState, DownloadTaskState, DownloadTaskInfo


@pytest.fixture
def fresh_app_state():
    """提供一个已重置的 AppState 单例。"""
    state = AppState()
    state.reset()
    return state


class TestAppState:
    """AppState 核心行为测试。"""

    def test_initial_state(self, fresh_app_state):
        """初始状态应为未连接。"""
        assert fresh_app_state.device is None
        assert fresh_app_state.device_info == {}
        assert fresh_app_state.device_state == DeviceState.DISCONNECTED
        assert fresh_app_state.is_device_connected is False

    def test_set_device(self, fresh_app_state):
        """设置设备后状态应为已连接，并发出信号。"""
        connected = []
        state_changed = []

        fresh_app_state.device_connected.connect(lambda info: connected.append(info))
        fresh_app_state.device_state_changed.connect(lambda state: state_changed.append(state))

        fresh_app_state.set_device(object(), {"ip": "192.168.1.10", "serial": "test123"})

        assert fresh_app_state.is_device_connected is True
        assert fresh_app_state.device_info["ip"] == "192.168.1.10"
        assert len(connected) == 1
        assert connected[0]["serial"] == "test123"
        assert DeviceState.CONNECTED.value in state_changed

    def test_set_device_none(self, fresh_app_state):
        """传入 None 应清空设备状态。"""
        fresh_app_state.set_device(object(), {"ip": "192.168.1.10"})
        assert fresh_app_state.is_device_connected is True

        disconnected = []
        fresh_app_state.device_disconnected.connect(lambda: disconnected.append(True))

        fresh_app_state.set_device(None)

        assert fresh_app_state.device is None
        assert fresh_app_state.is_device_connected is False
        assert len(disconnected) == 1

    def test_set_device_state_error(self, fresh_app_state):
        """设置为错误状态应发出 device_error 信号。"""
        errors = []
        fresh_app_state.device_error.connect(lambda msg: errors.append(msg))

        fresh_app_state.set_device_state(DeviceState.ERROR, "密码错误")

        assert fresh_app_state.device_state == DeviceState.ERROR
        assert len(errors) == 1
        assert errors[0] == "密码错误"

    def test_update_channel_list(self, fresh_app_state):
        """更新通道列表后应能正确查询。"""
        updated = []
        fresh_app_state.channel_list_updated.connect(lambda channels: updated.append(channels))

        fresh_app_state.update_channel_list([
            {"id": 1, "name": "通道1", "online": True},
            {"id": 2, "name": "通道2", "online": False},
        ])

        assert len(fresh_app_state._channels) == 2
        ch1 = fresh_app_state.get_channel_info(1)
        assert ch1 is not None
        assert ch1.name == "通道1"
        assert ch1.is_online is True

        ch2 = fresh_app_state.get_channel_info(2)
        assert ch2.is_online is False

        assert len(updated) == 1
        assert len(updated[0]) == 2

    def test_preview_state(self, fresh_app_state):
        """预览状态应正确维护。"""
        fresh_app_state.update_channel_list([{"id": 1, "name": "通道1"}])

        started = []
        stopped = []
        fresh_app_state.preview_started.connect(lambda cid: started.append(cid))
        fresh_app_state.preview_stopped.connect(lambda cid: stopped.append(cid))

        fresh_app_state.start_preview(1, preview_handle=100)
        assert fresh_app_state.is_previewing(1) is True
        assert fresh_app_state.get_channel_info(1).preview_state == PreviewState.PLAYING
        assert started == [1]

        fresh_app_state.stop_preview(1)
        assert fresh_app_state.is_previewing(1) is False
        assert fresh_app_state.get_channel_info(1).preview_state == PreviewState.IDLE
        assert stopped == [1]

    def test_download_task_management(self, fresh_app_state):
        """下载任务应支持添加、查询、状态更新。"""
        from datetime import datetime

        task = DownloadTaskInfo(
            task_id="task-001",
            channel=1,
            start_time=datetime.now(),
            end_time=datetime.now(),
        )

        added = []
        state_changed = []
        progress_updated = []

        fresh_app_state.download_task_added.connect(lambda tid: added.append(tid))
        fresh_app_state.download_task_state_changed.connect(lambda tid, state: state_changed.append((tid, state)))
        fresh_app_state.download_progress_updated.connect(lambda tid, p, s, e: progress_updated.append((tid, p, s, e)))

        fresh_app_state.add_download_task(task)
        assert fresh_app_state.get_download_task("task-001") is task
        assert added == ["task-001"]

        fresh_app_state.update_download_state("task-001", DownloadTaskState.RUNNING)
        assert task.state == DownloadTaskState.RUNNING
        assert state_changed == [("task-001", DownloadTaskState.RUNNING.value)]

        fresh_app_state.update_download_progress("task-001", 50, 1024, 60)
        assert task.progress == 50
        assert progress_updated == [("task-001", 50, 1024, 60)]

        fresh_app_state.remove_download_task("task-001")
        assert fresh_app_state.get_download_task("task-001") is None

    def test_reset(self, fresh_app_state):
        """reset 应清空所有状态。"""
        fresh_app_state.update_channel_list([{"id": 1}])
        fresh_app_state.start_preview(1)

        from datetime import datetime
        task = DownloadTaskInfo(
            task_id="task-001",
            channel=1,
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        fresh_app_state.add_download_task(task)

        fresh_app_state.reset()

        assert fresh_app_state.device is None
        assert fresh_app_state.device_state == DeviceState.DISCONNECTED
        assert len(fresh_app_state._channels) == 0
        assert len(fresh_app_state._active_previews) == 0
        assert len(fresh_app_state._download_tasks) == 0
