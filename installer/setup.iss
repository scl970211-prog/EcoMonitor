; Inno Setup 脚本 - EcoMonitor 生态监控平台
; 需要先安装 Inno Setup: https://jrsoftware.org/isinfo.php
; 注意：程序已通过 PyInstaller 自带 VC++ 运行时 DLL，无需额外安装 VC++ Redistributable

#define MyAppName "EcoMonitor 生态监控平台"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "中国水利水电科学研究院"
#define MyAppExeName "EcoMonitor.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EcoMonitor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
OutputDir=..\output
OutputBaseFilename=EcoMonitor_v{#MyAppVersion}_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
; 主程序目录（包含 exe、_internal、sdk、assets）
; 程序已自带 VC++ 运行时 DLL，无需额外分发 vc_redist.x64.exe
Source: "..\dist\EcoMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 此处不再需要静默安装 VC++ Redistributable
; PyInstaller 打包时已将 vcruntime140.dll / msvcp140.dll 等自动包含在 _internal/ 目录中

[Code]
; 安装完成后的可选操作
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    ; 安装完成后的可选操作（如写注册表等）
  end;
end;
