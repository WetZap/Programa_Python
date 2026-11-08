; Instalador de Windows de ajustelab (Inno Setup 6).
; Lo llama empaquetado/construir.py:
;   iscc /DVersion=1.7.0 /DOrigen=dist\ajustelab /DSalida=dist /DIcono=ajustelab\gui\recursos\icono.ico ajustelab.iss
; Instala para el usuario (sin permisos de administrador; se puede elegir para todos),
; con acceso en el menú Inicio, icono en el escritorio opcional, asociación de los
; ficheros .ajustelab y desinstalador.

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Origen
  #define Origen "..\dist\ajustelab"
#endif
#ifndef Salida
  #define Salida "..\dist"
#endif
#ifndef Icono
  #define Icono "..\ajustelab\gui\recursos\icono.ico"
#endif

[Setup]
AppId={{34AA6E26-773A-43D5-83D4-D888D57C991A}
AppName=ajustelab
AppVersion={#Version}
AppVerName=ajustelab {#Version}
AppPublisher=WetZap (Jorge del Río López)
AppPublisherURL=https://github.com/WetZap/Programa_Python
AppSupportURL=https://github.com/WetZap/Programa_Python/issues
; No en «Programs\ajustelab»: esa carpeta es la de instalar.ps1 (con pip) y se pisarían.
DefaultDirName={autopf}\WetZap\ajustelab
DefaultGroupName=ajustelab
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Salida}
OutputBaseFilename=ajustelab-{#Version}-windows-x64-instalador
SetupIconFile={#Icono}
UninstallDisplayIcon={app}\ajustelab.exe
UninstallDisplayName=ajustelab {#Version}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked
Name: "asociar"; Description: "Abrir las sesiones .ajustelab con ajustelab"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; una versión anterior podía dejar bibliotecas que ya no se usan
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\ajustelab"; Filename: "{app}\ajustelab.exe"; AppUserModelID: "WetZap.ajustelab"; Comment: "Ajustes, estadística y gráficas para el laboratorio"
Name: "{autodesktop}\ajustelab"; Filename: "{app}\ajustelab.exe"; AppUserModelID: "WetZap.ajustelab"; Tasks: escritorio

[Registry]
Root: HKA; Subkey: "Software\Classes\.ajustelab"; ValueType: string; ValueName: ""; ValueData: "ajustelab.sesion"; Flags: uninsdeletevalue; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\ajustelab.sesion"; ValueType: string; ValueName: ""; ValueData: "Sesión de ajustelab"; Flags: uninsdeletekey; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\ajustelab.sesion\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\ajustelab.exe,0"; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\ajustelab.sesion\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ajustelab.exe"" ""%1"""; Tasks: asociar

[Run]
Filename: "{app}\ajustelab.exe"; Description: "Abrir ajustelab"; Flags: nowait postinstall skipifsilent
