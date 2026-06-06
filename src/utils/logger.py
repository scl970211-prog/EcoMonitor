"""
日志模块 - 统一的日志管理
"""

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
    
    # 清除已有处理器
    root_logger.handlers.clear()
    
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
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取命名日志记录器"""
    return logging.getLogger(name)
