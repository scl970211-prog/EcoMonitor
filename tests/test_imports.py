"""
基础导入测试 - 验证核心模块可正常导入
"""

import sys
import os

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_src_package_import():
    """测试 src 包基础元数据"""
    from src import __version__, __author__, __organization__
    assert isinstance(__version__, str)
    assert len(__version__.split(".")) >= 2


def test_core_imports():
    """测试核心模块导入"""
    from src.core import Device, SDKLoader
    from src.core.database import Database
    from src.core.download_task import DownloadTask
    from src.core.event_bus import EventBus
    from src.core.constants import DEFAULT_SDK_PORT, DEVICE_TYPE_MAP


def test_utils_imports():
    """测试工具模块导入"""
    from src.utils.config import get_config
    from src.utils.crypto import CryptoManager
    from src.utils.logger import setup_logger


def test_gui_imports():
    """测试 GUI 模块导入（不创建 QApplication）"""
    # 仅导入不依赖 Qt 运行时实例的模块
    from src.gui.main_window import MainWindow
    from src.gui.tabs.connection_tab import ConnectionTab
    from src.gui.constants import Color, TabLabel


def test_constants_imports():
    """测试常量模块导入"""
    from src.core.constants import DEFAULT_SDK_PORT
    from src.gui.constants import Color, TabLabel
    assert Color.PRIMARY == "#2196F3"
    assert TabLabel.DEVICE_SCAN == "设备搜索"
