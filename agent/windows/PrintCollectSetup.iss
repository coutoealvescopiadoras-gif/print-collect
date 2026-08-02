#ifndef MyAppVersion
  #define MyAppVersion "0.3.0"
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
DisableDirPage=no
DisableProgramGroupPage=no
PrivilegesRequired=admin
Compression=lzma
SolidCompression=yes
; IMPORTANTE: Antes = ArchitecturesInstallIn64BitMode=x64compatible (forcava so 64 bits!)
; Para INSTALAR EM QUALQUER WINDOWS (32 ou 64 bits), NAO forcar 64-bit mode:
; geramos o PrintCollectAgent.exe em 32 bits, que roda sempre via WOW64.
ArchitecturesInstallIn64BitMode=
ArchitecturesAllowed=x64compatible arm64 x86compatible
WizardStyle=modern
OutputDir=..\dist\windows
OutputBaseFilename=PrintCollectSetup
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\PrintCollectAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WizardPareamento.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\SearchPrinters.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.yaml"; DestDir: "{app}"; DestName: "config.example.yaml"; Flags: ignoreversion
; === IMPORTANTE: config.yaml NAO fica mais em {app} (Program Files = somente leitura UAC).
; === Agora fica em {commonappdata}\PrintCollect\ = C:\ProgramData\PrintCollect\ (gravavel SEM admin!)
Source: "..\config.example.yaml"; DestDir: "{commonappdata}\PrintCollect"; DestName: "config.yaml"; Flags: ignoreversion onlyifdoesntexist; Check: not HasExternalConfig
Source: ".\runtime\*.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{src}\config.yaml"; DestDir: "{commonappdata}\PrintCollect"; DestName: "config.yaml"; Flags: external ignoreversion onlyifdoesntexist; Check: HasExternalConfig

[Dirs]
; Garante que a pasta C:\ProgramData\PrintCollect exista antes de qualquer coisa
Name: "{commonappdata}\PrintCollect"; Permissions: authusers-modify; Flags: uninsneveruninstall

[Icons]
; === WIZARD NATIVO: atalhos apontam para WizardPareamento.exe (NAO E .bat! EXE NATIVO!) ===
; (NAO usa cmd.exe, NAO usa aspas, NAO da erro de aspas / fechar sozinho! Abre SEMPRE!)
Name: "{autoprograms}\Print Collect Agent\1. Parear Agora (Wizard)"; Filename: "{app}\WizardPareamento.exe"; IconFilename: "{app}\WizardPareamento.exe"
Name: "{autoprograms}\Print Collect Agent\Wizard de pareamento"; Filename: "{app}\WizardPareamento.exe"; IconFilename: "{app}\WizardPareamento.exe"
; === PROCURAR IMPRESSORAS: EXE NATIVO SearchPrinters.exe (nao fecha sozinho!) ===
Name: "{autoprograms}\Print Collect Agent\Procurar impressoras"; Filename: "{app}\SearchPrinters.exe"; IconFilename: "{app}\SearchPrinters.exe"
Name: "{autoprograms}\Print Collect Agent\Testar conexao"; Filename: "{app}\test-agent.bat"
Name: "{autoprograms}\Print Collect Agent\Executar coleta unica"; Filename: "{app}\run-once.bat"
Name: "{autoprograms}\Print Collect Agent\Editar configuracao"; Filename: "{app}\open-config.bat"
Name: "{autoprograms}\Print Collect Agent\Reinstalar inicializacao"; Filename: "{app}\register-startup-task.bat"
Name: "{autoprograms}\Print Collect Agent\Desinstalar inicializacao"; Filename: "{app}\unregister-startup-task.bat"
Name: "{autoprograms}\Print Collect Agent\Abrir pasta"; Filename: "{app}"
Name: "{autodesktop}\Print Collect - Wizard"; Filename: "{app}\WizardPareamento.exe"; IconFilename: "{app}\WizardPareamento.exe"; Tasks: desktopicon

[Run]
; === WIZARD NATIVO: Chama WizardPareamento.exe DIRETAMENTE (0 .bat, 0 cmd.exe!) ===
; (Abre a janela preta SEMPRE, sem bug de fechar sozinho, sem aspas.)
; Sem flag unchecked = vem MARCADO POR PADRAO na ultima tela do setup! Todo mundo clica Finish e abre!
Filename: "{app}\WizardPareamento.exe"; \
  WorkingDir: "{app}"; \
  Description: "Executar Wizard de Pareamento (vincular agente ao cliente — RECOMENDADO)"; \
  Flags: nowait postinstall skipifsilent
Filename: "{app}\list-printers.bat"; \
  Description: "Procurar impressoras na rede do cliente (primeira busca)"; \
  Flags: nowait postinstall skipifsilent unchecked
Filename: "{app}\register-startup-task-silent.bat"; \
  Flags: runhidden waituntilterminated skipifdoesntexist; \
  StatusMsg: "Configurando inicializacao automatica..."
Filename: "{app}\open-config.bat"; Description: "Editar config.yaml manualmente"; Flags: nowait postinstall skipifsilent unchecked

[Tasks]
Name: "desktopicon"; Description: "Criar atalho Wizard na Area de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[UninstallRun]
Filename: "{app}\unregister-startup-task.bat"; Flags: runhidden skipifdoesntexist

