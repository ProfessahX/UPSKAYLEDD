#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef PortableDir
  #error PortableDir not defined
#endif
#ifndef OutputDir
  #error OutputDir not defined
#endif
#ifndef BrandingDir
  #error BrandingDir not defined
#endif
#ifndef LicenseFile
  #error LicenseFile not defined
#endif

#define AppName "UPSKAYLEDD"
#define AppExeName "upskayledd-desktop.exe"

[Setup]
AppId={{A9E98E53-48C9-4E4E-8B10-3C312E9F04D8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=UPSKAYLEDD Contributors
AppPublisherURL=https://github.com/
DefaultDirName={localappdata}\Programs\UPSKAYLEDD
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
LicenseFile={#LicenseFile}
OutputDir={#OutputDir}
OutputBaseFilename=UPSKAYLEDD-Setup-{#AppVersion}
SetupIconFile={#BrandingDir}\upskayledd.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\UPSKAYLEDD"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{#BrandingDir}\upskayledd.ico"
Name: "{userprograms}\UPSKAYLEDD"; Filename: "{app}\{#AppExeName}"; IconFilename: "{#BrandingDir}\upskayledd.ico"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch UPSKAYLEDD"; Flags: nowait postinstall skipifsilent
