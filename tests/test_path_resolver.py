# -*- coding: utf-8 -*-
"""
路径解析模块测试
"""

from pathlib import Path

import pytest

from src.core import path_resolver


class TestPathResolver:
    def test_get_data_dir_creates_directory(self, tmp_path, monkeypatch):
        """测试数据目录可创建并写入。"""
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        # 重新导入以应用新的环境变量
        import importlib

        importlib.reload(path_resolver)
        data_dir = path_resolver.get_data_dir()
        assert data_dir.exists()
        assert data_dir.name == "EcoMonitor"

    def test_get_config_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        import importlib

        importlib.reload(path_resolver)
        config_path = path_resolver.get_config_path()
        assert config_path.name == "config.json"
        assert config_path.parent.name == "EcoMonitor"

    def test_get_temp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        import importlib

        importlib.reload(path_resolver)
        temp_dir = path_resolver.get_temp_dir()
        assert temp_dir.exists()
        assert temp_dir.name == "temp"

    def test_get_log_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        import importlib

        importlib.reload(path_resolver)
        log_dir = path_resolver.get_log_dir()
        assert log_dir.exists()
        assert log_dir.name == "logs"

    def test_check_sdk_exists_without_sdk(self, tmp_path, monkeypatch):
        """当 SDK 不存在时应返回失败。"""
        fake_sdk_path = tmp_path / "sdk" / "win64"
        monkeypatch.setattr(path_resolver, "get_sdk_path", lambda: fake_sdk_path)
        exists, msg = path_resolver.check_sdk_exists()
        assert exists is False
        assert "HCNetSDK.dll" in msg