[Code]
var
  BrandingPage: TWizardPage;
  BrandingTitleLabel: TNewStaticText;
  BrandingInfoLabel: TNewStaticText;
  BrandingHintLabel: TNewStaticText;
  BrandingLogoImage: TBitmapImage;

function HasExternalConfig: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\config.yaml'));
end;

function GetBrandingIniPath: string;
begin
  Result := ExpandConstant('{src}\branding.ini');
end;

function GetBrandingPartnerName: string;
begin
  if FileExists(GetBrandingIniPath()) then
    Result := Trim(GetIniString('partner', 'name', '', GetBrandingIniPath()))
  else
    Result := '';
end;

function GetBrandingLogoPath: string;
var
  ConfiguredLogo: string;
begin
  Result := '';

  if FileExists(GetBrandingIniPath()) then
  begin
    ConfiguredLogo := Trim(GetIniString('partner', 'logo_file', '', GetBrandingIniPath()));
    if ConfiguredLogo <> '' then
    begin
      Result := ExpandConstant('{src}\') + ConfiguredLogo;
      if FileExists(Result) then
        exit;
    end;
  end;

  Result := ExpandConstant('{src}\logo-revendedor.bmp');
  if FileExists(Result) then
    exit;

  Result := '';
end;

function HasBrandingAssets: Boolean;
begin
  Result := (GetBrandingPartnerName() <> '') or (GetBrandingLogoPath() <> '');
end;

function IsBmpFile(const FilePath: string): Boolean;
var
  Lowered: string;
begin
  Lowered := Lowercase(FilePath);
  Result := (Length(Lowered) >= 4) and (Copy(Lowered, Length(Lowered) - 3, 4) = '.bmp');
end;

procedure InitializeWizard;
var
  PartnerName: string;
  LogoPath: string;
  InfoText: string;
begin
  if not HasBrandingAssets() then
    exit;

  PartnerName := GetBrandingPartnerName();
  LogoPath := GetBrandingLogoPath();

  BrandingPage := CreateCustomPage(
    wpWelcome,
    'Apresentacao do revendedor',
    'Este pacote foi preparado por um parceiro autorizado'
  );

  BrandingTitleLabel := TNewStaticText.Create(WizardForm);
  BrandingTitleLabel.Parent := BrandingPage.Surface;
  BrandingTitleLabel.Left := ScaleX(0);
  BrandingTitleLabel.Top := ScaleY(0);
  BrandingTitleLabel.Width := BrandingPage.SurfaceWidth;
  BrandingTitleLabel.Height := ScaleY(24);
  BrandingTitleLabel.Font.Style := [fsBold];

  if PartnerName <> '' then
    BrandingTitleLabel.Caption := 'Revendedor responsavel: ' + PartnerName
  else
    BrandingTitleLabel.Caption := 'Instalacao personalizada do seu revendedor';

  BrandingInfoLabel := TNewStaticText.Create(WizardForm);
  BrandingInfoLabel.Parent := BrandingPage.Surface;
  BrandingInfoLabel.Left := ScaleX(0);
  BrandingInfoLabel.Top := ScaleY(32);
  BrandingInfoLabel.Width := BrandingPage.SurfaceWidth;
  BrandingInfoLabel.Height := ScaleY(56);
  BrandingInfoLabel.WordWrap := True;
  BrandingInfoLabel.AutoSize := False;

  InfoText :=
    'O software continua com o nome Print Collect Agent. ' +
    'A personalizacao exibida aqui e apenas visual/comercial e nao altera o funcionamento do agente.';
  BrandingInfoLabel.Caption := InfoText;

  BrandingHintLabel := TNewStaticText.Create(WizardForm);
  BrandingHintLabel.Parent := BrandingPage.Surface;
  BrandingHintLabel.Left := ScaleX(0);
  BrandingHintLabel.Top := ScaleY(176);
  BrandingHintLabel.Width := BrandingPage.SurfaceWidth;
  BrandingHintLabel.Height := ScaleY(40);
  BrandingHintLabel.WordWrap := True;
  BrandingHintLabel.AutoSize := False;

  if (LogoPath <> '') and IsBmpFile(LogoPath) then
  begin
    BrandingLogoImage := TBitmapImage.Create(WizardForm);
    BrandingLogoImage.Parent := BrandingPage.Surface;
    BrandingLogoImage.Left := ScaleX(0);
    BrandingLogoImage.Top := ScaleY(92);
    BrandingLogoImage.Width := ScaleX(260);
    BrandingLogoImage.Height := ScaleY(72);
    BrandingLogoImage.Stretch := True;
    BrandingLogoImage.Center := True;
    BrandingLogoImage.Bitmap.LoadFromFile(LogoPath);
    BrandingHintLabel.Caption := 'A marca acima foi carregada a partir do arquivo logo-revendedor.bmp colocado ao lado do instalador.';
  end
  else
  begin
    BrandingHintLabel.Caption := 'Se o revendedor quiser mostrar a logo durante a instalacao, basta colocar um arquivo logo-revendedor.bmp na mesma pasta do PrintCollectSetup.exe.';
  end;
end;
