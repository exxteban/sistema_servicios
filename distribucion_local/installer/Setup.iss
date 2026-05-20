#define AppName "Sistema Silvio Cel Local"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef ClienteId
  #define ClienteId "cliente"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "Setup_SistemaSilvioCel"
#endif

[Setup]
AppId={{A4E67A7C-06D8-4A24-96CD-9FA7FBE32AA1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Sistema Silvio Cel
DefaultDirName={autopf}\SistemaSilvioCel
DefaultGroupName=Sistema Silvio Cel
OutputDir=..\artifacts\installers
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en escritorio"; GroupDescription: "Accesos directos"

[Files]
Source: "..\artifacts\backend\backend_service.exe"; DestDir: "{app}\backend"; Flags: ignoreversion
Source: "..\artifacts\backend\.env.example"; DestDir: "{app}\backend"; Flags: ignoreversion
Source: "..\artifacts\frontend\*"; DestDir: "{app}\frontend"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\artifacts\license\license.dat"; DestDir: "{app}\license"; Flags: ignoreversion
Source: "..\scripts\install_service.ps1"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{group}\Sistema Silvio Cel"; Filename: "http://127.0.0.1:5003"
Name: "{autodesktop}\Sistema Silvio Cel"; Filename: "http://127.0.0.1:5003"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{tmp}\install_service.ps1"" -ServiceName ""SistemaSilvioCelBackend_{#ClienteId}"" -InstallDir ""{app}"" -BackendExeRelativePath ""backend\backend_service.exe"" -Host ""127.0.0.1"" -Port 5003 -AppConfig ""production"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "sc.exe"; Parameters: "stop SistemaSilvioCelBackend_{#ClienteId}"; Flags: runhidden
Filename: "sc.exe"; Parameters: "delete SistemaSilvioCelBackend_{#ClienteId}"; Flags: runhidden
