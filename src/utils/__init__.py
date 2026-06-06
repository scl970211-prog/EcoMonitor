"""
工具模块 - 通用工具函数
"""

import subprocess
import platform


def run_hidden(cmd, **kwargs):
    """在隐藏窗口中运行命令"""
    if platform.system() == "Windows":
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)
