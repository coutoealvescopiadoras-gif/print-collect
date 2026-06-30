#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

#define MyAppName "Print Collect Agent"
#define MyAppPublisher "Print Collect"
#define MyAppExeName "PrintCollectAgent.exe"

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
Source: "..\config.example.yaml"; DestDir: "{app}"; DestName: "config.yaml"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{autoprograms}\Print Collect Agent\Executar agente"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Print Collect Agent\Editar configuracao"; Filename: "notepad.exe"; Parameters: """{app}\config.yaml"""
Name: "{autoprograms}\Print Collect Agent\Abrir pasta"; Filename: "{app}"

[Run]
Filename: "notepad.exe"; Parameters: """{app}\config.yaml"""; Flags: postinstall nowait skipifsilent; Description: "Abrir config.yaml ao concluir"
