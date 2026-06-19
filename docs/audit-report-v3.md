# EcoMonitor 第二轮全量审核报告（2026-06-19）

> 审核范围：`src/`、`tests/`、`build/`、`installer/`、`.github/`、`docs/`、`AGENTS.md`、`README.md`、`main.py`、`pyproject.toml`、`.gitignore` 等。
> 审核方式：静态代码审查 + 自动化扫描（pytest、py_compile、ast 统计）+ 与 v2 报告对照。
> 验证结果：`python -m pytest tests/ -q` → **100 passed**；`scripts/run_ci_checks.py` → **通过**。

---

## 执行摘要

第一轮审核中识别的 **5 项严重问题** 与 **12 项警告问题** 已基本按 P0 → P1 → P2 顺序修复完成。第二轮审核未发现新的严重问题，但仍存在若干 **P1/P2 残留风险** 与 **建议改进项**，主要集中在安全细节、打包稳定性、Git 索引清理和长期可维护性。

| 维度 | 评级 | 关键发现 |
|---|---|---|
| 功能正确性 | 🟢 良 | 单元测试 100 通过，CI 脚本通过。 |
| 安全合规 | 🟡 中 | 密码明文传播/持久化已修复，但 SSH 主机密钥策略、ISAPI HTTP 明文传输、密钥文件 ACL 仍未处理。 |
| 代码风格 / AGENTS 合规 | 🟢 良 | `src/` 内已无实际 `print()` 调用；非主题文件中已无硬编码十六进制色值；`setStyleSheet` 仍有少量但均使用 theme token。 |
| 构建 / 部署 | 🟡 中 | `output/EcoMonitor_v1.0.0_setup.exe` 仍被跟踪且与新版本冲突；OpenGL 隐藏导入/回退 DLL 处理存在隐患；`setup.iss` AppId 仍为占位符。 |
| 测试 / CI | 🟢 良 | CI 已覆盖 `release/*`；测试数量与文档一致。 |

---

## 已验证修复（来自 v2 报告）

| 原编号 | 问题 | 状态 | 关键改动 |
|---|---|---|---|
| C1 | 版本号不一致 | ✅ 已修复 | 统一为 `1.0.1` |
| C2 | 密码明文持久化 | ✅ 已修复 | `DownloadTask`、`segment_download` 状态文件加密密码 |
| C3 | `device_info` 传播明文密码 | ✅ 已修复 | `connection_tab.py`、`device.py` 移除 `password` 字段；下载页从加密配置读取 |
| C4 | 主窗口关闭崩溃 | ✅ 已修复 | `closeEvent` 判空后关闭懒加载标签页 |
| C5 | 下载登录在 UI 线程 | ✅ 已修复 | `Device` 创建与 `login()` 移至 `DownloadWorker.run()` |
| W1 | speedtest 全局代理 | ✅ 已修复 | 移除 `os.environ.pop`，`_build_opener` 局部无代理 |
| W2 | EventBus 跨线程/死锁 | ✅ 已修复 | `QRecursiveMutex` + `QMutexLocker`；跨线程信号投递 |
| W6 | 段状态目录旧项目名 | ✅ 已修复 | 改为 `get_data_dir() / "task_states"` |
| W8 | `.gitignore` 冲突 | ⚠️ 部分修复 | 已删除 `/docs`、细化 `/output/*.exe` 与 `build/build/` 等；但 `output/EcoMonitor_v1.0.0_setup.exe` 仍被跟踪 |
| W9 | CI 分支覆盖 | ✅ 已修复 | 增加 `release/*` 触发 |

---

## 残留问题（Warning / 需关注）

### R1. SSH 主机密钥策略不安全

- **文件**：`src/gui/tabs/terminal_tab.py:258`
- **问题**：仍使用 `paramiko.AutoAddPolicy()`，首次连接即信任任意主机密钥，存在中间人攻击风险。
- **建议**：提示用户确认指纹，或支持导入/保存已知主机密钥。

### R2. ISAPI/HTTP 明文传输凭据

- **文件**：`src/core/isapi_client.py:22`
- **问题**：`self.base_url = f"http://{ip}:{port}"`，设备凭据通过 HTTP 明文发送。
- **建议**：优先尝试 HTTPS（443），提供“忽略证书校验”降级选项；HTTP 仅作为最后降级并弹窗提示。

### R3. 密钥文件未限制 ACL

- **文件**：`src/utils/crypto.py:10-14, 37-39, 70-72`
- **问题**：`.key` 文件创建时未设置仅当前用户可读，其他用户/进程可能读取 Fernet 密钥。
- **建议**：创建后设置 Windows ACL（或至少 `0o600`），并定期审计密钥文件权限。

### R4. `output/EcoMonitor_v1.0.0_setup.exe` 仍被 Git 跟踪

- **问题**：`.gitignore` 已改为忽略 `/output/*.exe`，但旧版安装包仍留在索引中，导致：
  1. 仓库体积持续增长；
  2. `git status` 中显示 `AM output/EcoMonitor_v1.0.0_setup.exe`，与新版本 `1.0.1` 文件名冲突。
- **建议**：`git rm --cached output/EcoMonitor_v1.0.0_setup.exe` 并从工作区删除；如需保留历史版本，应通过 GitHub Release 分发。

