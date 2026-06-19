# EcoMonitor 生态监控平台

一款综合性的视频设备管理与网络运维工具，支持设备发现、视频预览、录像下载、网络诊断等功能。

## 下载使用

1. 最新安装包请前往 Releases 下载。
2. 直接下载链接：https://github.com/scl970211-prog/EcoMonitor/releases


## 功能特性

1. **设备发现** - 局域网多协议设备扫描（ARP / Ping / TCP / ONVIF）
2. **设备连接** - 支持主流 DVR / NVR / IPC 设备登录管理
3. **视频预览** - 多通道实时预览，支持 1/4/9/16 画面布局
4. **录像下载** - 批量录像检索与下载，支持段级断点续传
5. **下载管理** - 下载任务管理、状态监控、格式转换
6. **终端调试** - 内置 SSH / Telnet 设备调试终端
7. **网络诊断** - Ping / MTU / 吞吐量测试、IP 冲突检测
8. **流量分析** - DSCP 检测与轻量抓包

## 技术栈

- Python 3.10+
- PyQt6
- HCNetSDK / PlayCtrl SDK
- FFmpeg

## 项目结构

```
EcoMonitor/
├── main.py              # 程序入口
├── requirements.txt     # Python 依赖
├── assets/              # 图标、启动画面
├── build/               # PyInstaller 打包配置
│   ├── main.spec
│   ├── build.bat
│   └── post_build_cleanup.py
├── installer/           # Inno Setup 安装脚本
│   └── setup.iss
├── sdk/                 # 设备 SDK（DLL）
│   ├── win64/
│   └── tools/
├── src/                 # 源代码
│   ├── core/            # 核心模块（SDK 封装、设备管理、下载）
│   ├── gui/             # GUI 模块（主窗口、标签页、控件）
│   └── utils/           # 工具模块（配置、加密、日志）
├── tests/               # 测试
└── data/                # 用户数据（运行时生成）
```

## 环境准备

1. 安装 Python 3.10+
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. （可选）安装 Npcap，用于流量分析功能：
   https://npcap.com/#download

## 运行程序

```bash
python main.py
```

> Windows 系统建议以管理员身份运行，以确保 ARP 扫描等功能正常工作。

## 打包发布

```bash
pyinstaller build/main.spec
```

打包完成后，使用 Inno Setup 编译 `installer/setup.iss` 生成安装程序。

## 许可证

[MIT License](LICENSE)

---

**软件开发**：际和（北京）科技有限责任公司
**技术人员**：孙成龙
