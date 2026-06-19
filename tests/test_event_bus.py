# -*- coding: utf-8 -*-
"""
事件总线单元测试
"""

import pytest
from src.core.event_bus import EventBus, EventType


@pytest.fixture
def fresh_event_bus():
    """提供一个已清理订阅者的 EventBus 单例。"""
    bus = EventBus()
    bus.clear_subscribers()
    return bus


class TestEventBus:
    """EventBus 核心行为测试。"""

    def test_subscribe_and_publish(self, fresh_event_bus):
        """订阅后发布事件，处理函数应被调用。"""
        received = []

        def handler(event):
            received.append(event.data)

        handler_id = fresh_event_bus.subscribe(EventType.DEVICE_CONNECTED, handler)
        fresh_event_bus.emit(EventType.DEVICE_CONNECTED, {"ip": "192.168.1.10"})

        assert len(received) == 1
        assert received[0]["ip"] == "192.168.1.10"
        assert handler_id and isinstance(handler_id, str)

    def test_unsubscribe(self, fresh_event_bus):
        """取消订阅后，处理函数不应再被调用。"""
        received = []

        def handler(event):
            received.append(event.data)

        handler_id = fresh_event_bus.subscribe(EventType.DEVICE_ERROR, handler)
        fresh_event_bus.emit(EventType.DEVICE_ERROR, "error1")
        assert len(received) == 1

        assert fresh_event_bus.unsubscribe(handler_id) is True
        fresh_event_bus.emit(EventType.DEVICE_ERROR, "error2")
        assert len(received) == 1

    def test_unsubscribe_invalid_id(self, fresh_event_bus):
        """取消不存在的订阅 ID 应返回 False。"""
        assert fresh_event_bus.unsubscribe("not_exists") is False

    def test_subscribe_once(self, fresh_event_bus):
        """一次性订阅在处理一次后应自动移除。"""
        received = []

        def handler(event):
            received.append(event.data)

        fresh_event_bus.subscribe_once(EventType.SCANNER_COMPLETED, handler)
        fresh_event_bus.emit(EventType.SCANNER_COMPLETED, "first")
        fresh_event_bus.emit(EventType.SCANNER_COMPLETED, "second")

        assert len(received) == 1
        assert received[0] == "first"

    def test_priority_order(self, fresh_event_bus):
        """高优先级处理函数应先被调用。"""
        order = []

        def low_priority(event):
            order.append("low")

        def high_priority(event):
            order.append("high")

        fresh_event_bus.subscribe(EventType.DEVICE_CONNECTED, low_priority, priority=0)
        fresh_event_bus.subscribe(EventType.DEVICE_CONNECTED, high_priority, priority=10)
        fresh_event_bus.emit(EventType.DEVICE_CONNECTED, None)

        assert order == ["high", "low"]

    def test_get_subscriber_count(self, fresh_event_bus):
        """订阅者计数应随订阅/取消订阅变化。"""
        def handler(event):
            pass

        assert fresh_event_bus.get_subscriber_count(EventType.DEVICE_CONNECTED) == 0

        h1 = fresh_event_bus.subscribe(EventType.DEVICE_CONNECTED, handler)
        h2 = fresh_event_bus.subscribe(EventType.DEVICE_CONNECTED, handler)
        assert fresh_event_bus.get_subscriber_count(EventType.DEVICE_CONNECTED) == 2

        fresh_event_bus.unsubscribe(h1)
        assert fresh_event_bus.get_subscriber_count(EventType.DEVICE_CONNECTED) == 1

        fresh_event_bus.unsubscribe(h2)
        assert fresh_event_bus.get_subscriber_count(EventType.DEVICE_CONNECTED) == 0

    def test_has_subscribers(self, fresh_event_bus):
        """has_subscribers 应正确反映是否存在订阅者。"""
        def handler(event):
            pass

        assert fresh_event_bus.has_subscribers(EventType.UI_NOTIFICATION) is False
        fresh_event_bus.subscribe(EventType.UI_NOTIFICATION, handler)
        assert fresh_event_bus.has_subscribers(EventType.UI_NOTIFICATION) is True

    def test_decorator_subscribe(self, fresh_event_bus):
        """装饰器方式订阅应正常工作。"""
        received = []

        @fresh_event_bus.on(EventType.PREVIEW_STARTED)
        def handler(event):
            received.append(event.data)

        fresh_event_bus.emit(EventType.PREVIEW_STARTED, 1)
        assert received == [1]
