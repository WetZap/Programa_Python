<#
.SYNOPSIS
    Instalador de ajustelab para Windows 10 y 11.

.DESCRIPTION
    En PowerShell:

        irm https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1 | iex

    Todo queda en tu usuario y no hacen falta permisos de administrador:
      1. Busca Python >= 3.10 (lanzador «py» o PATH); si falta, ofrece instalar
         Python 3.13 con winget.
      2. Crea un entorno propio en %LOCALAPPDATA%\Programs\ajustelab\venv e
         instala ajustelab ahí.
      3. Deja las órdenes «ajustelab» y «ajustelab-cli» en
         %LOCALAPPDATA%\Programs\ajustelab\bin y añade esa carpeta al PATH.
      4. Crea el acceso directo del menú Inicio (y, si quieres, del escritorio)
         y asocia los ficheros .ajustelab para abrirlos con doble clic.
      5. Lo registra en Configuración > Aplicaciones, desde donde se desinstala.
      6. Comprueba que la interfaz arranca.
    Volver a ejecutarlo actualiza a la última versión.

    Con «irm | iex» no se pueden pasar parámetros; usa esta forma:
        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1))) -Si
    o las variables de entorno AJUSTELAB_SI=1, AJUSTELAB_DESINSTALAR=1,
    AJUSTELAB_SIN_ESCRITORIO=1, AJUSTELAB_DESDE, AJUSTELAB_RAMA y AJUSTELAB_PYTHON.

.PARAMETER Si
    Responde «sí» a todo (instalar Python con winget, acceso en el escritorio...).
.PARAMETER Desinstalar
    Quita ajustelab: entorno, órdenes, accesos directos, asociación y PATH.
.PARAMETER SinAccesoEscritorio
    No crea el acceso directo del escritorio.
.PARAMETER Python
    Intérprete que se usa (Python >= 3.10).
.PARAMETER Desde
    Instala desde otra carpeta, fichero o URL que entienda pip.
.PARAMETER Rama
    Rama de GitHub que se descarga (por defecto, main).
#>
param(
    [switch]$Si,
    [switch]$Desinstalar,
    [switch]$SinAccesoEscritorio,
    [string]$Python = '',
    [string]$Desde = '',
    [string]$Rama = 'main'
)

if ($env:AJUSTELAB_SI -eq '1') { $Si = $true }
if ($env:AJUSTELAB_DESINSTALAR -eq '1') { $Desinstalar = $true }
if ($env:AJUSTELAB_DESDE) { $Desde = $env:AJUSTELAB_DESDE }
if ($env:AJUSTELAB_RAMA) { $Rama = $env:AJUSTELAB_RAMA }
if ($env:AJUSTELAB_PYTHON) { $Python = $env:AJUSTELAB_PYTHON }
if ($env:AJUSTELAB_SIN_ESCRITORIO -eq '1') { $SinAccesoEscritorio = $true }

$AjRaiz = Join-Path $env:LOCALAPPDATA 'Programs\ajustelab'
$AjVenv = Join-Path $AjRaiz 'venv'
$AjBin = Join-Path $AjRaiz 'bin'
$AjRepo = 'https://github.com/WetZap/Programa_Python'
$AjUrlInstalador = 'https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1'
$AjClaveDesinstalar = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ajustelab'

# --- salida y preguntas ---------------------------------------------------------
# Solo caracteres que existen en las páginas de códigos de la consola (850/1252).
function AjPaso {
    param([string]$Texto)
    Write-Host ''
    Write-Host "==> $Texto" -ForegroundColor Cyan
}
function AjOk {
    param([string]$Texto)
    Write-Host "  [ok] $Texto" -ForegroundColor Green
}
function AjAviso {
    param([string]$Texto)
    Write-Host "  [!] $Texto" -ForegroundColor Yellow
}
function AjPreguntar {
    param([string]$Texto, [bool]$PorDefecto = $true)
    if ($Si) { return $true }
    if ([Console]::IsInputRedirected) { return $false }  # sin terminal (CI): no se cambia nada
    $opciones = '[s/N]'
    if ($PorDefecto) { $opciones = '[S/n]' }
    $respuesta = Read-Host "  $Texto $opciones"
    if ([string]::IsNullOrWhiteSpace($respuesta)) { return $PorDefecto }
    return ($respuesta -match '^[sSyY]')
}

