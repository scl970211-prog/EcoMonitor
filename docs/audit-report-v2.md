# EcoMonitor 全量审核报告（2026-06-19）

> 审核范围：`src/`、`tests/`、`build/`、`installer/`、`.github/`、`docs/`、`AGENTS.md`、`README.md`、`main.py`、`pyproject.toml` 等。
> 审核方式：静态代码审查 + 工具扫描（pytest、py_compile）+ 多维度交叉复核。
> 验证结果：`python -m pytest tests/ -q` → **100 passed**；`scripts/run_ci_checks.py` → 通过。
> 仓库状态：工作区存在大量未提交/未跟踪文件（约 55 个），部分生成物（`output/*.exe`）已被 Git 跟踪但与 `.gitignore` 冲突。

---

## 执行摘要

本次审核共识别出 **5 项严重问题**、**12 项警告问题** 与 **多项建议改进**。最严重的问题集中在 **版本号不一致**、**设备密码明文流转与持久化**、**主窗口关闭崩溃**、**UI 线程阻塞** 以及 **安全/部署风险**。这些问题应在 `release/v1.0.1` 发布前优先修复。

| 维度 | 评级 | 关键发现 |
|---|---|---|
| 功能正确性 | 🟡 中 | 单元测试 100 通过，但大量异常被静默吞掉，真实问题难以暴露。 |
| 安全合规 | 🔴 差 | 设备密码在内存字典、SQLite 任务库、段级状态文件中均明文存在。 |
| 代码风格 / AGENTS 合规 | 🟠 较差 | 仍有 `print`、内联 `setStyleSheet`、硬编码路径/色值。 |
| 构建 / 部署 | 🟠 中高风险 | 版本号不一致；`.gitignore` 与已跟踪文件冲突；OpenGL 回退 DLL 被主动删除。 |
| 测试 / CI | 🟡 中 | 测试数量与文档不符；CI 未覆盖 `release/*` 分支；缺少 lint/类型检查。 |

---

## 严重问题（Critical）

### C1. 版本号不一致（阻塞发布）

- **文件**：
  - `src/__init__.py:5` — `__version__ = "1.0.0"`
  - `pyproject.toml:7` — `version = "1.0.0"`
  - `installer/setup.iss:6` — `#define MyAppVersion "1.0.0"`
  - `AGENTS.md:20` — 版本：`1.0.0`
- **问题**：当前工作区明显为 `release/v1.0.1` 分支目标，但所有版本标记仍为 `1.0.0`。`setup.iss` 会生成 `EcoMonitor_v1.0.0_setup.exe`，与发布流程期望的文件名冲突。
- **修复建议**：统一 bump 到 `1.0.1`；建立单一版本源（推荐 `src/__init__.__version__`），其他文件在构建时同步。

### C2. 设备密码明文持久化（安全合规）

- **文件**：
  - `src/core/database.py:25` — `TASK_COLUMNS["device_password"] = "TEXT"`
  - `src/core/download_task.py:37,229-265` — `to_dict`/`from_dict` 直接序列化明文密码
  - `src/core/segment_download.py:459-469` — 状态 JSON 写入 `device_password`
  - `src/core/segment_download.py:527-531` — 状态目录硬编码为 `%APPDATA%/HikvisionTool/tasks`
- **问题**：SQLite 任务库与段级断点续传状态文件均以明文保存设备密码；状态目录还使用了旧项目名称。
- **修复建议**：
  1. 任务 DB/JSON 中保存 `encrypt_password(password)`，读取时解密。
  2. 状态目录改为 `path_resolver.get_data_dir() / "task_states"`。
  3. 恢复任务时从加密配置/数据库重新获取密码，而非明文状态文件。

### C3. 设备密码在 UI / 内存中明文传播

- **文件**：
  - `src/core/device.py:867` — `get_device_info_dict()` 返回 `"password": self.password`
  - `src/gui/tabs/connection_tab.py:410` — `_get_device_info()` 把密码加入字典
  - `src/gui/main_window.py:700-703` — 通过信号/事件总线把含密码的 `device_info` 分发给各标签页
- **问题**：密码随 `device_info` 在 GUI 各模块间传播，可能进入日志、缓存或崩溃 dump。
- **修复建议**：从对外传递的 `device_info` 中移除 `password`；需要登录的下游模块独立获取并尽快使用。

### C4. 主窗口关闭时可能崩溃

- **文件**：`src/gui/main_window.py:963-966`
- **问题**：`terminal_tab` / `traffic_analysis_tab` 采用懒加载，未访问时属性存在但值为 `None`。`None.close()` 会抛出 `AttributeError`，导致程序退出异常。
- **修复建议**：
  ```python
  tab = getattr(self, 'terminal_tab', None)
  if tab is not None:
      tab.close()
  ```

