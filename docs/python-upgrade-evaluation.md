# EcoMonitor Python 3.10+ 升级评估

**评估日期**：2026-06-19  
**当前环境**：Python 3.8.15（开发 + 运行）  
**目标版本**：Python 3.10+（建议 3.10 或 3.11）  
**评估目标**：分析从 Python 3.8 升级到 3.10+ 的可行性、风险、依赖兼容性、打包影响及推荐步骤。

---

## 1. 升级动机

1. **依赖弃用警告**
   - 当前 `cryptography>=41.0.0` 在 Python 3.8 下会打印：
     ```
     Python 3.8 is no longer supported by the Python core team and support for it is deprecated.
     The next release of cryptography will remove support for Python 3.8.
     ```
   - 未来 `cryptography` 新版本可能直接无法安装，导致安全更新受阻。

2. **官方支持周期**
   - Python 3.8 已于 2024-10 结束官方支持，不再接收安全补丁。
   - Python 3.10 官方支持至 2026-10（进入 security-fix 阶段），3.11 支持至 2027-10。

3. **Qt / 工具链支持**
   - PyQt6 6.4+ 对 Python 3.10/3.11 提供完整 wheel。
   - PyInstaller 6.x 对 3.10/3.11 支持良好。

4. **开发体验**
   - 可使用 `match-case`、更友好的错误信息、`Union` 简写 `|` 等新特性。
   - 当前项目代码尚未使用 3.10 语法，升级不会破坏现有逻辑。

---

## 2. 依赖兼容性检查

### 2.1 生产依赖

| 依赖 | 当前版本 | Python 3.10 | Python 3.11 | 备注 |
|---|---|---|---|---|
| `PyQt6` | `>=6.4.0,<7.0.0` | ✅ | ✅ | 官方支持 |
| `PyQt6-Qt6` | `>=6.4.0,<7.0.0` | ✅ | ✅ | 官方支持 |
| `psutil` | `>=5.9.0,<6.0.0` | ✅ | ✅ | 提供 wheel |
| `icmplib` | `>=3.0.0,<4.0.0` | ✅ | ✅ | 纯 Python |
| `paramiko` | `>=3.4.0,<4.0.0` | ✅ | ✅ | 提供 wheel |
| `scapy` | `>=2.5.0,<3.0.0` | ✅ | ✅ | 提供 wheel |
| `numpy` | `>=1.24.0,<2.0.0` | ✅ | ✅ | 提供 wheel |
| `cryptography` | `>=41.0.0,<44.0.0` | ✅ | ✅ | 推荐 42+ |
| `requests` | `>=2.31.0,<3.0.0` | ✅ | ✅ | 纯 Python |

### 2.2 开发 / 构建依赖

| 依赖 | 当前情况 | Python 3.10 | Python 3.11 | 备注 |
|---|---|---|---|---|
| `pytest` | 已使用 | ✅ | ✅ | 无问题 |
| `pytest-qt` | 已配置 dev | ✅ | ✅ | 无问题 |
| `black` | 已配置 dev | ✅ | ✅ | 无问题 |
| `ruff` | 已配置 dev | ✅ | ✅ | 无问题 |
| `mypy` | 已配置 dev | ✅ | ✅ | 无问题 |
| `PyInstaller` | 全局 6.19.0 | ✅ | ✅ | 需确认目标环境版本 |

> 全局 `PyInstaller 6.19.0` 支持 Python 3.8–3.12，升级后无需更新 PyInstaller 版本。

### 2.3 结论

**所有声明依赖均支持 Python 3.10 和 3.11。** 升级本身不会引入依赖兼容性问题。

---

## 3. 升级风险分析

### 3.1 高风险项

| 风险 | 说明 | 缓解措施 |
|---|---|---|
| **打包产物体积变化** | Python 3.10/3.11 的运行时和标准库模块与 3.8 不同，`main.spec` 的 `excludes` 列表可能需要调整 | 升级后重新打包，对比 `_internal/` 体积，必要时补充/移除 excludes |
| **hiddenimports 遗漏** | 不同 Python 版本下，PyInstaller 对动态导入的检测行为可能不同 | 在 3.10 上跑 `--clean` 打包并运行完整功能 checklist |
| **海康 SDK DLL 兼容性** | SDK 通过 `ctypes.WinDLL` 加载，与 Python 版本无关，但打包后运行时路径可能变化 | 升级后验证 `HCNetSDK.dll` 能被正确加载 |
| **Npcap / scapy 在 3.10+ 上的行为** | scapy 对 Windows/Python 版本较敏感 | 升级后运行抓包/流量分析功能 |

### 3.2 中风险项

| 风险 | 说明 | 缓解措施 |
|---|---|---|
| **代码中可能存在的 3.8 特定写法** | 项目目前使用 `typing.Optional`、`typing.Dict` 等，3.10 仍兼容；但 `collections.abc` 等迁移需检查 | 使用 `ruff --target-version py310` 扫描 |
| **mypy / black target-version** | `pyproject.toml` 中 `target-version` 仍为 `py38` | 升级后改为 `py310` 并重新格式化/检查 |
| **CI 运行时间** | GitHub Actions 的 `windows-latest` 上 Python 3.10 安装和依赖下载时间可能不同 | 已配置 3.8/3.10 矩阵，观察即可 |

### 3.3 低风险项

- **语法兼容性**：当前代码未使用 3.10+ 特有语法，反向兼容无问题。
- **配置文件**：`config.json` 格式与 Python 版本无关。
- **SQLite 数据库**：与 Python 版本无关。

---

## 4. 推荐升级策略

### 4.1 策略选择

