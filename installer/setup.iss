; Inno Setup 脚本 - EcoMonitor 生态监控平台
; 需要先安装 Inno Setup: https://jrsoftware.org/isinfo.php
; 注意：程序已通过 PyInstaller 自带 VC++ 运行时 DLL，无需额外安装 VC++ Redistributable

#define MyAppName "EcoMonitor 生态监控平台"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "中国水利水电科学研究院"
#define MyAppExeName "EcoMonitor.exe"
#define NpcapVersion "1.88"
#define NpcapExe "npcap-" + NpcapVersion + ".exe"

[Setup]
AppId={{E9CB67BB-060B-4B4E-9A05-A5D9AF69F9CE}}
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
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile="..\assets\icon.ico"
UninstallDisplayIcon="{app}\{#MyAppExeName}"

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
InstallNpcapTask=安装 Npcap 抓包驱动（推荐，流量分析/抓包功能需要）

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked
Name: "installnpcap"; Description: "{cm:InstallNpcapTask}"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 主程序目录（包含 exe、_internal、sdk、assets）
; 程序已自带 VC++ 运行时 DLL，无需额外分发 vc_redist.x64.exe
Source: "..\dist\EcoMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
; Npcap 安装包（流量分析/抓包功能需要）
Source: "redist\{#NpcapExe}"; DestDir: "{app}\redist"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 此处不再需要静默安装 VC++ Redistributable
; PyInstaller 打包时已将 vcruntime140.dll / msvcp140.dll 等自动包含在 _internal/ 目录中
; 仅在用户选择且系统未检测到 Npcap 时，才启动 Npcap 安装程序（图形界面，按提示完成）
Filename: "{app}\redist\{#NpcapExe}"; \
  Parameters: "/winpcap_mode=no"; \
  WorkingDir: "{app}\redist"; \
  StatusMsg: "正在启动 Npcap {#NpcapVersion} 安装程序，请按提示完成安装..."; \
  Description: "{cm:InstallNpcapTask}"; \
  Flags: waituntilidle runascurrentuser skipifdoesntexist; \
  Tasks: installnpcap; \
  Check: NeedInstallNpcap

[Code]
function NpcapInstalled: Boolean;
begin
  Result :=
    RegKeyExists(HKLM32, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\NpcapInst') or
    RegKeyExists(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\NpcapInst') or
    RegKeyExists(HKLM32, 'SOFTWARE\Npcap') or
    RegKeyExists(HKLM64, 'SOFTWARE\Npcap');
end;

function NeedInstallNpcap: Boolean;
begin
  Result := WizardIsTaskSelected('installnpcap') and not NpcapInstalled;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  I: Integer;
  Caption: String;
begin
  if CurPageID = wpSelectTasks then
  begin
    Caption := ExpandConstant('{cm:InstallNpcapTask}');
    if NpcapInstalled then
    begin
      for I := 0 to WizardForm.TasksList.Items.Count - 1 do
      begin
        if WizardForm.TasksList.ItemCaption[I] = Caption then
          WizardForm.TasksList.Checked[I] := False;
      end;
    end;
  end;
end;
