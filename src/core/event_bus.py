# -*- coding: utf-8 -*-
"""
事件总线模块
实现模块间的解耦通信
"""

import logging
import uuid
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """事件定义"""
    type: str                   # 事件类型
    data: Any                   # 事件数据
    source: str = ""            # 事件源
    event_id: str = ""          # 事件ID
    timestamp: datetime = None  # 时间戳
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())[:8]
        if not self.timestamp:
            self.timestamp = datetime.now()


class EventBus(QObject):
    """
    事件总线（单例）
    实现发布-订阅模式，解耦模块间通信
    
    特性：
    - 支持同步和异步事件处理
    - 支持事件过滤
    - 支持一次性订阅
    - 支持优先级
    - 线程安全
    """
    
    # 信号（用于跨线程通信）
    event_posted = pyqtSignal(object)  # Event
    
    _instance = None
    _mutex = QMutex()
    
    def __new__(cls):
        if cls._instance is None:
            cls._mutex.lock()
            try:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
            finally:
                cls._mutex.unlock()
        return cls._instance
    
    def __init__(self):
        super().__init__()
        
        if hasattr(self, '_initialized'):
            return
        
        # 订阅者: {event_type: [(handler_id, handler, priority, once)]}
        self._subscribers: Dict[str, List[tuple]] = {}
        
        # 异步事件队列
        self._event_queue: Queue = Queue()
        
        # 处理线程
        self._worker_thread: Optional[EventBusWorker] = None
        self._running = False
        
        # 处理器ID映射
        self._handler_ids: Dict[str, tuple] = {}
        
        # 连接信号到处理
        self.event_posted.connect(self._process_event)
        
        self._initialized = True
        logger.info("EventBus 初始化完成")
    
    def start(self):
        """启动事件总线"""
        if not self._running:
            self._worker_thread = EventBusWorker(self)
            self._worker_thread.start()
            self._running = True
            logger.info("EventBus 已启动")
    
    def stop(self):
        """停止事件总线"""
        if self._running:
            self._running = False
            if self._worker_thread:
                self._worker_thread.stop()
                self._worker_thread.wait(5000)
            logger.info("EventBus 已停止")
    
    # ========== 订阅功能 ==========
    
    def subscribe(self, event_type: str, handler: Callable,
                  priority: int = 0, once: bool = False) -> str:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 处理函数 fn(event: Event)
            priority: 优先级（数字越大优先级越高）
            once: 是否只处理一次
        
        Returns:
            handler_id: 订阅ID，用于取消订阅
        """
        handler_id = str(uuid.uuid4())[:8]
        
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        # 按优先级插入
        inserted = False
        for i, (_, _, p, _) in enumerate(self._subscribers[event_type]):
            if priority > p:
                self._subscribers[event_type].insert(i, (handler_id, handler, priority, once))
                inserted = True
                break
        
        if not inserted:
            self._subscribers[event_type].append((handler_id, handler, priority, once))
        
        self._handler_ids[handler_id] = (event_type, handler)
        
        logger.debug(f"订阅事件: {event_type}, handler: {handler_id}")
        return handler_id
    
    def unsubscribe(self, handler_id: str) -> bool:
        """
        取消订阅
        
        Args:
            handler_id: 订阅时返回的ID
        
        Returns:
            是否成功取消
        """
        if handler_id not in self._handler_ids:
            return False
        
        event_type, handler = self._handler_ids[handler_id]
        
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                (hid, h, p, o) for hid, h, p, o in self._subscribers[event_type]
                if hid != handler_id
            ]
        
        del self._handler_ids[handler_id]
        logger.debug(f"取消订阅: {handler_id}")
        return True
    
    def subscribe_once(self, event_type: str, handler: Callable,
                       priority: int = 0) -> str:
        """订阅一次性事件"""
        return self.subscribe(event_type, handler, priority, once=True)
    
    # ========== 发布功能 ==========
    
    def publish(self, event_type: str, data: Any = None,
                source: str = "", async_mode: bool = False):
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件源标识
            async_mode: 是否异步处理
        """
        event = Event(
            type=event_type,
            data=data,
            source=source
        )
        
        if async_mode and self._running:
            # 异步模式：放入队列，由工作线程处理
            self._event_queue.put(event)
        else:
            # 同步模式：直接处理
            self._process_event(event)
    
    def post(self, event_type: str, data: Any = None, source: str = ""):
        """发布异步事件（便捷方法）"""
        self.publish(event_type, data, source, async_mode=True)
    
    def emit(self, event_type: str, data: Any = None, source: str = ""):
        """发布同步事件（便捷方法）"""
        self.publish(event_type, data, source, async_mode=False)
    
    # ========== 事件处理 ==========
    
    def _process_event(self, event: Event):
        """处理事件"""
        event_type = event.type
        
        # 获取订阅者
        subscribers = self._subscribers.get(event_type, [])
        
        if not subscribers:
            return
        
        # 调用处理函数
        to_remove = []
        
        for handler_id, handler, priority, once in subscribers:
            try:
                handler(event)
                
                if once:
                    to_remove.append(handler_id)
                    
            except Exception as e:
                logger.error(f"事件处理错误 [{event_type}]: {e}")
        
        # 移除一次性订阅
        for handler_id in to_remove:
            self.unsubscribe(handler_id)
    
    def _process_async_events(self):
        """处理异步事件（在工作线程中调用）"""
        try:
            while self._running:
                try:
                    event = self._event_queue.get(timeout=0.1)
                    self.event_posted.emit(event)
                except Empty:
                    continue
        except Exception as e:
            logger.error(f"异步事件处理异常: {e}")
    
    # ========== 便捷订阅方法 ==========
    
    def on(self, event_type: str, priority: int = 0):
        """
        装饰器方式订阅
        
        用法：
            @event_bus.on('device_connected')
            def handler(event):
                print(event.data)
        """
        def decorator(func: Callable) -> Callable:
            self.subscribe(event_type, func, priority)
            return func
        return decorator
    
    def once(self, event_type: str, priority: int = 0):
        """装饰器方式一次性订阅"""
        def decorator(func: Callable) -> Callable:
            self.subscribe_once(event_type, func, priority)
            return func
        return decorator
    
    # ========== 工具方法 ==========
    
    def clear_subscribers(self, event_type: str = None):
        """清除订阅者"""
        if event_type:
            if event_type in self._subscribers:
                del self._subscribers[event_type]
        else:
            self._subscribers.clear()
        
        self._handler_ids.clear()
        logger.info("已清除所有订阅者")
    
    def get_subscriber_count(self, event_type: str = None) -> int:
        """获取订阅者数量"""
        if event_type:
            return len(self._subscribers.get(event_type, []))
        return sum(len(s) for s in self._subscribers.values())
    
    def has_subscribers(self, event_type: str) -> bool:
        """检查是否有订阅者"""
        return event_type in self._subscribers and len(self._subscribers[event_type]) > 0


