# -*- coding: utf-8 -*-
"""
设备操作类单元测试（使用 mock SDK）

本测试通过 mock `SDKLoader` 避免加载真实海康 DLL，
验证 Device 的登录、登出、状态流转等核心逻辑。
"""

import pytest
from unittest.mock import MagicMock

from src.core.device import Device, DeviceStatus
from src.core.sdk_loader import NET_DVR_DEVICEINFO_V30


@pytest.fixture
def mock_sdk_loader(monkeypatch):
    """将 src.core.device.SDKLoader 替换为 mock，避免加载真实 DLL。"""
    mock_sdk = MagicMock()
    mock_sdk.NET_DVR_Login_V30.return_value = 1
    mock_sdk.NET_DVR_Logout.return_value = True
    mock_sdk.NET_DVR_GetLastError.return_value = 0

    mock_loader = MagicMock()
    mock_loader.sdk = mock_sdk

    monkeypatch.setattr(
        "src.core.device.SDKLoader",
        MagicMock(return_value=mock_loader),
    )
    return mock_sdk


class TestDeviceLogin:
    """Device 登录/登出测试。"""

    def test_login_success(self, mock_sdk_loader):
        """模拟 SDK 登录成功，设备应进入 ONLINE 状态。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")

        states = []
        device.device_status_changed.connect(
            lambda status, msg: states.append(status)
        )

        result = device.login()

        assert result is True
        assert device.is_connected is True
        assert device.user_id == 1
        assert DeviceStatus.ONLINE in states
        mock_sdk_loader.NET_DVR_Login_V30.assert_called_once()

    def test_login_failure(self, mock_sdk_loader):
        """模拟 SDK 登录失败，设备应进入 ERROR 状态并抛出异常。"""
        mock_sdk_loader.NET_DVR_Login_V30.return_value = -1
        mock_sdk_loader.NET_DVR_GetLastError.return_value = 1

        device = Device("192.168.1.10", 8000, "admin", "wrong")

        errors = []
        device.error_occurred.connect(lambda msg: errors.append(msg))

        with pytest.raises(RuntimeError):
            device.login()

        assert device.is_connected is False
        assert device.user_id == -1
        assert len(errors) == 1
        assert "登录失败" in errors[0]

    def test_logout(self, mock_sdk_loader):
        """登出后设备状态应重置为 OFFLINE。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")
        device.login()
        assert device.is_connected is True

        login_states = []
        device.login_state_changed.connect(lambda connected: login_states.append(connected))

        device.logout()

        assert device.is_connected is False
        assert device.user_id == -1
        assert device.get_device_status()[0] == DeviceStatus.OFFLINE
        assert False in login_states
        mock_sdk_loader.NET_DVR_Logout.assert_called_once_with(1)

    def test_device_info_after_login(self, mock_sdk_loader):
        """登录后应能读取设备信息结构体。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")
        device.login()

        info = device.device_info
        assert info is not None
        assert isinstance(info, NET_DVR_DEVICEINFO_V30)

    def test_login_when_already_connected(self, mock_sdk_loader):
        """已连接状态下再次登录应直接返回 True，不重复调用 SDK。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")
        device.login()
        mock_sdk_loader.NET_DVR_Login_V30.reset_mock()

        result = device.login()

        assert result is True
        mock_sdk_loader.NET_DVR_Login_V30.assert_not_called()


class TestDeviceStatus:
    """Device 状态常量与辅助方法测试。"""

    def test_initial_status(self, mock_sdk_loader):
        """初始状态应为 OFFLINE。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")
        status, error, code = device.get_device_status()
        assert status == DeviceStatus.OFFLINE
        assert error == ""
        assert code == 0

    def test_channel_status_default(self, mock_sdk_loader):
        """未设置通道状态时默认返回 OFFLINE。"""
        device = Device("192.168.1.10", 8000, "admin", "pass123")
        assert device.get_channel_status(1) == "offline"