# --- PATH del usuario -----------------------------------------------------------
# Se lee y escribe el valor sin expandir (REG_EXPAND_SZ) para no estropear las
# entradas con %USERPROFILE% y similares.
function AjAvisarEntorno {
    param()
    # .NET difunde WM_SETTINGCHANGE al cambiar una variable de usuario: así las
    # terminales que se abran después ven el PATH nuevo sin cerrar sesión.
    [Environment]::SetEnvironmentVariable('AJUSTELAB_REFRESCO', '1', 'User')
    [Environment]::SetEnvironmentVariable('AJUSTELAB_REFRESCO', $null, 'User')
}
function AjPartesPath {
    param([string]$Valor)
    return @($Valor -split ';' | Where-Object { $_ -and $_.Trim() })
}
function AjAnadirPath {
    param([string]$Dir)
    $clave = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    try {
        $actual = [string]$clave.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $partes = AjPartesPath $actual
        foreach ($p in $partes) { if ($p.TrimEnd('\') -ieq $Dir.TrimEnd('\')) { return $false } }
        $clave.SetValue('Path', ((@($partes) + $Dir) -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
    } finally { $clave.Close() }
    AjAvisarEntorno
    return $true
}
function AjQuitarPath {
    param([string]$Dir)
    $clave = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    try {
        $actual = [string]$clave.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $partes = AjPartesPath $actual
        $resto = @($partes | Where-Object { $_.TrimEnd('\') -ine $Dir.TrimEnd('\') })
        if ($resto.Count -eq $partes.Count) { return $false }
        $clave.SetValue('Path', ($resto -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
    } finally { $clave.Close() }
    AjAvisarEntorno
    return $true
}

# --- Python ---------------------------------------------------------------------
function AjPythonValido {
    # Ruta real de python.exe si es >= 3.10 y tiene venv; si no, $null.
    param([string]$Exe, [string[]]$Previos = @())
    $codigo = "import sys, venv, ensurepip; print(sys.executable if sys.version_info >= (3, 10) else '')"
    try { $salida = & $Exe @Previos -c $codigo 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $salida) { return $null }
    $ruta = ([string]($salida | Select-Object -Last 1)).Trim()
    if ($ruta -and (Test-Path -LiteralPath $ruta)) { return $ruta }
    return $null
}
function AjVersionPython {
    param([string]$Exe)
    if (-not (Test-Path -LiteralPath $Exe)) { return '' }
    try { $v = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { return '' }
    if ($LASTEXITCODE -ne 0) { return '' }
    return ([string]$v).Trim()
}
function AjBuscarPython {
    param()
    if ($Python) { return (AjPythonValido $Python) }
    if (Get-Command py -CommandType Application -ErrorAction SilentlyContinue) {
        # 3.13 primero: todas las dependencias tienen paquetes para ella
        foreach ($v in '3.13', '3.12', '3.14', '3.11', '3.10') {
            $r = AjPythonValido 'py' @("-$v")
            if ($r) { return $r }
        }
    }
    foreach ($nombre in 'python', 'python3') {
        # El «python.exe» de WindowsApps es un atajo que abre la Microsoft Store
        $c = Get-Command $nombre -CommandType Application -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
        if ($c) {
            $r = AjPythonValido $c.Source
            if ($r) { return $r }
        }
    }
    # Recién instalado con winget o python.org: puede no estar aún en el PATH de esta sesión
    foreach ($v in '313', '312', '314', '311', '310') {
        foreach ($base in (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v"), (Join-Path $env:ProgramFiles "Python$v")) {
            $exe = Join-Path $base 'python.exe'
            if (Test-Path -LiteralPath $exe) {
                $r = AjPythonValido $exe
                if ($r) { return $r }
            }
        }
    }
    return $null
}

function AjOrigen {
    param()
    if ($Desde) { return $Desde }
    # Ejecutado como fichero dentro del repositorio: se instala esa copia
    if ($PSCommandPath) {
        $dir = Split-Path -Parent $PSCommandPath
        $pyproject = Join-Path $dir 'pyproject.toml'
        if ((Test-Path -LiteralPath $pyproject) -and (Select-String -LiteralPath $pyproject -Pattern '^name = "ajustelab"' -Quiet)) {
            return $dir
        }
    }
    return "$AjRepo/archive/refs/heads/$Rama.zip"
}

function AjProcesosAbiertos {
    param()
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $ruta = $null
            try { $ruta = $_.Path } catch { $ruta = $null }
            $ruta -and $ruta.StartsWith($AjRaiz, [StringComparison]::OrdinalIgnoreCase)
        })
}

# --- instalar -------------------------------------------------------------------
function AjInstalar {
    param()
    AjPaso "Sistema: Windows $([Environment]::OSVersion.Version) ($env:PROCESSOR_ARCHITECTURE), PowerShell $($PSVersionTable.PSVersion)"

    AjPaso 'Python'
    $py = AjBuscarPython
    if (-not $py -and -not $Python) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            if (AjPreguntar 'Falta Python >= 3.10. ¿Instalar Python 3.13 con winget?') {
                winget install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
                $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
                $py = AjBuscarPython
            }
        }
    }
    if (-not $py) {
        if ($Python) { throw "$Python no es Python >= 3.10 con el módulo venv." }
        throw ('Hace falta Python >= 3.10. Instálalo desde https://www.python.org/downloads/windows/ ' +
            '(marca «Add python.exe to PATH») o con «winget install Python.Python.3.13», y vuelve a ejecutar este instalador.')
    }
    AjOk "Python $(AjVersionPython $py) ($py)"

    $abiertos = AjProcesosAbiertos
    if ($abiertos.Count -gt 0) {
        if (AjPreguntar 'ajustelab está abierto y hay que cerrarlo para actualizarlo. ¿Cerrarlo ahora?') {
            $abiertos | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        } else {
            throw 'Cierra ajustelab y vuelve a ejecutar el instalador.'
        }
    }

    AjPaso "Entorno en $AjVenv"
    $pyVenv = Join-Path $AjVenv 'Scripts\python.exe'
    if (Test-Path -LiteralPath $AjVenv) {
        if ((AjVersionPython $pyVenv) -ne (AjVersionPython $py)) {
            AjAviso 'El entorno usa otra versión de Python o se ha roto: se vuelve a crear.'
            Remove-Item -LiteralPath $AjVenv -Recurse -Force
        }
    }
    if (-not (Test-Path -LiteralPath $AjVenv)) {
        New-Item -ItemType Directory -Force -Path $AjRaiz | Out-Null
        & $py -m venv $AjVenv | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual con $py." }
        AjOk 'Creado'
    } else {
        AjOk 'Ya existía: se actualiza'
    }
    & $pyVenv -m pip install --quiet --disable-pip-version-check --upgrade pip | Out-Host
    if ($LASTEXITCODE -ne 0) { AjAviso 'No se pudo actualizar pip; se sigue con el que hay.' }

    $origen = AjOrigen
    AjPaso "Instalando ajustelab desde $origen"
    Write-Host '  La primera vez se descargan unos 200 MB (Qt, SciPy, SymPy...): puede tardar unos minutos.'
    & $pyVenv -m pip uninstall --quiet --yes ajustelab 2>$null | Out-Null
    & $pyVenv -m pip install --disable-pip-version-check $origen | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'pip no pudo instalar ajustelab. Revisa la conexión a Internet y vuelve a intentarlo.' }
    $version = (& $pyVenv -c 'import ajustelab; print(ajustelab.__version__)') | Select-Object -Last 1
    AjOk "ajustelab $version"

    AjPaso "Instalando las órdenes en $AjBin"
    New-Item -ItemType Directory -Force -Path $AjBin | Out-Null
    # «ajustelab» como .cmd con el Python de consola: en la terminal muestra la salida
    # de --version, --diagnostico... (el menú Inicio usa el lanzador sin consola).
    # Ruta relativa (%~dp0): cmd.exe lee los .cmd en la página de códigos OEM y una
    # ruta absoluta con «José» o «ñ» se rompería. El contenido es ASCII.
    $cmd = "@echo off`r`nrem Generado por instalar.ps1 de ajustelab (se regenera al reinstalar).`r`n" +
        "`"%~dp0..\venv\Scripts\python.exe`" -m ajustelab %*`r`n"
    [IO.File]::WriteAllText((Join-Path $AjBin 'ajustelab.cmd'), $cmd, (New-Object System.Text.ASCIIEncoding))
    Copy-Item -LiteralPath (Join-Path $AjVenv 'Scripts\ajustelab-cli.exe') -Destination (Join-Path $AjBin 'ajustelab-cli.exe') -Force
    AjOk 'ajustelab y ajustelab-cli'
    if (AjAnadirPath $AjBin) {
        AjOk 'Añadido al PATH de tu usuario (abre una terminal nueva para usarlo)'
    } else {
        AjOk 'Ya estaba en el PATH'
    }
    if (-not ((@($env:Path -split ';') | ForEach-Object { $_.TrimEnd('\') }) -contains $AjBin.TrimEnd('\'))) {
        $env:Path = "$env:Path;$AjBin"
    }

    AjPaso 'Menú Inicio y ficheros .ajustelab'
    & $pyVenv -m ajustelab --instalar-escritorio | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el acceso directo del menú Inicio.' }
    AjOk 'ajustelab aparece en el menú Inicio; las sesiones .ajustelab se abren con doble clic'
    $acceso = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ajustelab.lnk'
    $escritorio = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ajustelab.lnk'
    if (-not $SinAccesoEscritorio -and (Test-Path -LiteralPath $acceso)) {
        if ((Test-Path -LiteralPath $escritorio) -or (AjPreguntar '¿Crear también un acceso directo en el escritorio?')) {
            Copy-Item -LiteralPath $acceso -Destination $escritorio -Force
            AjOk 'Acceso directo en el escritorio'
        }
    }

    AjPaso 'Configuración > Aplicaciones'
    $ico = Join-Path $AjRaiz 'ajustelab.ico'
    $icoPaquete = (& $pyVenv -c "from ajustelab.escritorio import RECURSOS; print(RECURSOS / 'icono.ico')") | Select-Object -Last 1
    Copy-Item -LiteralPath ([string]$icoPaquete).Trim() -Destination $ico -Force
    $desinstalador = Join-Path $AjRaiz 'desinstalar.ps1'
    [IO.File]::WriteAllText($desinstalador, (AjTextoDesinstalador), (New-Object System.Text.UTF8Encoding($true)))
    $orden = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$desinstalador`""
    New-Item -Path $AjClaveDesinstalar -Force | Out-Null
    $tamano = [int]((Get-ChildItem -LiteralPath $AjRaiz -Recurse -File -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum).Sum / 1KB)
    $valores = @{
        DisplayName = 'ajustelab'; DisplayVersion = $version; Publisher = 'WetZap (Jorge del Río López)'
        DisplayIcon = $ico; InstallLocation = $AjRaiz; URLInfoAbout = $AjRepo
        HelpLink = "$AjRepo#solución-de-problemas"; UninstallString = $orden; QuietUninstallString = "$orden -Si"
    }
    foreach ($k in $valores.Keys) { Set-ItemProperty -Path $AjClaveDesinstalar -Name $k -Value $valores[$k] }
    foreach ($k in 'NoModify', 'NoRepair') { Set-ItemProperty -Path $AjClaveDesinstalar -Name $k -Value 1 -Type DWord }
    Set-ItemProperty -Path $AjClaveDesinstalar -Name EstimatedSize -Value $tamano -Type DWord
    AjOk 'Se puede desinstalar desde Configuración > Aplicaciones > Aplicaciones instaladas'

    AjPaso 'Comprobación'
    $plataformaPrevia = $env:QT_QPA_PLATFORM
    $env:QT_QPA_PLATFORM = 'offscreen'  # sin abrir ninguna ventana
    try { & $pyVenv -m ajustelab --probar-interfaz | Out-Null } finally { $env:QT_QPA_PLATFORM = $plataformaPrevia }
    if ($LASTEXITCODE -ne 0) {
        AjAviso 'La interfaz no arranca. Diagnóstico:'
        & $pyVenv -m ajustelab --diagnostico | Out-Host
        throw 'ajustelab está instalado, pero la ventana no arranca (ver el diagnóstico).'
    }
    AjOk 'La interfaz carga correctamente'

    Write-Host ''
    Write-Host '¡Listo! Abre ajustelab desde el menú Inicio, o escribe «ajustelab» en una terminal nueva.' -ForegroundColor Green
    Write-Host "  Actualizar:   vuelve a ejecutar   irm $AjUrlInstalador | iex"
    Write-Host '  Problemas:    ajustelab --diagnostico'
    Write-Host '  Desinstalar:  Configuración > Aplicaciones > ajustelab'
}

# --- desinstalar ----------------------------------------------------------------
function AjDesinstalar {
    param()
    AjPaso 'Desinstalando ajustelab'
    $abiertos = AjProcesosAbiertos
    if ($abiertos.Count -gt 0) {
        AjAviso 'Cerrando ajustelab...'
        $abiertos | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    $pyVenv = Join-Path $AjVenv 'Scripts\python.exe'
    if (Test-Path -LiteralPath $pyVenv) { & $pyVenv -m ajustelab --desinstalar-escritorio 2>$null | Out-Null }
    # Lo mismo a mano, por si el entorno ya no funciona
    foreach ($lnk in (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ajustelab.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ajustelab.lnk')) {
        Remove-Item -LiteralPath $lnk -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path 'HKCU:\Software\Classes\WetZap.ajustelab.sesion' -Recurse -Force -ErrorAction SilentlyContinue
    $ext = 'HKCU:\Software\Classes\.ajustelab'
    if ((Test-Path $ext) -and ((Get-ItemProperty -Path $ext).'(default)' -eq 'WetZap.ajustelab.sesion')) {
        Remove-Item -Path $ext -Recurse -Force -ErrorAction SilentlyContinue
    }
    AjOk 'Accesos directos y asociación de .ajustelab'
    if (AjQuitarPath $AjBin) { AjOk 'Quitado del PATH' }
    Remove-Item -Path $AjClaveDesinstalar -Recurse -Force -ErrorAction SilentlyContinue
    AjOk 'Entrada de Configuración > Aplicaciones'
    $ajustes = 'HKCU:\Software\WetZap\ajustelab'
    if ((Test-Path $ajustes) -and (AjPreguntar '¿Borrar también tus ajustes (tema, ficheros recientes...)?' $false)) {
        Remove-Item -Path $ajustes -Recurse -Force -ErrorAction SilentlyContinue
        AjOk 'Ajustes'
    }
    Set-Location -LiteralPath $env:TEMP  # para poder borrar la carpeta aunque estuviéramos dentro
    Remove-Item -LiteralPath $AjRaiz -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $AjRaiz) {
        AjAviso "No se pudo borrar del todo $AjRaiz (¿algún fichero en uso?): bórrala a mano."
    } else {
        AjOk "Carpeta $AjRaiz"
    }
    Write-Host ''
    Write-Host 'ajustelab se ha desinstalado. Tus datos y sesiones .ajustelab no se han tocado.' -ForegroundColor Green
}

# El desinstalador que se guarda junto a la instalación (y que lanza Configuración >
# Aplicaciones) se genera con las mismas funciones de este script.
function AjTextoDesinstalador {
    param()
    $citar = { param($t) "'" + ($t -replace "'", "''") + "'" }
    $lineas = @(
        '# Desinstalador de ajustelab, generado por instalar.ps1.',
        'param([switch]$Si)',
        "`$AjRaiz = $(& $citar $AjRaiz)",
        "`$AjVenv = $(& $citar $AjVenv)",
        "`$AjBin = $(& $citar $AjBin)",
        "`$AjClaveDesinstalar = $(& $citar $AjClaveDesinstalar)",
        '$ErrorActionPreference = ''Continue'''
    )
    foreach ($f in 'AjPaso', 'AjOk', 'AjAviso', 'AjPreguntar', 'AjAvisarEntorno', 'AjPartesPath', 'AjQuitarPath',
        'AjProcesosAbiertos', 'AjDesinstalar') {
        $lineas += "function $f {"
        $lineas += (Get-Item "function:$f").ScriptBlock.ToString()
        $lineas += '}'
    }
    $lineas += 'AjDesinstalar'
    $lineas += 'if (-not $Si -and -not [Console]::IsInputRedirected) { Read-Host ''  Pulsa Intro para cerrar'' | Out-Null }'
    return ($lineas -join "`r`n")
}

function AjPrincipal {
    param()
    $ErrorActionPreference = 'Continue'  # solo en esta función: los errores se tratan a mano
    $previas = @{}
    foreach ($v in 'PYTHONUTF8', 'PYTHONIOENCODING') { $previas[$v] = [Environment]::GetEnvironmentVariable($v, 'Process') }
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    # PowerShell decodifica la salida de los programas con la codificación de la consola;
    # mientras dura la instalación es UTF-8, como la de Python (se restaura al final).
    $codificacionPrevia = $null
    try {
        $codificacionPrevia = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    } catch { $codificacionPrevia = $null }
    try {
        if ($Desinstalar) { AjDesinstalar } else { AjInstalar }
    } catch {
        Write-Host ''
        Write-Host "[error] $($_.Exception.Message)" -ForegroundColor Red
        Set-Variable -Name AjCodigo -Value 1 -Scope 1
    } finally {
        foreach ($v in $previas.Keys) { [Environment]::SetEnvironmentVariable($v, $previas[$v], 'Process') }
        if ($codificacionPrevia) { try { [Console]::OutputEncoding = $codificacionPrevia } catch { $null = $_ } }
    }
}

# Todo está en funciones y la llamada va al final: con «irm | iex» no se ejecuta
# nada hasta leer el script entero. No se usa «exit» salvo al ejecutarlo como
# fichero, porque con «iex» cerraría la ventana de PowerShell.
$AjCodigo = 0
AjPrincipal
if ($PSCommandPath -and $AjCodigo -ne 0) { exit $AjCodigo }
