"""
路径解析模块 - 处理 SDK 和资源路径
"""

import os
import sys
from pathlib import Path
from typing import List


def get_resource_dirs() -> List[Path]:
    """获取可能的资源目录列表，兼容源码和打包环境。"""
    candidates: List[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent)
    else:
        candidates.append(Path(__file__).resolve().parents[2])

    unique_candidates: List[Path] = []
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def get_app_dir() -> Path:
    """获取程序安装目录（只读资源）。打包后指向 exe 所在目录。"""
    return get_resource_dirs()[0]


def get_base_dir() -> Path:
    """获取程序基础目录（兼容旧版接口，语义同 get_app_dir）。"""
    return get_app_dir()


def get_data_dir() -> Path:
    """
    获取用户数据目录（读写配置、数据库、日志）。
    使用 %LOCALAPPDATA% 确保普通用户权限下可写入。
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        data_dir = Path(local_appdata) / "EcoMonitor"
    else:
        # 降级方案
        data_dir = Path.home() / "EcoMonitor"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_sdk_path() -> Path:
    """获取 SDK 路径（程序目录内，只读）。"""
    for base in get_resource_dirs():
        sdk_path = base / "sdk" / "win64"
        if sdk_path.exists():
            return sdk_path
    return get_app_dir() / "sdk" / "win64"


def get_format_convert_path() -> Path:
    """获取 FormatConverter.exe 路径（程序目录内，只读）。"""
    for base in get_resource_dirs():
        for path in (
            base / "sdk" / "tools" / "FormatConvert" / "FormatConverter.exe",
            base / "tools" / "FormatConverter.exe",
        ):
            if path.exists():
                return path
    return get_app_dir() / "sdk" / "tools" / "FormatConvert" / "FormatConverter.exe"


def get_db_path() -> Path:
    """获取数据库路径（用户数据目录，读写）。"""
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)
    return data_dir / "tasks.db"


def get_temp_dir() -> Path:
    """获取临时目录（用户数据目录，读写）。"""
    data_dir = get_data_dir()
    temp_dir = data_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir


def get_config_path() -> Path:
    """获取配置文件路径（用户数据目录，读写）。"""
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)
    return data_dir / "config.json"


def get_log_dir() -> Path:
    """获取日志目录（用户数据目录，读写）。"""
    data_dir = get_data_dir()
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def check_sdk_exists() -> tuple:
    """检查 SDK 是否存在（程序目录内）。"""
    sdk_path = get_sdk_path()
    hc_sdk = sdk_path / "HCNetSDK.dll"

    if not hc_sdk.exists():
        return False, f"HCNetSDK.dll 未找到: {hc_sdk}"

    return True, "SDK 检查通过"


def check_ffmpeg_exists() -> tuple:
    """检查 FFmpeg 是否存在。"""
    base = get_app_dir()

    # 检查多个可能位置
    possible_paths = [
        base / "sdk" / "tools" / "FormatConvert" / "ffmpeg.exe",
        base / "ffmpeg.exe",
    ]

    # 检查环境变量
    import shutil
    ffmpeg_in_path = shutil.which("ffmpeg")

    if ffmpeg_in_path:
        return True, f"FFmpeg 在环境变量中: {ffmpeg_in_path}"

    for path in possible_paths:
        if path.exists():
            return True, f"FFmpeg 找到: {path}"

    return False, "FFmpeg 未找到"


# 保持兼容性
PathResolver = type('PathResolver', (), {
    'get_app_dir': staticmethod(get_app_dir),
    'get_base_dir': staticmethod(get_base_dir),
    'get_data_dir': staticmethod(get_data_dir),
    'get_resource_dirs': staticmethod(get_resource_dirs),
    'get_sdk_path': staticmethod(get_sdk_path),
    'get_format_convert_path': staticmethod(get_format_convert_path),
    'get_db_path': staticmethod(get_db_path),
    'get_temp_dir': staticmethod(get_temp_dir),
    'get_config_path': staticmethod(get_config_path),
    'get_log_dir': staticmethod(get_log_dir),
    'check_sdk_exists': staticmethod(check_sdk_exists),
    'check_ffmpeg_exists': staticmethod(check_ffmpeg_exists),
})()