### R5. OpenGL 打包隐患

- **文件**：`build/main.spec:20-62`、`build/post_build_cleanup.py:37-42`
- **问题**：
  1. `hiddenimports` 未显式包含 `PyQt6.QtOpenGLWidgets`、`PyQt6.QtOpenGL`；
  2. 打包后主动删除 `opengl32sw.dll`，在仅支持 Software OpenGL 的环境中可能无法启动视频渲染。
- **建议**：增加 OpenGL hiddenimports；保留 `opengl32sw.dll` 或在文档中显著说明 GPU/OpenGL 依赖。

### R6. `setup.iss` AppId 为占位符

- **文件**：`installer/setup.iss:13`
- **问题**：`AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}` 为占位 GUID，安装升级时可能造成版本覆盖混乱。
- **建议**：生成项目唯一 GUID 并替换。

### R7. MTU 测试可能把超时误判为成功

- **文件**：`src/gui/tabs/network_quality_tab.py:569-578`
- **问题**：`result.returncode != 0` 且输出不含 `fragment`/`需要分段` 时，代码将 `success` 设为 `True`，可能把请求超时/不可达误判为 MTU 可用。
- **建议**：Windows 下明确成功条件：`returncode == 0` 且输出不含分段提示；非零返回码统一视为失败。

### R8. DSCP 映射重复定义

- **文件**：`src/core/constants.py:96`、`src/gui/tabs/packet_capture_tab.py:450-454`、`src/gui/tabs/traffic_analysis_tab.py:30-50`
- **问题**：DSCP 名称映射在三处分别维护，容易不一致。
- **建议**：统一使用 `src.core.constants.DSCP_NAMES`。

### R9. `logger.py` 清空根 logger handlers

- **文件**：`src/utils/logger.py:35`
- **问题**：`root_logger.handlers.clear()` 会移除 pytest、第三方库已注册的 handler，影响调试与测试输出捕获。
- **建议**：仅添加/更新本项目 handler，避免清理非本应用注册的 handler。

### R10. `crypto.py` 未复用 `path_resolver`

- **文件**：`src/utils/crypto.py:10-14`
- **问题**：密钥路径硬编码 `%LOCALAPPDATA%/EcoMonitor/.key`，与项目统一的路径解析约定不一致。
- **建议**：改为 `get_data_dir() / ".key"`，便于测试与打包环境统一。

---

## 统计

| 指标 | 数值 | 说明 |
|---|---|---|
| pytest 用例 | 100 passed | 与 AGENTS.md 一致 |
| 静默 `except: pass` | 72 处 | 较 v2 报告（约 70 处）基本持平，多为 UI/资源清理防御代码 |
| `src/` 实际 `print()` 调用 | 0 | 已统一为 logging |
| 非主题文件硬编码色值 | 0 | 色值均集中在 `theme.py`/`styles.py`/`constants.py` |

---

## 建议改进（Suggestion）

| 编号 | 问题 | 文件 | 优先级 |
|---|---|---|---|
| S1 | 下载管理页每秒重建行控件 | `src/gui/tabs/download_manager_tab_v2.py:181-206` | P2 |
| S2 | SDKLoader 仍使用 `os.chdir` | `src/core/sdk_loader.py:276,304` | P2（当前已有 `add_dll_directory` 回退，但 `os.chdir` 仍改变进程 CWD） |
| S3 | 为核心下载/扫描流程增加测试 | `download_worker.py`、`segment_download.py`、`scanner/` | P2 |
| S4 | 安装包代码签名 | `installer/setup.iss` | P2 |
| S5 | Npcap 商业授权提示 | `README.md` | 已部分在 AGENTS.md 完成，可同步到 README |

---

## 验证结果

| 检查项 | 命令/方式 | 结果 |
|---|---|---|
| 全量单元测试 | `.venv/Scripts/python.exe -m pytest tests/ -q` | **100 passed** |
| 本地 CI 脚本 | `.venv/Scripts/python.exe scripts/run_ci_checks.py` | **通过** |
| 语法检查 | `py_compile` 全量扫描 | **通过** |
| 版本一致性 | 多文件 grep | **1.0.1 一致** |
| 密码加密合规 | 静态审查 | **合规（无内存/持久化明文传播）** |
| Git 索引冲突 | `git status --short` | **仍存 `output/EcoMonitor_v1.0.0_setup.exe` 跟踪冲突** |

---

## 修复优先级建议

1. **P1（建议下一轮发布前处理）**
   - 从 Git 索引中移除 `output/EcoMonitor_v1.0.0_setup.exe`。
   - 修复 `setup.iss` 占位 AppId。
   - 修复 MTU 测试误判。
   - 统一 DSCP 映射。

2. **P2（后续迭代）**
   - SSH 主机密钥确认/已知主机管理。
   - ISAPI HTTPS 优先降级。
   - `.key` ACL、日志根 handler、`crypto.py` 路径统一。
   - OpenGL hiddenimports 与回退 DLL 策略。
   - 下载管理页增量更新与核心流程测试覆盖。

---

*报告生成时间：2026-06-19*  
*第二轮审核基于当前工作区修复后的状态。*
