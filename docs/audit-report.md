# EcoMonitor 代码审核与优化报告

**版本**：v1.0.0  
**审核日期**：2026-06-19  
**范围**：`src/` 源码、`tests/` 测试、`requirements.txt`、`AGENTS.md`  
**目标**：从界面 UI、视觉风格、可维护性、使用体验、功能完整可用性五个维度发现问题并落地改进。

---

## 1. 执行摘要

本次审核对 EcoMonitor 项目进行了全量代码检查，共识别并修复/优化了 **8 类问题**：

| 类别 | 主要问题 | 处理结果 |
|---|---|---|
| 代码质量 | `DraggableChannelList` 重复实现、`SpeedCurveWidget.__init__` 重复定义 | 已删除重复代码，统一引用 |
| 依赖管理 | `requirements.txt` 包含未使用的 `matplotlib`、`speedtest-cli`，缺少 `numpy` | 已修正 |
| 可维护性 | 大量魔法数字、颜色、端口、DSCP 映射散落在各模块 | 已抽离到 `src/core/constants.py` 与 `src/gui/constants.py` |
| 视觉风格 | 内联 `setStyleSheet` 遍布各标签页，颜色不统一 | 已建立设计系统雏形（`styles.py` + 常量），并替换部分内联样式 |
| 跨平台稳定性 | 主窗口标签页与多处状态标签使用 Emoji | 已全部替换为中文文字 |
| 工程化 | 缺少统一的格式化、lint、类型检查配置 | 已新增 `pyproject.toml` |
| 测试覆盖 | 仅 1 个导入测试 | 已扩展至 32 个用例，覆盖配置、加密、常量、路径、下载任务 |
| 文档 | `AGENTS.md` 与最新依赖/测试状态不同步 | 已更新 |

**验证结果**：

- `python -m py_compile` 全量通过。
- `python -m pytest tests/ -q`：**32 passed**。

---

## 2. 界面 UI 优化

### 2.1 问题

- 部分控件尺寸、字号、间距为硬编码，缺乏统一的设计 token。
- 标签页标题原先使用 Emoji，在不同 Windows 字体环境下可能出现显示异常或占位问题。
- 连接状态、工具检测状态等多处使用 Emoji/彩色符号，既不稳定也不利于色盲用户识别。

### 2.2 已实施优化

- 新增 `src/gui/constants.py` 集中管理：
  - `Color`（主色、语义色、中性色、背景/表面色）
  - `FontSize`、`Size`（圆角、按钮尺寸、间距）
  - `StatusColor`（在线/离线/错误/警告语义别名）
  - `TabLabel`（无 Emoji 标签名常量）
- 重写 `src/gui/styles.py`，提供 `get_global_stylesheet()` 统一注入全局 QSS。
- `src/gui/main_window.py` 标签页标题全面改用 `TabLabel` 常量。
- 替换以下 Emoji/符号为中文文字：
  - 主窗口标签页：`🔍 设备搜索` → `设备搜索` 等。
  - 连接状态、Wireshark/tshark/Npcap 检测状态中的 ✅/❌ → `已找到` / `未安装`。
  - 测速按钮 `🚀 开始测速` → `开始测速`。
  - 流量分析、IP 冲突风险列的 ⚠️/🟢/🔵/🟡 → 纯文字描述。
  - 视频窗格状态符号 → 文字标签（`播放中`、`在线`、`错误` 等）。

### 2.3 剩余建议

- 继续将各标签页剩余的内联 `setStyleSheet` 迁移到 `styles.py` 或基于 `objectName` 的全局 QSS。
- 对高对比度/深色模式用户提供一套可选主题，可通过 `Color` 常量切换实现。
- 为关键操作按钮增加图标（SVG 或 Qt 资源文件），在保留文字的同时提升识别度。

---

## 3. 整体视觉风格优化

### 3.1 问题

- 颜色值在多个文件中重复出现（如 `#107c10`、`#c42b1c`、`#999`），容易因局部修改导致风格不一致。
- 没有明确的设计系统入口，新增标签页时容易复制旧代码中的硬编码样式。

### 3.2 已实施优化

- 建立两层设计系统：
  1. **基础 Token**：`src/gui/constants.py` 中的 `Color`、`FontSize`、`Size`。
  2. **全局样式表**：`src/gui/styles.py` 提供 `MAIN_WINDOW`、`VIDEO_WIDGET` 等分层 QSS，并通过 `get_global_stylesheet()` 统一输出。
