# AGENTS.md - EcoMonitor 生态监控平台

> 本文件面向 AI 编程 Agent。读者应被假定为对该项目一无所知。

## 项目概述

**EcoMonitor 生态监控平台** 是一款面向 Windows 的桌面级综合视频设备管理与网络运维工具，主要用于管理和运维海康威视（Hikvision）等主流 DVR / NVR / IPC 设备。

核心功能包括：

1. **设备搜索** —— 局域网多协议设备扫描（ARP / Ping / TCP / ONVIF）。
2. **设备连接** —— 登录主流 DVR / NVR / IPC 设备。
3. **视频预览** —— 多通道实时预览，支持 1 / 4 / 9 / 16 画面布局。
4. **批量下载** —— 录像检索与批量下载，支持段级断点续传。
5. **下载管理** —— 下载任务队列、状态监控、格式转换。
6. **终端调试** —— 内置 SSH / Telnet 设备调试终端。
7. **网络诊断** —— Ping / MTU / 吞吐量测试、IP 冲突检测。
8. **流量分析** —— DSCP 检测与轻量抓包。

版本：`1.0.1`  
作者：孙成龙  
组织：中国水利水电科学研究院  
许可证：MIT License（见 `LICENSE`）

## 技术栈

- **运行环境**：Python 3.10+（当前开发/打包环境均为 Python 3.10.11）。
- **GUI 框架**：PyQt6（`>=6.4.0,<7.0.0`）。
- **设备 SDK**：海康威视 HCNetSDK、PlayCtrl SDK（Windows x64 DLL，位于 `sdk/win64/`）。
- **视频处理**：FFmpeg / FormatConverter.exe（位于 `sdk/tools/FormatConvert/`），`numpy` 用于帧处理。
- **网络扫描**：`psutil`、`icmplib`。
- **终端调试**：`paramiko`（SSH）。
- **抓包与流量分析**：`scapy`（安装包已集成 Npcap 安装程序；源码运行仍需手动安装）。
- **配置/密码**：JSON 配置 + `cryptography` 对称加密（Fernet）。
- **数据持久化**：SQLite（下载任务表）。

## 项目结构

```
EcoMonitor/
├── main.py                 # 程序入口
├── requirements.txt        # Python 依赖
├── AGENTS.md               # 本文件
├── README.md               # 用户文档
├── LICENSE                 # 许可证
├── assets/                 # 图标、启动画面
│   ├── icon.ico
│   └── splash.png
├── build/                  # PyInstaller 打包配置
│   ├── build.bat
│   ├── main.spec
│   └── post_build_cleanup.py
├── data/                   # 用户数据样例/模板（运行时真正数据在 %LOCALAPPDATA%）
│   └── config.json
├── dist/                   # PyInstaller 输出目录
│   └── EcoMonitor/
├── docs/                   # 版本更新流程等文档
│   └── version-update.md
├── installer/              # Inno Setup 安装脚本
│   ├── redist/
│   └── setup.iss
├── sdk/                    # 设备 SDK 与工具
│   ├── tools/              # FormatConvert / ffmpeg.exe 等
│   └── win64/              # HCNetSDK.dll、PlayCtrl.dll 等 Windows x64 DLL
├── src/                    # 源代码
│   ├── __init__.py         # 包元数据（版本、作者、组织）
│   ├── core/               # 核心模块
│   │   ├── constants.py        # 核心常量（端口、超时、设备类型、DSCP 等）
│   │   ├── sdk_loader.py       # HCNetSDK DLL 加载与 API 封装
│   │   ├── device.py           # 设备登录/登出/预览/下载/通道元数据
│   │   ├── database.py         # SQLite 任务持久化
│   │   ├── download_controller.py   # 下载任务编排
│   │   ├── download_task.py    # 任务模型
│   │   ├── download_worker.py  # 下载工作线程
│   │   ├── segment_download.py # 段级下载管理
│   │   ├── format_converter.py # 格式转换封装
│   │   ├── video_preview.py    # 视频预览封装
│   │   ├── video_searcher.py   # 录像文件检索
│   │   ├── video_download.py   # 录像下载
│   │   ├── isapi_client.py     # ISAPI/HTTP 通道信息获取
│   │   ├── path_resolver.py    # 资源/数据/日志路径解析
│   │   ├── app_state.py        # 全局应用状态
│   │   ├── event_bus.py        # 应用内事件总线
│   │   ├── player/             # 视频渲染组件（OpenGL / QPainter 窗格）
│   │   │   ├── __init__.py
│   │   │   └── video_widget.py
│   │   └── scanner/            # 扫描子模块
│   │       ├── scanner_manager.py
│   │       ├── enhanced_scanner.py
│   │       ├── fast_scanner.py
│   │       ├── onvif_scanner.py
│   │       ├── device_info.py
│   │       ├── device_fingerprint.py
│   │       └── network_utils.py
│   ├── gui/                # 图形界面
│   │   ├── constants.py        # UI 常量（颜色、字号、TabLabel、状态色等）
│   │   ├── main_window.py      # 主窗口（含标签页管理、全局日志、自动登录）
│   │   ├── styles.py           # 全局 QSS 样式与设计系统入口
│   │   ├── theme.py            # 主题模式/Token/ThemeManager（浅色/深色/跟随系统）
│   │   ├── icons.py            # 系统图标字体（Segoe Fluent Icons）渲染工具
│   │   ├── tabs/               # 各功能标签页
│   │   │   ├── connection_tab.py
│   │   │   ├── device_scan_tab.py
│   │   │   ├── preview_tab_v2.py
│   │   │   ├── download_tab_v2.py
│   │   │   ├── download_manager_tab_v2.py
│   │   │   ├── terminal_tab.py
│   │   │   ├── network_quality_tab.py
│   │   │   ├── speedtest_tab.py
│   │   │   ├── ip_conflict_tab.py
│   │   │   ├── traffic_analysis_tab.py
│   │   │   └── packet_capture_tab.py
│   │   └── widgets/            # 自定义控件
│   │       ├── video_grid_v2.py
│   │       ├── video_widget.py
│   │       └── draggable_channel_list.py
│   └── utils/              # 工具模块
│       ├── config.py           # JSON 配置管理（含密码加密）
│       ├── crypto.py           # Fernet 密码加密
│       ├── logger.py           # 日志系统初始化
│       └── system_check.py     # 启动自检（VC++ 运行时、数据目录、SDK 完整性）
└── tests/                  # 测试目录
    └── test_imports.py
```