### C5. 下载控制器在 UI 线程执行设备登录

- **文件**：`src/core/download_controller.py:128-141`
- **问题**：`_start_task` 在主线程实例化 `Device` 并调用 `login()`。SDK 网络超时会阻塞 GUI，登录失败也会在主线程报错。
- **修复建议**：将 `Device` 创建与登录移到 `DownloadWorker.run()`（工作线程）中；UI 线程只负责任务入队与状态更新。

---

## 警告问题（Warning）

### W1. `speedtest_tab.py` 在模块导入时修改全局代理

- **文件**：`src/gui/tabs/speedtest_tab.py:44-48`
- **问题**：导入模块时即删除所有 `HTTP_PROXY`/`HTTPS_PROXY` 等环境变量，影响整个进程的后续网络请求（包括 ISAPI/设备连接）。
- **修复建议**：将代理清空逻辑移到 `_build_opener()` 或测速函数内部，仅影响测速请求。

### W2. `EventBus` 同步事件跨线程触发与潜在死锁

- **文件**：`src/core/event_bus.py:174-196`、`src/core/event_bus.py:223`
- **问题**：`async_mode=False` 时直接在调用线程执行回调，可能跨线程访问 Qt 对象；`QMutex` 非递归，回调内若再次 `publish()` 会死锁。
- **修复建议**：工作线程统一使用 `async_mode=True`；对 Qt 对象回调改用 `QMetaObject.invokeMethod(..., Qt.QueuedConnection)`；或将 `QMutex` 改为 `QRecursiveMutex`。

### W3. 大量异常被静默吞掉

- **统计**：`src/` 下约 70 处 `except Exception: pass` 或未记录的 `pass`。
- **典型位置**：`src/core/device.py:150-151`、`src/gui/main_window.py:180`、`src/core/download_controller.py:170-171` 等。
- **修复建议**：至少改为 `logger.exception(...)` 或 `logger.warning(...)` 后再 `pass`；核心路径不应吞掉异常。

### W4. 项目中仍存在 `print()` 而非日志

- **文件**：`main.py:45-49`、`src/utils/system_check.py:120`、`src/core/scanner/expand_oui.py`、`src/core/scanner/merge_oui.py`、`src/core/scanner/onvif_scanner.py`。
- **修复建议**：按 AGENTS.md 统一使用 `logging`。

### W5. 内联 `setStyleSheet` 与硬编码色值仍大量存在

- **文件**：`src/gui/tabs/download_tab_v2.py`、`src/gui/widgets/video_widget.py`、`src/core/player/video_widget.py`、`src/gui/tabs/preview_tab_v2.py` 等。
- **修复建议**：将颜色/字号迁移到 `src.gui.theme`/`src.gui.constants`；将控件样式迁移到 `src.gui.styles.py` 的 QSS 选择器。

### W6. `segment_download.py` 状态目录硬编码为旧项目名

- **文件**：`src/core/segment_download.py:527-531`
- **修复建议**：改为 `path_resolver.get_data_dir() / "task_states"`。

### W7. `AGENTS.md` 与项目现状严重不同步

- **问题**：测试数量写“79 个用例”，实际 100 个；新增模块（`src/core/player/`、`src/core/scanner/` 等）未在项目结构中列出；版本号仍为 `1.0.0`。
- **修复建议**：按当前实际结构、测试数量、依赖、版本全面更新。

### W8. `.gitignore` 与已跟踪文件冲突

- **文件**：`.gitignore:27-28`
- **问题**：`.gitignore` 忽略 `/output`、`/docs`，但 `output/*.exe`、`docs/*.md` 已被跟踪，导致 `git status` 持续显示修改。
- **修复建议**：
  - 删除 `/docs` 忽略项；
  - 精确忽略生成产物（如 `output/*.exe`、`build/build/`、`build/main/`），保留 `build/main.spec`、`build/build.bat`、`build/post_build_cleanup.py`。

### W9. CI 未覆盖 `release/*` 分支且缺少 lint

- **文件**：`.github/workflows/ci.yml:5-7`、`.pre-commit-config.yaml`
- **修复建议**：
  - `branches` 增加 `release/*`；
  - CI 增加 `ruff check`、`black --check`、`mypy src`；
  - pre-commit 中完整 pytest 改为可选或按改动测试，避免提交耗时过长。

### W10. OpenGL 打包隐患

- **文件**：`build/main.spec:20-62`、`build/post_build_cleanup.py:37-42`、`src/core/player/video_widget.py:12-13`
- **问题**：`hiddenimports` 未显式包含 `PyQt6.QtOpenGLWidgets`、`PyQt6.QtOpenGL`；打包后主动删除 `opengl32sw.dll`。
- **修复建议**：增加 OpenGL hiddenimports；保留 software OpenGL 回退，或在文档中注明依赖 GPU/OpenGL。

