# -*- coding: utf-8 -*-
"""
测试共享 fixture

为所有测试提供一个进程唯一的 QApplication，避免 PyQt6 相关模块在测试时
因缺少 QApplication 而报错。
"""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """提供全局唯一的 QApplication 实例。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_singletons():
    """每个测试结束后清理单例状态，避免测试间互相污染。"""
    yield
    # 延迟导入，避免在 QApplication 创建前触发 Qt 对象初始化
    from src.core.event_bus import get_event_bus
    from src.core.app_state import get_app_state

    get_event_bus().clear_subscribers()
    get_app_state().reset()