| 策略 | 做法 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|---|
| **A. 激进升级（推荐）** | 开发、CI、打包环境统一切换到 Python 3.10；`pyproject.toml` 最低版本改为 `>=3.10` | 统一环境、消除弃用警告、简化配置 | 需要所有协作者升级 Python | ⭐⭐⭐⭐⭐ |
| **B. 保守兼容** | 代码保持 3.8 兼容，CI 同时跑 3.8 和 3.10；打包使用 3.10 | 兼容旧开发环境 | 无法使用 3.10 新特性，维护两套 CI 配置 | ⭐⭐⭐ |
| **C. 等待 3.11** | 直接升级到 3.11 | 获得更长支持周期 | 测试覆盖不足，风险略高 | ⭐⭐⭐ |

**推荐策略 A：直接升级到 Python 3.10。**

理由：
- Python 3.10 是成熟的 LTS 后版本，生态完全支持。
- 与 3.11 相比，3.10 的 PyInstaller / Qt 经验更丰富，风险更低。
- 项目当前没有依赖 3.8 的特定环境，升级成本低。

### 4.2 推荐升级步骤

#### 步骤 1：准备新 Python 环境

1. 在构建机和开发机上安装 Python 3.10.x（推荐 3.10.11）。
2. 创建新虚拟环境：
   ```bash
   python3.10 -m venv .venv310
   .venv310\Scripts\activate
   pip install -r requirements.txt
   pip install -e .[dev]
   ```

#### 步骤 2：更新项目配置

1. `pyproject.toml`：
   ```toml
   requires-python = ">=3.10"
   ```
2. `pyproject.toml` 工具版本：
   ```toml
   [tool.black]
   target-version = ['py310']

   [tool.ruff]
   target-version = "py310"

   [tool.mypy]
   python_version = "3.10"
   ```
3. `AGENTS.md` 中更新 Python 版本说明。

#### 步骤 3：代码检查

```bash
ruff check src --target-version py310
mypy src
black --check src
```

修复所有新增警告（主要是 `UP` 规则推荐的现代写法）。

#### 步骤 4：运行测试

```bash
python scripts/run_ci_checks.py
```

确认 79 个用例全部通过。

#### 步骤 5：重新打包验证

```bash
build\build.bat
```

打包完成后：
1. 检查 `dist/EcoMonitor/_internal/` 下 `numpy` 是否存在（P0 修复项）。
2. 启动 `dist/EcoMonitor/EcoMonitor.exe`，运行完整功能 checklist：
   - 登录设备
   - 视频预览
   - 录像下载
   - 网络测速
   - IP 冲突检测
   - 流量分析 / 抓包
   - 终端调试

#### 步骤 6：更新 CI

当前 `.github/workflows/ci.yml` 已包含 3.8 和 3.10 矩阵。升级后：
- 将 `3.8` 从矩阵中移除，仅保留 `3.10`（或保留 `3.10` + `3.11` 矩阵）。
- 如有必要，增加一个 `build` job，用 3.10 打包并检查产物启动。

#### 步骤 7：发布说明

在版本更新日志中注明：
- 最低运行/开发环境从 Python 3.8 提升到 Python 3.10。
- 安装包不再支持 Windows 7/8（Python 3.10 官方不支持 Windows 7）。

---

## 5. 关键注意事项

### 5.1 Windows 7 支持

- Python 3.10 官方不支持 Windows 7。
- 如果目标用户仍在使用 Windows 7，升级将意味着安装包无法运行。
- **建议**：确认用户机器最低 Windows 版本。若需支持 Windows 7，只能继续维护 Python 3.8 分支或延迟升级。

### 5.2 虚拟环境切换

- 当前项目 `.venv` 基于 Python 3.8，升级后需要删除并重建：
  ```bash
  rm -rf .venv
  python3.10 -m venv .venv
  pip install -r requirements.txt
  ```
- `scripts/run_ci_checks.py` 会自动检测 `.venv/Scripts/python.exe`，升级后无影响。

### 5.3 PyInstaller 路径

- `build/build.bat` 直接调用 `pyinstaller`，使用的是 PATH 中的 PyInstaller。
- 升级后确保 PATH 指向 Python 3.10 的 Scripts 目录，或在 `build.bat` 中显式指定解释器：
  ```bat
  .venv\Scripts\pyinstaller --clean build\main.spec
  ```

### 5.4 类型注解现代化（可选）

- Python 3.10 支持 `X | Y` 替代 `Union[X, Y]`、`list[int]` 替代 `List[int]`。
- 不建议在升级时一次性全改，可在后续重构中逐步使用 `ruff UP` 规则自动迁移。

---

## 6. 回滚方案

如果升级后发现严重问题：

1. 保留 Python 3.8 的 `.venv38` 虚拟环境作为备份。
2. 在 Git 中保留升级前的 `release/v1.0.x` 分支。
3. `pyproject.toml` 的 `requires-python` 可快速改回 `>=3.8`。
4. CI 矩阵可临时加回 3.8。

---

## 7. 结论

- **技术上完全可行**：所有依赖均支持 Python 3.10+，代码无需大量修改。
- **推荐升级到 Python 3.10**：可消除 `cryptography` 弃用警告，获得更长的安全支持周期。
- **主要风险在打包与目标系统**：需要在 Python 3.10 上完整跑一遍 PyInstaller 打包和功能 checklist。
- **实施成本**：约 **1 人天**（环境重建 + 配置更新 + 打包验证）。

**建议**：在当前版本稳定后，单独安排一次 Python 3.10 升级专项，不要与功能开发并行，以便出问题可快速回滚。

---

*评估结束。*