### W11. ISAPI/HTTP 明文传输凭据

- **文件**：`src/core/isapi_client.py:22,47`
- **修复建议**：优先尝试 HTTPS（端口 443），并提供“忽略证书校验”选项；HTTP 仅作为降级并给出安全提示。

### W12. SSH 主机密钥策略不安全

- **文件**：`src/gui/tabs/terminal_tab.py:258`
- **问题**：使用 `paramiko.AutoAddPolicy()`，首次连接即信任任意主机密钥。
- **修复建议**：提示用户确认指纹，或支持导入已知主机密钥。

---

## 建议改进（Suggestion）

| 编号 | 问题 | 文件 | 修复建议 |
|---|---|---|---|
| S1 | 下载管理页每秒重建行控件 | `src/gui/tabs/download_manager_tab_v2.py:181-283` | 增量更新，避免内存泄漏与性能下降。 |
| S2 | MTU 测试可能把超时误判为成功 | `src/gui/tabs/network_quality_tab.py:569-578` | Windows 下明确成功条件：`returncode == 0` 且不含分段提示。 |
| S3 | DSCP 映射重复定义 | `src/core/constants.py`、`packet_capture_tab.py`、`traffic_analysis_tab.py` | 统一使用 `src.core.constants.DSCP_NAMES`。 |
| S4 | 密钥文件未限制 ACL | `src/utils/crypto.py:10-14` | 创建 `.key` 后设置仅当前用户可读（Windows ACL / `0o600`）。 |
| S5 | `main.py` 资源路径未统一 | `main.py:111,135-137` | 使用 `path_resolver.get_app_dir() / "assets"`。 |
| S6 | `crypto.py` 未复用 `path_resolver` | `src/utils/crypto.py:10-14` | 密钥路径改为 `get_data_dir() / ".key"`。 |
| S7 | `SDKLoader` 使用 `os.chdir` | `src/core/sdk_loader.py:259-271` | 改用 `os.add_dll_directory`（Python 3.8+）。 |
| S8 | `logger.py` 清空根 logger handlers | `src/utils/logger.py:35` | 只添加/更新项目 handler，避免影响 pytest/第三方库。 |
| S9 | `setup.iss` `AppId` 为占位符 | `installer/setup.iss:13` | 生成项目唯一 GUID。 |
| S10 | 安装包未代码签名 | `installer/setup.iss` | 申请证书并配置 `SignTool`，提升用户信任。 |
| S11 | 核心复杂模块缺乏测试 | `download_worker.py`、`segment_download.py`、`format_converter.py`、`scanner/` | 增加 mock/SDK stub 测试。 |
| S12 | Npcap 商业授权提示不足 | `AGENTS.md`、`README.md` | 显著位置提示商业/政府大规模部署需购买 Npcap OEM。 |

---

## 验证结果

| 检查项 | 命令/方式 | 结果 |
|---|---|---|
| 全量单元测试 | `.venv/Scripts/python.exe -m pytest tests/ -q` | **100 passed** |
| 本地 CI 脚本 | `.venv/Scripts/python.exe scripts/run_ci_checks.py` | **通过** |
| 语法检查 | CI 中 `py_compile` | **通过** |
| 版本一致性 | 多文件 grep | **不一致（仍为 1.0.0）** |
| 密码加密合规 | 静态审查 | **未合规（明文持久化）** |

---

## 修复优先级建议

1. **P0（阻塞发布）**
   - 同步版本号到 `1.0.1`。
   - 修复 `MainWindow.closeEvent` 空指针崩溃。
   - 停止在 `device_info` 中传播明文密码。
   - 对任务数据库/段状态文件中的密码做加密或移除。

2. **P1（发布前强烈建议）**
   - 修复 `EventBus` 跨线程安全。
   - 将下载设备登录移到工作线程。
   - 将 `speedtest_tab.py` 全局代理修改改为局部。
   - 修正 `segment_download.py` 状态目录。
   - 修复 `.gitignore` 与已跟踪文件冲突。

3. **P2（后续迭代）**
   - 清理内联样式与硬编码色值。
   - 替换 `print` 为日志。
   - 补充 CI lint/类型检查与 `release/*` 触发。
   - 为核心下载/扫描流程增加测试覆盖。
   - 完成主题 Token 化并默认启用 `Theme.SYSTEM`。

---

*报告生成时间：2026-06-19*  
*审计基于当前工作区状态，未覆盖真实海康 SDK / 网络扫描 / 抓包 / FFmpeg 等外部硬件/环境相关流程。*
