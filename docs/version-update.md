# 版本更新步骤

这个文档说明了项目后续发布新版本时的标准流程。

## 1. 新版本分支

在本地创建一个新分支，用于开发和测试本次发布：

```powershell
cd "D:\生态监控平台 - 综合视频设备管理与网络运维工具\EcoMonitor"
git checkout -b release/v1.0.1
```

## 2. 修改代码与更新版本号

1. 在源码中完成功能改动或 Bug 修复。
2. 更新版本号：
   - `installer/setup.iss` 中的 `MyAppVersion`
   - 如果有其它版本常量或说明文档，也同步更新。
3. 提交改动：

```powershell
git add .
git commit -m "Release v1.0.1"
```

## 3. 合并到 `main`

确认版本代码稳定后，把发布分支合并到 `main`：

```powershell
git checkout main
git merge release/v1.0.1
```

## 4. 本地打包

运行打包脚本，生成 PyInstaller 的发布目录：

```powershell
cd "D:\生态监控平台 - 综合视频设备管理与网络运维工具\EcoMonitor"
.\build\build.bat
```

如果打包成功，它会生成 `dist\EcoMonitor\` 或 `build\dist\EcoMonitor\` 目录。

## 5. 生成安装程序

使用 Inno Setup 编译 `installer/setup.iss`：

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "D:\生态监控平台 - 综合视频设备管理与网络运维工具\EcoMonitor\installer\setup.iss"
```

最终会生成：

```text
output\EcoMonitor_v1.0.1_setup.exe
```

## 6. 发布 GitHub Release

1. 打开仓库页面 `Releases`
2. 点击 `Draft a new release`
3. 填写：
   - Tag version：`v1.0.1`
   - Release title：`EcoMonitor v1.0.1`
   - Release notes：本次更新内容、修复与改进
4. 上传生成的安装包和其他资产
5. 发布 Release

## 7. 清理与后续

发布完成后，建议删除临时分支：

```powershell
git branch -d release/v1.0.1
```

如果你希望长期维护版本控制策略，还可以按照以下分支规则：

- `feature/*`：开发功能
- `bugfix/*`：修复问题
- `release/*`：打包发布
- `main`：稳定发布分支
