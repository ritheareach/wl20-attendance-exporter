; Inno Setup script — builds the Windows installer for the WL20 Attendance Exporter.
;
;   iscc /DMyAppVersion=1.4.0 packaging\windows-installer.iss
;
; It packages the PyInstaller folder build (dist-folder) into a normal
; double-click installer: per-user by default (so no administrator rights are
; needed on a locked-down office PC), with Start Menu entry, optional desktop
; shortcut and an uninstaller. The app itself needs no Python on the machine.

#define MyAppName "WL20 Attendance Exporter"
#define MyAppShortName "WL20 Attendance Exporter"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "AIFarm"
#define MyAppExeName "WL20-Attendance-Exporter.exe"
#define MyAppId "{{7C4A9E4B-3A21-4E77-9C0B-8F1D2A6B5E10}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppShortName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=WL20-Attendance-Exporter-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user install by default: the office Windows machine may not grant admin
; rights, and {autopf} resolves to %LOCALAPPDATA%\Programs in that case.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist-folder\WL20-Attendance-Exporter\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppShortName}}"; \
    Flags: nowait postinstall skipifsilent