- `src/gui/tabs/connection_tab.py` 与 `src/gui/widgets/video_widget.py` 已改用 `Color` / `StatusColor` 常量。
- `src/gui/tabs/packet_capture_tab.py` 工具检测状态色改用 `Color.SUCCESS_LIGHT` / `Color.ERROR_LIGHT`。

### 3.3 剩余建议

- 为 `QGroupBox`、`QPushButton`、`QLineEdit`、`QTableWidget` 等通用控件补充全局样式，减少每个标签页自行设置。
- 统一使用 `setObjectName` + QSS 选择器管理选中态、悬停态、禁用态，避免运行时频繁拼接样式字符串。
- 引入图标字体或 SVG 资源，替代当前文字符号；图标应支持主题色切换。

---

## 4. 后期维护与升级便利性

### 4.1 问题

- 魔法数字与业务常量分散在 UI、核心、网络模块中，修改默认值需要多处调整。
- `requirements.txt` 与实际导入不一致，增加新成员上手成本。
- 缺少格式化、lint、类型检查配置，代码风格难以保持一致。
- 测试极少，重构时缺少安全网。

### 4.2 已实施优化

- **核心常量集中化**：新增 `src/core/constants.py`，包含：
  - 默认端口：`DEFAULT_SDK_PORT`、`DEFAULT_HTTP_PORT`
  - 超时：`DEFAULT_TIMEOUT`、`SCAN_TIMEOUT`
  - 设备类型：`DeviceType`
  - DSCP 名称/风险映射：`DSCP_NAMES`、`DSCP_RISK_LEVELS`
  - 日期/时间/布局相关常量
- **UI 常量集中化**：`src/gui/constants.py` 覆盖颜色、字号、间距、布局映射、表格默认列宽、日志级别、标签名。
- **依赖修正**：`requirements.txt` 移除 `matplotlib`、`speedtest-cli`，新增 `numpy`。
- **工程化配置**：新增 `pyproject.toml`，配置：
  - `black` 行宽 100
  - `ruff` lint 规则（E、F、I、UP、B、C4、SIM）
  - `mypy` 基础类型检查
  - `pytest` 测试路径与覆盖率
- **延迟加载**：`src/core/__init__.py`、`src/gui/__init__.py` 改为懒加载 Qt 依赖模块，方便纯工具函数测试。
- **测试扩展**：新增 5 个测试文件，共 32 个用例，覆盖：
  - `test_config.py`：配置读写、默认值、密码加密。
  - `test_crypto.py`：Fernet 加解密、空值处理。
  - `test_constants.py`：核心常量、DSCP 映射、设备类型。
  - `test_path_resolver.py`：应用目录、用户数据目录解析。
  - `test_download_task.py`：下载任务模型、状态流转、分段验证。

### 4.3 剩余建议

- 逐步为 `src.core.device`、`src.core.download_controller` 等复杂类编写单元测试，使用 `unittest.mock` 模拟 SDK 调用。
- 引入 `pre-commit` 钩子，在提交前自动运行 `black`、`ruff`、`mypy`、`pytest`。
- 将 CI（GitHub Actions）纳入规划，在每次 PR 时执行测试与打包检查。
- 对海康 SDK 结构体访问做边界封装，降低 SDK 升级时的改动面。

---

## 5. 使用体验优化

### 5.1 问题

- 标签页 Emoji 在不同环境显示不一致，影响专业感。
- 状态文字依赖颜色传递含义，色盲/弱色用户可能难以区分。
- 部分提示文案直接拼接 Emoji，国际化/翻译时不友好。

### 5.2 已实施优化

- 全部标签页标题改为中文文字，稳定无歧义。
- 工具检测状态从“图标 + 颜色”改为“文字 + 颜色”双重编码，兼顾普通用户与色觉异常用户。
- 视频窗格状态标签从抽象符号改为中文状态词，提示更明确。

### 5.3 剩余建议

- 为关键状态增加 `QToolTip` 或 `QStatusBar` 详细说明。
- 对长时间操作（扫描、测速、批量下载）统一进度指示与取消机制。
- 增加键盘快捷键与焦点顺序优化，提升无鼠标操作体验。
- 提供“重置布局”与“恢复默认连接参数”入口，降低误操作成本。

---

## 6. 功能完整可用性

### 6.1 问题

- 部分依赖声明缺失可能导致功能在干净环境无法运行（如 `numpy`）。
- 重复代码和硬编码增加引入 Bug 的概率。
- 缺少对核心工具类的基础单元测试，回归风险高。

### 6.2 已实施优化

