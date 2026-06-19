# -*- coding: utf-8 -*-
"""
常量模块测试
"""

from src.core.constants import (
    DEFAULT_SDK_PORT,
    DEFAULT_HTTP_PORT,
    DEVICE_TYPE_MAP,
    CAMERA_VENDOR_KEYWORDS,
    CAMERA_FEATURE_PORTS,
    DSCP_NAMES,
)
from src.gui.constants import Color, FontSize, LAYOUT_INDEX_COMBO_MAP, LOG_LEVEL_MAP, TabLabel


class TestCoreConstants:
    def test_default_ports(self):
        assert DEFAULT_SDK_PORT == 8000
        assert DEFAULT_HTTP_PORT == 80

    def test_device_type_map(self):
        assert DEVICE_TYPE_MAP[1] == "DVR"
        assert DEVICE_TYPE_MAP[3] == "IPC"
        assert DEVICE_TYPE_MAP[4] == "NVR"

    def test_camera_vendors(self):
        assert "hikvision" in CAMERA_VENDOR_KEYWORDS
        assert "海康" in CAMERA_VENDOR_KEYWORDS

    def test_camera_feature_ports(self):
        assert 554 in CAMERA_FEATURE_PORTS
        assert 8000 in CAMERA_FEATURE_PORTS

    def test_dscp_names(self):
        assert DSCP_NAMES[46] == "EF (加速转发)"
        assert DSCP_NAMES[0] == "CS0 / BE (默认)"


class TestGuiConstants:
    def test_color_values(self):
        assert Color.PRIMARY == "#2196F3"
        assert Color.SUCCESS == "#107c10"
        assert Color.ERROR == "#c42b1c"

    def test_layout_mapping(self):
        assert LAYOUT_INDEX_COMBO_MAP[3] == 4
        assert LAYOUT_INDEX_COMBO_MAP[4] == 8

    def test_log_level_map(self):
        assert LOG_LEVEL_MAP["错误"] == "ERROR"
        assert LOG_LEVEL_MAP["信息"] == "INFO"

    def test_tab_labels_no_emoji(self):
        for label in [
            TabLabel.DEVICE_SCAN,
            TabLabel.CONNECTION,
            TabLabel.PREVIEW,
            TabLabel.DOWNLOAD,
        ]:
            assert isinstance(label, str)
            assert len(label) > 0
            # 确保标签不含常见 Emoji 范围字符（简单检查）
            assert not any(0x1F300 <= ord(ch) <= 0x1F9FF for ch in label)