## 运行时架构

- **入口**：`main.py`
  1. 初始化日志（`src.utils.logger.setup_logger`）。
  2. 启动自检（`src.utils.system_check.run_startup_check`），检查 VC++ 运行时、数据目录写权限、SDK 文件完整性；缺失关键项则弹窗警告，致命错误会退出。
  3. 初始化 `QApplication`，启用高 DPI，设置字体（Microsoft YaHei 9pt）、图标、启动画面。
  4. 创建并显示 `src.gui.main_window.MainWindow`，进入事件循环。

- **路径约定**：
  - **只读资源**（SDK、assets、打包后的 exe 目录）：使用 `src.core.path_resolver.get_app_dir()`，兼容源码运行与 PyInstaller 打包环境（通过 `sys._MEIPASS` 与 `sys.frozen` 自动判断）。
  - **用户数据**（配置、数据库、日志、临时文件）：统一写入 `%LOCALAPPDATA%/EcoMonitor`（降级为 `~/EcoMonitor`）。

- **配置**：`src.utils.config.Config` 单例，保存为 `%LOCALAPPDATA%/EcoMonitor/config.json`。`device.password` 字段默认被 Fernet 加密。

- **加密密钥**：`src.utils.crypto` 在 `%LOCALAPPDATA%/EcoMonitor/.key` 生成/读取 Fernet 密钥。

- **SDK 加载**：`src.core.sdk_loader.SDKLoader` 单例，使用 `ctypes.WinDLL` 加载 `sdk/win64/HCNetSDK.dll`，并将 `HCNetSDKCom` 子目录加入 `PATH`，仅支持 Windows。

- **设备对象**：`src.core.device.Device` 基于 PyQt6 `QObject`，封装登录/登出、自动重连、通道元数据（优先 ISAPI，失败回退 SDK）、实时预览、按文件名/时间下载。

- **下载管理**：`src.core.download_controller.DownloadManager` 维护任务队列，使用 `QThreadPool` 调度 `DownloadWorker`，并通过 SQLite 持久化任务状态。

- **事件通信**：`src.core.event_bus.EventBus` 与 `src.core.app_state.AppState` 提供全局状态与事件机制；各 GUI 标签页通过信号/事件与核心模块交互。

## 开发环境准备

1. 安装 Python 3.10+（推荐 Python 3.10.11）。
2. 创建并激活虚拟环境（推荐 `.venv`）：

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. 安装依赖：

   ```bash
   pip install -r requirements.txt
   pip install pytest
   ```

3. 确保 `sdk/win64/` 下存在关键 DLL：`HCNetSDK.dll`、`HCCore.dll`、`PlayCtrl.dll`。