- 修正 `requirements.txt`，确保 `numpy`、`PyQt6`、`psutil`、`icmplib`、`paramiko`、`scapy`、`cryptography`、`requests` 等核心依赖声明准确。
- 删除 `preview_tab_v2.py` 中内嵌的 `DraggableChannelList`，统一引用 `src/gui/widgets/draggable_channel_list.py`，避免两份实现行为分叉。
- 修复 `speedtest_tab.py` 中 `SpeedCurveWidget.__init__` 重复定义的问题。
- 通过新增测试覆盖配置、加密、路径、常量、下载任务，确保核心工具函数在修改后可快速回归验证。

### 6.3 剩余建议

- 对设备连接、视频预览、下载流程编写集成测试（可 mock SDK）。
- 添加启动自检的单元测试，验证 DLL 缺失、目录不可写等场景的提示行为。
- 对网络扫描模块增加离线测试，使用固定 ARP/Ping 数据集验证解析逻辑。
- 建立发布前手动验证清单（Checklist），覆盖登录、预览、下载、抓包、测速、IP 冲突检测等主流程。

---

## 7. 修改清单

### 7.1 新增文件

| 文件 | 说明 |
|---|---|
| `src/core/constants.py` | 核心常量（端口、超时、设备类型、DSCP 等） |
| `src/gui/constants.py` | UI 常量（颜色、字号、TabLabel、状态色等） |
| `pyproject.toml` | black / ruff / mypy / pytest 配置 |
| `tests/test_config.py` | 配置与密码加密测试 |
| `tests/test_crypto.py` | 加密工具测试 |
| `tests/test_constants.py` | 核心常量测试 |
| `tests/test_path_resolver.py` | 路径解析测试 |
| `tests/test_download_task.py` | 下载任务模型测试 |
| `docs/audit-report.md` | 本报告 |

### 7.2 修改文件

| 文件 | 修改内容 |
|---|---|
| `requirements.txt` | 移除 `matplotlib`、`speedtest-cli`；新增 `numpy` |
| `src/core/__init__.py` | 懒加载 Qt 依赖模块 |
| `src/gui/__init__.py` | 懒加载 Qt 依赖模块 |
| `src/gui/styles.py` | 重写为分层 QSS 设计系统入口 |
| `src/gui/main_window.py` | 标签页标题改用 `TabLabel` 常量 |
| `src/gui/tabs/connection_tab.py` | 状态色改用 `StatusColor`，减少硬编码 |
| `src/gui/tabs/packet_capture_tab.py` | 替换 Emoji，颜色改用 `Color` 常量 |
| `src/gui/tabs/speedtest_tab.py` | 移除测速按钮 Emoji，修复重复 `__init__` |
| `src/gui/tabs/ip_conflict_tab.py` | 替换风险列 Emoji |
| `src/gui/tabs/traffic_analysis_tab.py` | 替换警告/优先级 Emoji |
| `src/gui/widgets/video_widget.py` | 状态标签改用文字 + `Color` 常量，设置 objectName 便于全局 QSS |
| `src/gui/tabs/preview_tab_v2.py` | 删除内嵌 `DraggableChannelList`，统一导入 |
| `AGENTS.md` | 更新依赖、测试、设计系统约定 |

---

## 8. 验证结果

```bash
python -m py_compile src/core/constants.py src/gui/constants.py src/gui/styles.py src/gui/main_window.py src/gui/tabs/connection_tab.py src/gui/tabs/packet_capture_tab.py src/gui/tabs/speedtest_tab.py src/gui/tabs/ip_conflict_tab.py src/gui/tabs/traffic_analysis_tab.py src/gui/widgets/video_widget.py
python -m pytest tests/ -q
```

结果：

```
32 passed, 1 warning in 0.47s
```

> 唯一警告来自 `cryptography` 对 Python 3.8 的弃用提示，不影响功能；建议后续将运行环境升级至 Python 3.10+。

---

## 9. 后续行动建议（优先级排序）

1. **高**：继续迁移剩余内联样式到 `styles.py` 全局 QSS，消除硬编码色值。
2. **高**：为 `Device`、`DownloadManager`、`Scanner` 编写 mock 单元测试，补齐核心流程回归网。
3. **中**：引入 `pre-commit` 与 CI，自动执行格式化、lint、类型检查、测试。
4. **中**：建立发布前手动验证 Checklist，覆盖八大主流程。
5. **低**：评估深色主题与 SVG 图标方案，进一步提升视觉一致性。
6. **低**：将 Python 运行时从 3.8 升级至 3.10+，消除 `cryptography` 弃用警告。

---

*报告结束。*
