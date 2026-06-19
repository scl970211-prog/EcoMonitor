# EcoMonitor 第三轮修复审核报告（2026-06-19）

> 本轮依据 `docs/audit-report-v3.md` 的残留问题与建议项进行修复。
> 验证结果：`python -m pytest tests/ -q` → **100 passed**；`scripts/run_ci_checks.py` → **通过**。

---

## 本轮已修复问题

| v3 编号 | 问题 | 关键改动 |
|---|---|---|
| R4 | `output/EcoMonitor_v1.0.0_setup.exe` 仍被 Git 跟踪 | `git rm -f --cached` 并从工作区删除旧版安装包 |
| R6 | `setup.iss` AppId 为占位符 | 替换为新生成的 GUID `{E9CB67BB-060B-4B4E-9A05-A5D9AF69F9CE}` |
| R7 | MTU 测试可能把超时误判为成功 | 明确成功条件：`returncode == 0`；Windows 下若输出含分段提示仍视为失败 |
| R8 | DSCP 映射重复定义 | `packet_capture_tab.py`、`traffic_analysis_tab.py` 统一使用 `src.core.constants.DSCP_NAMES` |
| R1 | SSH 主机密钥策略不安全 | 新增 `_ConfirmHostKeyPolicy`，首次连接时弹窗提示用户确认指纹 |
| R2 | ISAPI/HTTP 明文传输凭据 | `ISAPIClient` 默认先尝试 HTTPS（443），失败再降级到 HTTP 并记录安全警告 |
| R3 | 密钥文件未限制 ACL | `.key` 创建后设置 `0o600`；`crypto.py` 默认路径改为 `get_data_dir() / ".key"` |
| R9 | `logger.py` 清空根 logger handlers | 仅移除本项目添加的 handler，保留 pytest/第三方库 handler |
| R5 | OpenGL 打包隐患 | `build/main.spec` 增加 `PyQt6.QtOpenGL`、`PyQt6.QtOpenGLWidgets` hiddenimports；`post_build_cleanup.py` 保留 `opengl32sw.dll` |

---

## 仍建议后续迭代的问题

| 编号 | 问题 | 文件 | 说明 |
|---|---|---|---|
| S1 | 下载管理页每秒重建行控件 | `src/gui/tabs/download_manager_tab_v2.py:181-206` | P2，建议增量更新以避免内存抖动 |
| S7 | `SDKLoader` 仍使用 `os.chdir` | `src/core/sdk_loader.py:275-276,304` | P2，当前依赖 `os.chdir` 加载 SDK 依赖 DLL；移除前需在真实海康设备环境验证 |
| S3 | 核心下载/扫描流程测试覆盖不足 | `download_worker.py`、`segment_download.py`、`scanner/` | P2 |
| S4 | 安装包代码签名 | `installer/setup.iss` | P2 |

---

## 验证结果

| 检查项 | 命令/方式 | 结果 |
|---|---|---|
| 全量单元测试 | `python -m pytest tests/ -q` | **100 passed** |
| 本地 CI 脚本 | `python scripts/run_ci_checks.py` | **通过** |
| 语法检查 | `py_compile` 覆盖本轮修改文件 | **通过** |
| Git 索引冲突 | `git status --short output/` | **已清除** |

---

*报告生成时间：2026-06-19*