> 注：Npcap 是 `scapy` 抓包/流量分析功能所依赖的 Windows 驱动。使用安装包部署时，安装向导会提示安装 Npcap；源码开发/运行时可从 <https://npcap.com/#download> 手动安装。

## 运行程序

```bash
python main.py
```

> Windows 系统建议以管理员身份运行，以保证 ARP 扫描等功能正常工作。

## 测试

测试位于 `tests/`，使用 `pytest` 运行：

```bash
python -m pytest tests/ -v
```

或运行本地 CI 检查脚本（自动检测并使用项目虚拟环境）：

```bash
python scripts/run_ci_checks.py
```

当前包含 **100 个用例**，覆盖：

- 包元数据与核心模块导入 (`test_imports.py`)。
- 配置读写与密码加密 (`test_config.py`)。
- 加解密工具 (`test_crypto.py`)。
- 核心常量与枚举 (`test_constants.py`)。
- 路径解析 (`test_path_resolver.py`)。
- 下载任务模型 (`test_download_task.py`)。
- 事件总线 (`test_event_bus.py`)。
- 应用全局状态 (`test_app_state.py`)。
- 设备登录/登出 mock 测试 (`test_device.py`)。
- 扫描器网络工具 (`test_scanner_network_utils.py`)。
- 扫描器设备信息解析 (`test_scanner_device_info.py`)。

> GUI 交互、视频预览、真实 SDK 调用、网络扫描、抓包等依赖外部环境或硬件的功能仍建议手动验证。

## 持续集成

项目已配置 GitHub Actions：

- 工作流文件：`.github/workflows/ci.yml`
- 运行环境：`windows-latest`
- 测试矩阵：Python 3.10
- 执行步骤：安装依赖 → 语法检查 → 运行 pytest → 验证 `src` 包导入

本地提交前也可启用 pre-commit：

```bash
pre-commit install
pre-commit run --all-files
```

> pre-commit 配置位于 `.pre-commit-config.yaml`，包含通用代码检查 hooks 和本地 pytest hook。

## 构建与发布

### 1. PyInstaller 打包

```bash
# 方式一：运行打包脚本（推荐）
build\build.bat

# 方式二：直接调用 pyinstaller
pyinstaller --clean build/main.spec
```

打包产物位于 `dist/EcoMonitor/`，包含 `EcoMonitor.exe`、`_internal/`、`sdk/`、`assets/`。

`build/main.spec` 要点：

- `console=False`：生成无控制台窗口的 GUI 程序。
- 将 `sdk/` 与 `assets/` 作为数据文件打包。
- 显式 `hiddenimports` 包含 `paramiko`、`scapy`、`cryptography`、`requests` 及各新增标签页。
- 排除 `unittest`、`pytest`、`matplotlib`、`numpy` 等以减小体积。

`build/post_build_cleanup.py` 会在打包后自动删除不影响功能的大文件（多余的 Qt 翻译、OpenGL Software 回退、PDF DLL、多余图片格式插件、`ffprobe.exe` 等）。

### 2. 生成安装程序

使用 Inno Setup 编译 `installer/setup.iss`：

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
```

输出：`output/EcoMonitor_v1.0.1_setup.exe`。

安装脚本要点：

- 需要管理员权限（`PrivilegesRequired=admin`）。
- 仅支持 x64 架构。
- 程序已通过 PyInstaller 自带 VC++ 运行时 DLL，安装包不再单独分发 `vc_redist.x64.exe`。
- 安装向导默认勾选“安装 Npcap 抓包驱动”，仅在系统未检测到已安装 Npcap 时才会启动 Npcap 安装程序。

### 3. 版本发布流程

详见 `docs/version-update.md`。关键步骤：

1. 创建 `release/vX.Y.Z` 分支。
2. 修改源码并同步更新 `installer/setup.iss` 中的 `MyAppVersion`。
3. 合并到 `main`。
4. 运行 `build\build.bat` 打包。
5. 使用 Inno Setup 编译安装程序。
6. 在 GitHub 发布 Release 并上传安装包。

## 代码风格指南

- **语言**：代码注释、文档字符串、用户界面文本均以中文为主。AI Agent 在新增注释/文档/界面文案时，应保持中文。
- **编码**：Python 源文件使用 UTF-8，建议在文件头标注 `# -*- coding: utf-8 -*-`。
- **命名**：
  - 模块/类/函数：遵循 PEP 8，使用 `snake_case` 函数、`CamelCase` 类名。
  - SDK 结构体/常量：保留海康 SDK 原始命名，如 `NET_DVR_DEVICEINFO_V30`、`NET_DVR_PREVIEWINFO`。
