# -*- coding: utf-8 -*-
"""
配置管理模块测试
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.utils import config as config_module


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """提供隔离的配置实例并在测试后清理单例。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import importlib

    importlib.reload(config_module)
    config_module.Config._instance = None
    config_module.Config._initialized = False
    yield config_module.get_config()
    config_module.Config._instance = None
    config_module.Config._initialized = False


class TestConfig:
    def test_default_values(self, isolated_config):
        assert isolated_config.get("device.port") == 8000
        assert isolated_config.get("device.http_port") == 80
        assert isolated_config.get("download.concurrent") == 2

    def test_set_and_get(self, isolated_config):
        isolated_config.set("device.ip", "192.168.1.100")
        assert isolated_config.get("device.ip") == "192.168.1.100"

    def test_password_encrypted(self, isolated_config):
        isolated_config.set("device.password", "secret")
        raw = isolated_config._config["device"]["password"]
        assert raw != "secret"
        assert isolated_config.get("device.password") == "secret"

    def test_merge_defaults(self, isolated_config):
        """旧配置缺少新字段时应自动合并默认值。"""
        config_path = isolated_config._config_path
        # 写入一个不完整的配置
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"device": {"ip": "1.2.3.4"}}, f)
        # 重新加载
        isolated_config._config = isolated_config._load()
        assert isolated_config.get("device.ip") == "1.2.3.4"
        assert isolated_config.get("device.port") == 8000

    def test_save_device_settings(self, isolated_config):
        isolated_config.save_device_settings("192.168.1.64", 8000, "admin", "pwd", 80)
        assert isolated_config.get("device.ip") == "192.168.1.64"
        assert isolated_config.get("device.username") == "admin"
        assert isolated_config.get("device.password") == "pwd"
