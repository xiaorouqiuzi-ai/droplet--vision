; Version and paths are supplied by scripts/build_windows_release.py.
[Setup]
AppId={{19F81635-09A7-4E93-9CA6-57A3D0F4E2D1}
AppName=Droplet Vision
AppVersion={#AppVersion}
AppPublisher=xiaorouqiuzi-ai
AppPublisherURL=https://github.com/xiaorouqiuzi-ai/droplet--vision
DefaultDirName={autopf}\Droplet Vision
DefaultGroupName=Droplet Vision
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir={#ReleaseDir}
OutputBaseFilename=DropletVision-Setup-v{#AppVersion}
SetupIconFile=..\src\droplet_vision\ui\assets\icons\planico.ico
UninstallDisplayIcon={app}\DropletVision.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
ChangesAssociations=yes
WizardStyle=modern
VersionInfoVersion={#NumericVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "cineassociation"; Description: "Associate Phantom Cine files with Droplet Vision"; Flags: unchecked

[Files]
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Droplet Vision"; Filename: "{app}\DropletVision.exe"
Name: "{autodesktop}\Droplet Vision"; Filename: "{app}\DropletVision.exe"; Tasks: desktopicon

; OpenWith registration does not replace another application's extension default
; or Windows-protected UserChoice. Uninstall removes only our owned entries.
[Registry]
Root: HKA; Subkey: "Software\Classes\.dvapkg\OpenWithProgids"; ValueType: string; ValueName: "DropletVision.AnnotationPackage"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\DropletVision.AnnotationPackage"; ValueType: string; ValueData: "Droplet Vision Annotation Package"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\DropletVision.AnnotationPackage\DefaultIcon"; ValueType: string; ValueData: """{app}\DropletVision.exe"",0"
Root: HKA; Subkey: "Software\Classes\DropletVision.AnnotationPackage\shell\open\command"; ValueType: string; ValueData: """{app}\DropletVision.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.dvrpkg\OpenWithProgids"; ValueType: string; ValueName: "DropletVision.LegacyReviewPackage"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\DropletVision.LegacyReviewPackage"; ValueType: string; ValueData: "Droplet Vision Legacy Package"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\DropletVision.LegacyReviewPackage\DefaultIcon"; ValueType: string; ValueData: """{app}\DropletVision.exe"",0"
Root: HKA; Subkey: "Software\Classes\DropletVision.LegacyReviewPackage\shell\open\command"; ValueType: string; ValueData: """{app}\DropletVision.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.cine\OpenWithProgids"; ValueType: string; ValueName: "DropletVision.Cine"; ValueData: ""; Flags: uninsdeletevalue; Tasks: cineassociation
Root: HKA; Subkey: "Software\Classes\DropletVision.Cine"; ValueType: string; ValueData: "Phantom Cine"; Flags: uninsdeletekey; Tasks: cineassociation
Root: HKA; Subkey: "Software\Classes\DropletVision.Cine\DefaultIcon"; ValueType: string; ValueData: """{app}\DropletVision.exe"",0"; Tasks: cineassociation
Root: HKA; Subkey: "Software\Classes\DropletVision.Cine\shell\open\command"; ValueType: string; ValueData: """{app}\DropletVision.exe"" ""%1"""; Tasks: cineassociation

[Code]
function ClassesRoot: Integer;
begin
  if IsAdminInstallMode then Result := HKLM else Result := HKCU;
end;

procedure RegisterUnclaimedExtension(Extension, ProgID: String);
var
  Current: String;
begin
  if not RegQueryStringValue(ClassesRoot, 'Software\Classes\' + Extension, '', Current) or (Current = '') then
    RegWriteStringValue(ClassesRoot, 'Software\Classes\' + Extension, '', ProgID);
end;

procedure RemoveOwnedDefault(Extension, ProgID: String);
var
  Current: String;
begin
  if RegQueryStringValue(ClassesRoot, 'Software\Classes\' + Extension, '', Current) and (Current = ProgID) then
  begin
    RegDeleteValue(ClassesRoot, 'Software\Classes\' + Extension, '');
    RegDeleteKeyIfEmpty(ClassesRoot, 'Software\Classes\' + Extension);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RegisterUnclaimedExtension('.dvapkg', 'DropletVision.AnnotationPackage');
    RegisterUnclaimedExtension('.dvrpkg', 'DropletVision.LegacyReviewPackage');
    if WizardIsTaskSelected('cineassociation') then
      RegisterUnclaimedExtension('.cine', 'DropletVision.Cine');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveOwnedDefault('.dvapkg', 'DropletVision.AnnotationPackage');
    RemoveOwnedDefault('.dvrpkg', 'DropletVision.LegacyReviewPackage');
    RemoveOwnedDefault('.cine', 'DropletVision.Cine');
  end;
end;
