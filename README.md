# EcoMonitor 生态监控平台

一款面向 Windows 的综合视频设备管理与网络运维工具，主要用于管理和运维海康威视（Hikvision）等主流 DVR / NVR / IPC 设备。

> 当前版本：**v1.0.1**

---

## 下载使用

1. 最新安装包请前往 Releases 下载：  
   https://github.com/scl970211-prog/EcoMonitor/releases
2. 下载后直接运行安装向导即可部署；安装过程中可选择是否安装 Npcap。

---

## 功能特性

1. **设备搜索** —— 局域网多协议设备扫描（ARP / Ping / TCP / ONVIF）。
2. **设备连接** —— 登录主流 DVR / NVR / IPC 设备，支持自动重连。
3. **视频预览** —— 多通道实时预览，支持 1 / 4 / 9 / 16 画面布局。
4. **批量下载** —— 录像检索与批量下载，支持段级断点续传。
5. **下载管理** —— 下载任务队列、状态监控、格式转换。
6. **终端调试** —— 内置 SSH / Telnet 设备调试终端。
7. **网络诊断** —— Ping / MTU / 吞吐量测试、IP 冲突检测。
8. **流量分析** —— DSCP 检测与轻量抓包。

---

## 技术栈

- **运行环境**：Python 3.10+
- **GUI 框架**：PyQt6
- **设备 SDK**：海康威视 HCNetSDK / PlayCtrl SDK
- **视频处理**：FFmpeg / FormatConverter
- **网络扫描**：psutil、icmplib
- **终端调试**：paramiko
- **抓包分析**：scapy + Npcap
- **配置安全**：JSON + Fernet 对称加密
- **数据持久化**：SQLite

---

## 系统要求

- **操作系统**：Windows 10 / 11（64 位）
- **Python**：3.10 或更高版本
- **管理员权限**：ARP 扫描、部分网络诊断、抓包功能需要管理员权限
- **Npcap**（可选）：用于流量分析与抓包；使用安装包部署时会自动提示安装

---

## 项目结构

```
EcoMonitor/
├── main.py                 # 程序入口
├── requirements.txt        # Python 依赖
├── README.md               # 本文件
├── LICENSE                 # MIT 许可证
├── assets/                 # 图标、启动画面
│   ├── icon.ico
│   └── splash.png
├── build/                  # PyInstaller 打包配置
│   ├── build.bat
│   ├── main.spec
│   └── post_build_cleanup.py
├── data/                   # 用户数据模板
├── dist/                   # PyInstaller 输出目录
├── docs/                   # 版本更新流程等文档
├── installer/              # Inno Setup 安装脚本
│   ├── redist/
│   └── setup.iss
├── sdk/                    # 设备 SDK 与工具
│   ├── tools/
│   └── win64/
├── src/                    # 源代码
│   ├── core/               # 核心模块
│   ├── gui/                # 图形界面
│   └── utils/              # 工具模块
└── tests/                  # 测试目录
```

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/scl970211-prog/EcoMonitor.git
cd EcoMonitor
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行程序

```bash
python main.py
```

> 建议以管理员身份运行，以保证 ARP 扫描等功能正常工作。

---

## 测试

项目使用 pytest 进行单元测试：

```bash
python -m pytest tests/ -v
```

也可运行本地 CI 检查脚本：

```bash
python scripts/run_ci_checks.py
```

---

## 打包与发布

### 方式一：运行打包脚本（推荐）

```bash
build\build.bat
```

### 方式二：直接调用 PyInstaller

```bash
pyinstaller --clean build/main.spec
```

打包产物位于 `dist/EcoMonitor/`。

### 生成安装程序

使用 Inno Setup 编译安装脚本：

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
```

输出：`output/EcoMonitor_v1.0.1_setup.exe`。

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

**软件开发**：际和（北京）科技有限责任公司    
**技术人员**：孙成龙
