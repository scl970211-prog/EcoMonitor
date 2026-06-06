@echo off
chcp 65001 >nul
echo ============================================
echo  EcoMonitor 生态监控平台 - 打包脚本
echo ============================================
echo.

REM 检查 pyinstaller
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 pyinstaller，请先安装：
    echo   pip install pyinstaller
    exit /b 1
)

REM 清理旧构建
if exist "dist" rmdir /s /q "dist"
if exist "build\build" rmdir /s /q "build\build"

REM 执行打包
echo [1/4] 正在分析依赖并打包...
pyinstaller --clean "%~dp0main.spec"
if errorlevel 1 (
    echo [错误] 打包失败，请检查上方日志。
    exit /b 1
)

REM 检查结果
set "OUTPUT_DIR=%~dp0..\dist\EcoMonitor"
if not exist "%OUTPUT_DIR%\EcoMonitor.exe" (
    echo [错误] 未找到生成的 exe，请检查 dist 目录结构。
    exit /b 1
)

echo [2/4] 打包完成，执行清理优化...
python "%~dp0post_build_cleanup.py" "%OUTPUT_DIR%"

echo [3/4] 检查最终输出...
for /f %%a in ('powershell -NoProfile -Command "(Get-ChildItem '%OUTPUT_DIR%' -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB"') do (
    echo 输出目录大小: %%a MB
)

echo [4/4] 全部完成！
echo 输出目录: %OUTPUT_DIR%
echo.
echo 下一步：将 installer\redist\vc_redist.x64.exe 准备好后，
echo         运行 Inno Setup 编译 installer\setup.iss
echo.
pause
