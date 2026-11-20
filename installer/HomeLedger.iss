; HomeLedger installer (Inno Setup 6). Built automatically by GitHub (see .github/workflows/build-installer.yml).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B7C0F4D2-5E1A-4C86-9A3B-0D6E2F1A7C45}
AppName=HomeLedger
AppVersion={#AppVersion}
AppVerName=HomeLedger {#AppVersion}
AppPublisher=HomeLedger
; Installs just for the signed-in Windows user: no administrator password needed, and it can be removed from Settings > Apps.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\HomeLedger
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\installer_out
OutputBaseFilename=HomeLedger-Setup-{#AppVersion}
SetupIconFile=..\homeledger.ico
UninstallDisplayIcon={app}\HomeLedger.exe
UninstallDisplayName=HomeLedger
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName=HomeLedger

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop icon"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\HomeLedger\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\homeledger.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\HomeLedger"; Filename: "{app}\HomeLedger.exe"; IconFilename: "{app}\homeledger.ico"; Comment: "Household and farm accounts"
Name: "{autoprograms}\Uninstall HomeLedger"; Filename: "{uninstallexe}"
Name: "{autodesktop}\HomeLedger"; Filename: "{app}\HomeLedger.exe"; IconFilename: "{app}\homeledger.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\HomeLedger.exe"; Description: "Start HomeLedger now"; Flags: nowait postinstall skipifsilent

[Code]
function BrowserFound: Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{commonpf32}\Microsoft\Edge\Application\msedge.exe')) or
    FileExists(ExpandConstant('{commonpf64}\Microsoft\Edge\Application\msedge.exe')) or
    FileExists(ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{commonpf64}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

procedure StopRunningApp;
var
  rc: Integer;
begin
  { HomeLedger saves after every entry and survives a sudden stop, so closing it here is safe }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM HomeLedger.exe /F', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Sleep(600);
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not BrowserFound then
    MsgBox('HomeLedger shows its window using Microsoft Edge or Google Chrome, and neither was found on this computer.' + #13#10#13#10 +
           'Windows 10 and 11 normally include Edge. HomeLedger will still install and will open in your default web browser instead.',
           mbInformation, MB_OK);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  StopRunningApp;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    if MsgBox('HomeLedger has been removed.' + #13#10#13#10 +
              'Your accounts and automatic backups are still stored on this computer in:' + #13#10 +
              ExpandConstant('{localappdata}\HomeLedger') + #13#10#13#10 +
              'Do you also want to DELETE that data permanently?' + #13#10 +
              'Choose No to keep it (recommended). Copies you saved in other folders, such as a pen drive or Google Drive, are never deleted.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{localappdata}\HomeLedger'), True, True, True);
  end;
end;