- **日志**：统一使用标准库 `logging`；通过 `logger = logging.getLogger(__name__)` 获取 logger。不要直接 `print`。
- **路径**：一律使用 `pathlib.Path`；程序资源与用户数据路径统一通过 `src.core.path_resolver` 获取，禁止硬编码。
- **线程**：GUI 线程与耗时操作分离，使用 `QThreadPool`、`QRunnable`、`QTimer` 或 `DownloadWorker` 模式。
- **Qt 信号**：设备、下载管理器、扫描管理器等核心对象通过 `pyqtSignal` 向 GUI 发送事件。
- **密码安全**：用户密码必须经 `src.utils.crypto.encrypt_password` 加密后写入配置，禁止明文保存。

### 设计系统 / UI 约定

- **颜色、字号、间距**统一使用 `src.gui.constants` 中的 `Color`、`FontSize`、`Size`、`StatusColor`，避免在代码中硬编码 `#107c10`、`#999` 等色值。
- **标签页标题**使用 `src.gui.constants.TabLabel` 常量，禁止使用 Emoji 作为标签或按钮文案，避免不同系统字体/渲染差异导致显示异常。
- **全局样式**通过 `src.gui.styles.get_global_stylesheet()` 统一注入；特殊控件可通过 `setObjectName` 配合 QSS 选择器命中，减少内联 `setStyleSheet`。
- **核心常量**（端口、超时、设备类型、DSCP 映射等）统一放在 `src.core.constants`。

## 安全与部署注意事项

- **Windows 专用**：由于使用 `ctypes.WinDLL`，项目只能在 Windows 上运行和开发。
- **管理员权限**：ARP 扫描、部分网络诊断、抓包功能需要管理员权限；普通安装目录运行无此问题，因为数据写入 `%LOCALAPPDATA%`。
- **SDK 完整性**：启动自检会检查 `HCNetSDK.dll` 等关键文件；若打包后缺失，程序会在启动时弹窗提示。
- **VC++ 运行时**：打包后由 PyInstaller 自动包含 `vcruntime140.dll`、`msvcp140.dll` 等，目标机器无需额外安装。
- **密码加密**：Fernet 密钥存储在用户本地 `%LOCALAPPDATA%/EcoMonitor/.key`，提供基础保护，但不应视为高安全等级。
- **外部依赖**：`scapy` / `Npcap`、海康 SDK DLL 均为外部二进制依赖，升级时需同步验证兼容性。
- **Npcap 许可**：安装包中分发的 Npcap 安装程序来自 <https://npcap.com/>。Npcap 免费版遵循其自有许可协议，非商业场景下可免费使用；商业/政府大规模部署或需要静默安装、再分发时，请购买 [Npcap OEM](https://npcap.com/oem) 授权。

## 常见修改入口

| 想要修改的功能 | 推荐查看的文件 |
|---|---|
| 启动流程 / 全局状态 | `main.py`、`src/core/app_state.py`、`src/core/event_bus.py` |
| 设备登录与连接 | `src/core/device.py`、`src/gui/tabs/connection_tab.py` |
| 局域网扫描 | `src/core/scanner/`、`src/gui/tabs/device_scan_tab.py` |
| 视频预览 | `src/core/player/`、`src/gui/tabs/preview_tab_v2.py`、`src/gui/widgets/video_grid_v2.py` |
| 录像下载 | `src/core/download_controller.py`、`src/core/download_worker.py`、`src/core/segment_download.py`、`src/gui/tabs/download_tab_v2.py` |
| 下载任务管理 | `src/core/database.py`、`src/gui/tabs/download_manager_tab_v2.py` |
| 配置与密码 | `src/utils/config.py`、`src/utils/crypto.py` |
| 样式 / UI 外观 | `src/gui/styles.py`、`src/gui/theme.py`、`src/gui/icons.py` |
| 打包与安装 | `build/main.spec`、`build/build.bat`、`build/post_build_cleanup.py`、`installer/setup.iss` |

## 依赖清单

见 `requirements.txt` 完整内容，主要包括：

- `PyQt6>=6.4.0,<7.0.0`
- `PyQt6-Qt6>=6.4.0,<7.0.0`
- `psutil>=5.9.0,<6.0.0`
- `icmplib>=3.0.0,<4.0.0`
- `paramiko>=3.4.0,<4.0.0`
- `scapy>=2.5.0,<3.0.0`
- `numpy>=1.24.0,<2.0.0`
- `cryptography>=41.0.0,<44.0.0`
- `requests>=2.31.0,<3.0.0`
