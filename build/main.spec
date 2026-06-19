# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent.resolve()
ASSETS_DIR = PROJECT_ROOT / "assets"
SDK_DIR = PROJECT_ROOT / "sdk"

# 收集数据文件列表
datas = []
if SDK_DIR.exists():
    datas.append((str(SDK_DIR), "sdk"))
if ASSETS_DIR.exists():
    datas.append((str(ASSETS_DIR), "assets"))

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # 核心模块
        "src.core.sdk_loader",
        "src.core.database",
        "src.gui.main_window",
        "src.utils.system_check",
        # 主题与图标基础设施
        "src.gui.theme",
        "src.gui.icons",
        # 网络扫描
        "icmplib",
        "psutil",
        # 终端调试 (SSH - 延迟导入)
        "paramiko",
        "paramiko.transport",
        "paramiko.rsakey",
        "paramiko.ed25519key",
        "paramiko.ecdsakey",
        # 流量分析 (scapy - 延迟导入)
        "scapy.all",
        "scapy.arch.windows",
        "scapy.layers.inet",
        "scapy.layers.l2",
        # 加密与HTTP
        "cryptography",
        "requests",
        # 视频解码（运行时依赖 numpy）
        "src.core.player.video_decoder",
        "src.core.player.preview_manager_v2",
        "numpy",
        # PyQt6 内部模块 (确保打包完整)
        "PyQt6.sip",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets",
        # 新增标签页 (确保无遗漏)
        "src.gui.tabs.terminal_tab",
        "src.gui.tabs.network_quality_tab",
        "src.gui.tabs.speedtest_tab",
        "src.gui.tabs.ip_conflict_tab",
        "src.gui.tabs.traffic_analysis_tab",
        "src.gui.tabs.packet_capture_tab",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除测试框架与不必要的库以减小体积
        # 注意：numpy 被 src/core/player/video_decoder.py 运行时依赖，不可排除
        "unittest",
        "pytest",
        "pydoc",
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "sphinx",
        "setuptools",
        "pkg_resources",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EcoMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=str(ASSETS_DIR / "icon.ico") if (ASSETS_DIR / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EcoMonitor",
)
