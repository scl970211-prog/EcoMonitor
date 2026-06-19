"""
EcoMonitor 生态监控平台 - 主程序入口 (PyQt6 整合版)

整合功能：
- 设备搜索：局域网设备发现
- 设备连接：视频设备登录
- 视频预览：多通道实时预览
- 批量下载：录像下载
- 下载管理：下载任务管理

技术栈：Python 3.10+ + PyQt6 + 设备 SDK
"""

import sys
import os
import logging
import traceback
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def show_startup_error(title: str, message: str):
    """显示启动错误（不依赖 Qt）"""
    # 尝试写入日志文件
    try:
        log_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 
                               'EcoMonitor', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'startup_error.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{title}]\n{message}\n")
    except Exception:
        pass
    
    # 显示错误对话框
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
        except Exception:
            pass
    
    # 控制台输出（日志初始化前使用默认 handler）
    logging.error("\n%s", '=' * 60)
    logging.error("启动错误: %s", title)
    logging.error('%s', '=' * 60)
    logging.error("%s", message)
    logging.error('%s', '=' * 60)


def main():
    """主函数"""
    # 初始化日志
    import logging
    logger = logging.getLogger(__name__)
    try:
        from src.utils.logger import setup_logger
        setup_logger(logging.INFO)
        logger.info("=" * 60)
        logger.info("EcoMonitor 生态监控平台启动")
        logger.info("=" * 60)
    except Exception as e:
        show_startup_error("日志初始化失败", str(e))
        # 继续运行，logger 保持默认配置

    # 启动自检
    try:
        from src.utils.system_check import run_startup_check, show_warning_dialog
        check_result = run_startup_check()
        if not check_result["all_passed"]:
            warnings = []
            fatal = False
            for name, (ok, msg) in check_result["checks"].items():
                if not ok:
                    warnings.append(msg)
                    if name in ("sdk", "data_dir"):
                        fatal = True
            show_warning_dialog(
                "环境检查警告",
                "检测到以下问题，可能影响程序运行：\n\n" + "\n\n".join(warnings)
            )
            if fatal:
                return 1
    except Exception as e:
        show_startup_error("启动自检失败", str(e))
        # 不阻断，继续尝试启动

    # 初始化 Qt 应用
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
    except ImportError as e:
        show_startup_error("依赖缺失", f"无法加载 PyQt6: {e}\n请安装: pip install PyQt6")
        return 1

    # 启用高 DPI 支持
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)

    # 设置应用图标（任务栏 & 窗口左上角）
    try:
        from PyQt6.QtGui import QIcon
        from src.core.path_resolver import get_app_dir
        icon_path = get_app_dir() / "assets" / "icon.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass

    # 设置应用字体
    try:
        font = QFont("Microsoft YaHei", 9)
        app.setFont(font)
    except Exception:
        pass

    # 设置应用信息
    from src import __version__
    app.setApplicationName("EcoMonitor 生态监控平台")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("EcoMonitor")

    # 启动画面
    splash = None
    try:
        from PyQt6.QtWidgets import QSplashScreen
        from PyQt6.QtGui import QPixmap
        from src.core.path_resolver import get_app_dir
        splash_candidates = [
            get_app_dir() / "assets" / "splash.png",
            get_app_dir() / "assets" / "splash.jpg",
        ]
        for candidate in splash_candidates:
            if candidate.exists():
                splash = QSplashScreen(QPixmap(str(candidate)))
                splash.show()
                app.processEvents()
                break
    except Exception:
        pass

    # 创建主窗口
    try:
        from src.gui.main_window import MainWindow
        window = MainWindow()
        window.show()
        logger.info("主窗口创建成功")
    except Exception as e:
        show_startup_error("界面初始化失败", f"无法创建主窗口: {e}\n\n{traceback.format_exc()}")
        return 1

    # 关闭启动画面
    if splash is not None:
        try:
            splash.finish(window)
        except Exception:
            pass

    # 运行应用
    try:
        exit_code = app.exec()
        logger.info(f"程序退出，代码: {exit_code}")
        return exit_code
    except Exception as e:
        show_startup_error("运行时错误", f"程序异常退出: {e}\n\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        show_startup_error("未知错误", f"程序异常退出: {e}\n\n{traceback.format_exc()}")
        sys.exit(1)
