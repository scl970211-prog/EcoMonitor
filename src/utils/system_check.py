"""
系统环境自检模块

在 Qt 初始化前执行，检测：
1. VC++ Redistributable 2015-2022 x64
2. 数据目录写权限
3. SDK 关键文件完整性
"""

import ctypes
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _check_vcredist() -> tuple:
    """
    检测 VC++ 运行时 DLL 是否可用。
    策略：优先检查程序自带目录（_internal/ 或程序根目录），
          因为 PyInstaller 打包时已自动包含 VC++ 运行时 DLL，
          目标电脑无需单独安装 VC++ Redistributable。
    Returns: (是否通过, 描述信息)
    """
    from ..core.path_resolver import get_app_dir
    app_dir = get_app_dir()

    # 检查 1：程序自带目录（_internal/ 或根目录）
    search_dirs = [app_dir]
    internal_dir = app_dir / "_internal"
    if internal_dir.exists():
        search_dirs.append(internal_dir)

    vc_found = False
    msvcp_found = False
    for d in search_dirs:
        if (d / "vcruntime140.dll").exists():
            vc_found = True
        if (d / "msvcp140.dll").exists():
            msvcp_found = True

    if vc_found and msvcp_found:
        return True, "程序已自带 VC++ 运行时 DLL"

    # 检查 2：系统目录（降级方案）
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    if (system32 / "vcruntime140.dll").exists() and (system32 / "msvcp140.dll").exists():
        return True, "系统已安装 VC++ 运行时"

    return (
        False,
        "未找到 VC++ 运行时 DLL (vcruntime140.dll / msvcp140.dll)。\n"
        "请重新安装本程序，或从微软官网下载 VC++ Redistributable 2015-2022 x64。"
    )


def _check_data_dir_writable() -> tuple:
    """检测数据目录是否可写。"""
    try:
        from ..core.path_resolver import get_data_dir
        data_dir = get_data_dir()
        test_file = data_dir / ".write_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        return True, str(data_dir)
    except Exception as e:
        return False, f"无法写入数据目录: {e}"


def _check_sdk_complete() -> tuple:
    """检测 SDK 关键文件是否完整。"""
    try:
        from ..core.path_resolver import get_sdk_path
        sdk_path = get_sdk_path()
        required = [
            sdk_path / "HCNetSDK.dll",
            sdk_path / "HCCore.dll",
            sdk_path / "PlayCtrl.dll",
        ]
        missing = [f.name for f in required if not f.exists()]
        if missing:
            return False, f"缺少关键文件: {', '.join(missing)}"
        return True, "SDK 文件完整"
    except Exception as e:
        return False, f"SDK 检查异常: {e}"


def run_startup_check() -> dict:
    """
    运行启动自检。
    Returns:
        {
            "all_passed": bool,
            "checks": {
                "vcredist": (bool, str),
                "data_dir": (bool, str),
                "sdk": (bool, str),
            }
        }
    """
    checks = {
        "vcredist": _check_vcredist(),
        "data_dir": _check_data_dir_writable(),
        "sdk": _check_sdk_complete(),
    }
    all_passed = all(v[0] for v in checks.values())
    return {"all_passed": all_passed, "checks": checks}


def show_warning_dialog(title: str, message: str):
    """显示警告对话框（不依赖 Qt，确保自检失败时也能弹窗）。"""
    if sys.platform == "win32":
        try:
            # 0x30 = MB_ICONWARNING
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x30)
        except Exception:
            pass
    logger.error("[警告] %s: %s", title, message)
