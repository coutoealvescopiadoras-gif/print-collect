#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

#define MyAppName "Print Collect Agent"
#define MyAppPublisher "Print Collect"
#define MyAppExeName "PrintCollectAgent.exe"
#define MyAppTaskName "Print Collect Agent"

[Setup]
AppId={{8D1A4508-4C10-4654-85E1-3A4D7DB23F5A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PrintCollect
DefaultGroupName={#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
OutputDir=..\dist\windows
OutputBaseFilename=PrintCollectSetup
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\windows\PrintCollectAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.yaml"; DestDir: "{app}"; DestName: "config.example.yaml"; Flags: ignoreversion
Source: ".\runtime\*.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{src}\config.yaml"; DestDir: "{app}"; DestName: "config.yaml"; Flags: external ignoreversion onlyifdoesntexist; Check: HasExternalConfig

[Icons]
Name: "{autoprograms}\Print Collect Agent\Testar conexao"; Filename: "{app}\test-agent.bat"
Name: "{autoprograms}\Print Collect Agent\Executar coleta unica"; Filename: "{app}\run-once.bat"
Name: "{autoprograms}\Print Collect Agent\Editar configuracao"; Filename: "{app}\open-config.bat"
Name: "{autoprograms}\Print Collect Agent\Abrir pasta"; Filename: "{app}"

[Run]
Filename: "{app}\register-startup-task.bat"; Flags: runhidden waituntilterminated; StatusMsg: "Configurando inicializacao automatica..."
Filename: "notepad.exe"; Parameters: """{app}\config.yaml"""; Flags: postinstall nowait skipifsilent; Description: "Abrir config.yaml ao concluir"

[UninstallRun]
Filename: "{app}\unregister-startup-task.bat"; Flags: runhidden skipifdoesntexist

[Code]
function HasExternalConfig: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\config.yaml'));
end;
