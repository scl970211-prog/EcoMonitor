"""
兼容导入层。

项目统一使用 download_controller.DownloadManager。
"""

from .download_controller import DownloadManager

__all__ = ["DownloadManager"]
