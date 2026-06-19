"""
日志模块 - 统一的日志管理
"""

import contextlib
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

from ..core.path_resolver import get_log_dir


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    """
    设置日志系统
    
    Args:
        level: 日志级别
    
    Returns:
        根日志记录器
    """
    log_dir = get_log_dir()
    
    # 创建日志文件名
    today = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f"app_{today}.log"
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 仅移除本应用之前添加的 handler，避免清空 pytest/第三方库已注册的 handler
    attr_name = "_eco_monitor_handlers"
    for old_handler in getattr(root_logger, attr_name, []):
        with contextlib.suppress(Exception):
            old_handler.close()
            root_logger.removeHandler(old_handler)

    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # 文件处理器 (每天一个文件，保留7天)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when='midnight', backupCount=7,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    setattr(root_logger, attr_name, [file_handler, console_handler])

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取命名日志记录器"""
    return logging.getLogger(name)