class EventBusWorker(QThread):
    """事件总线工作线程"""
    
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self._event_bus = event_bus
        self._running = False
    
    def run(self):
        """运行"""
        self._running = True
        self._event_bus._process_async_events()
    
    def stop(self):
        """停止"""
        self._running = False


# ========== 预定义事件类型 ==========

class EventType:
    """预定义事件类型"""
    
    # 设备事件
    DEVICE_CONNECTING = "device.connecting"
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    DEVICE_ERROR = "device.error"
    DEVICE_RECONNECTING = "device.reconnecting"
    
    # 通道事件
    CHANNEL_LIST_UPDATED = "channel.list_updated"
    CHANNEL_SELECTED = "channel.selected"
    CHANNEL_STATE_CHANGED = "channel.state_changed"
    
    # 预览事件
    PREVIEW_STARTING = "preview.starting"
    PREVIEW_STARTED = "preview.started"
    PREVIEW_STOPPING = "preview.stopping"
    PREVIEW_STOPPED = "preview.stopped"
    PREVIEW_ERROR = "preview.error"
    PREVIEW_LAYOUT_CHANGED = "preview.layout_changed"
    
    # 下载事件
    DOWNLOAD_TASK_CREATED = "download.task_created"
    DOWNLOAD_TASK_STARTED = "download.task_started"
    DOWNLOAD_TASK_PAUSED = "download.task_paused"
    DOWNLOAD_TASK_RESUMED = "download.task_resumed"
    DOWNLOAD_TASK_CANCELLED = "download.task_cancelled"
    DOWNLOAD_TASK_COMPLETED = "download.task_completed"
    DOWNLOAD_TASK_FAILED = "download.task_failed"
    DOWNLOAD_PROGRESS = "download.progress"
    
    # 扫描事件
    SCANNER_STARTED = "scanner.started"
    SCANNER_PROGRESS = "scanner.progress"
    SCANNER_DEVICE_FOUND = "scanner.device_found"
    SCANNER_COMPLETED = "scanner.completed"
    SCANNER_ERROR = "scanner.error"
    
    # UI事件
    UI_TAB_CHANGED = "ui.tab_changed"
    UI_NOTIFICATION = "ui.notification"
    UI_ERROR_DIALOG = "ui.error_dialog"
    
    # 系统事件
    SYSTEM_ERROR = "system.error"
    SYSTEM_SHUTDOWN = "system.shutdown"


# 全局实例
_event_bus = None

def get_event_bus() -> EventBus:
    """获取事件总线全局实例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
