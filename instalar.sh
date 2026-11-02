#!/bin/sh
# Instalador de ajustelab para Linux (cualquier distribución con glibc).
#
#   curl -fsSL https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh | sh
#   sh instalar.sh                  # desde el repositorio clonado: instala esa copia
#   sh instalar.sh --desinstalar
#   sh instalar.sh --ayuda
#
# Todo queda en tu usuario y no toca el Python del sistema:
#   1. Comprueba que hay Python >= 3.10 con venv (si falta, ofrece instalarlo).
#   2. Crea un entorno propio en ~/.local/share/ajustelab/venv e instala ajustelab
#      ahí. Así se evita el error «externally-managed-environment» (PEP 668).
#   3. Enlaza «ajustelab» y «ajustelab-cli» en ~/.local/bin y revisa el PATH.
#   4. Ofrece instalar las bibliotecas del sistema que necesita Qt (xcb-cursor…).
#   5. Añade ajustelab al menú de aplicaciones, con icono y doble clic en .ajustelab.
#   6. Comprueba que la interfaz arranca.
# Volver a ejecutarlo actualiza a la última versión y repara el entorno si una
# actualización del Python del sistema lo ha roto.

set -eu

REPO="https://github.com/WetZap/Programa_Python"
URL_INSTALADOR="https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
DESTINO="$DATOS/ajustelab"
VENV="$DESTINO/venv"
BIN="$HOME/.local/bin"

SI=0
CON_DEPS=1
CON_MENU=1
DESDE=""
PYTHON=""
RAMA="main"
ACCION="instalar"

# --- salida ---------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    NEGRITA=$(printf '\033[1m'); VERDE=$(printf '\033[32m'); AMARILLO=$(printf '\033[33m')
    ROJO=$(printf '\033[31m'); NORMAL=$(printf '\033[0m')
else
    NEGRITA=""; VERDE=""; AMARILLO=""; ROJO=""; NORMAL=""
fi
paso() { printf '\n%s==> %s%s\n' "$NEGRITA" "$*" "$NORMAL"; }
ok() { printf '  %s✓%s %s\n' "$VERDE" "$NORMAL" "$*"; }
aviso() { printf '  %s!%s %s\n' "$AMARILLO" "$NORMAL" "$*"; }
fallo() { printf '\n%s✗ %s%s\n' "$ROJO" "$*" "$NORMAL" >&2; exit 1; }
hay() { command -v "$1" >/dev/null 2>&1; }

ayuda() {
    cat <<'FIN'
Instalador de ajustelab para Linux.

Uso: sh instalar.sh [opciones]
     curl -fsSL https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh | sh -s -- [opciones]

Opciones:
  -y, --si             responde «sí» a todo (también a instalar paquetes con sudo)
  --sin-dependencias   no comprueba ni instala paquetes del sistema
  --sin-menu           no añade ajustelab al menú de aplicaciones
  --python RUTA        usa ese intérprete (Python >= 3.10)
  --desde ORIGEN       instala desde otra carpeta, fichero o URL que entienda pip
  --rama RAMA          rama de GitHub que se descarga (por defecto: main)
  --desinstalar        quita ajustelab: entorno, órdenes y entrada del menú
  -h, --ayuda          muestra esta ayuda
FIN
}

# Pregunta sí/no en la terminal. Con «curl | sh» la entrada estándar es el propio
# script, así que se lee de /dev/tty. Sin terminal (CI, cron) la respuesta es «no»
# salvo que se haya pasado -y.   $1 = pregunta, $2 = s|n (respuesta con Intro)
preguntar() {
    [ "$SI" = 1 ] && return 0
    # En subshell: un error de redirección sobre un built-in especial («:») haría
    # salir a la shell entera en dash y otras shells POSIX.
    (exec </dev/tty) 2>/dev/null || return 1
    if [ "${2:-n}" = s ]; then opciones="[S/n]"; else opciones="[s/N]"; fi
    printf '  %s %s ' "$1" "$opciones" >/dev/tty
    respuesta=""
    read -r respuesta </dev/tty || respuesta=""
    case "$respuesta" in
        [sSyY]*) return 0 ;;
        [nN]*) return 1 ;;
        *) [ "${2:-n}" = s ] ;;
    esac
}

como_root() {
    if [ "$(id -u)" = 0 ]; then "$@"
    elif hay sudo; then sudo "$@"
    elif hay doas; then doas "$@"
    else fallo "Hace falta sudo o doas para instalar paquetes del sistema."
    fi
}

# --- distribución -------------------------------------------------------------
leer_os_release() {  # $1 = variable de os-release
    for f in /etc/os-release /usr/lib/os-release; do
        if [ -r "$f" ]; then
            # shellcheck source=/dev/null  # os-release es un fichero de asignaciones de shell
            (. "$f" && eval "printf '%s' \"\${$1:-}\"")
            return
        fi
    done
}

detectar_familia() {
    for i in $(leer_os_release ID) $(leer_os_release ID_LIKE); do
        case "$i" in
            arch|archarm|manjaro*|endeavouros|garuda|cachyos|artix|arcolinux) echo arch; return ;;
            debian|ubuntu|linuxmint|pop|elementary|zorin|kali|raspbian|neon|deepin|mx|pureos) echo debian; return ;;
            fedora|rhel|centos|rocky|almalinux|nobara|ol|ultramarine|bazzite) echo fedora; return ;;
            opensuse*|suse|sles|sled) echo suse; return ;;
            void) echo void; return ;;
            gentoo|funtoo) echo gentoo; return ;;
            nixos) echo nixos; return ;;
            alpine|postmarketos) echo alpine; return ;;
        esac
    done
    echo desconocida
}

paquetes_python() {
    case "$1" in
        arch) echo "python" ;;
        debian) echo "python3 python3-venv" ;;
        fedora) echo "python3" ;;
        suse) echo "python3 python3-pip" ;;
        void) echo "python3 python3-pip" ;;
        *) echo "" ;;
    esac
}

orden_paquetes() {  # texto de la orden, para mostrarla
    case "$1" in
        arch) echo "sudo pacman -S --needed $2" ;;
        debian) echo "sudo apt install $2" ;;
        fedora) echo "sudo dnf install $2" ;;
        suse) echo "sudo zypper install $2" ;;
        void) echo "sudo xbps-install -S $2" ;;
        gentoo) echo "sudo emerge --ask --noreplace $2" ;;
        *) echo "(instala con tu gestor de paquetes: $2)" ;;
    esac
}

_instalar() {  # $1 = gestor, resto = paquetes
    gestor=$1
    shift
    case "$gestor" in
        arch) como_root pacman -S --needed --noconfirm "$@" ;;
        debian) como_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
        fedora) como_root dnf install -y "$@" ;;
        suse) como_root zypper --non-interactive install "$@" ;;
        void) como_root xbps-install -y "$@" ;;
        *) return 1 ;;
    esac
}

# Instala paquetes (ya confirmado por el usuario). Si la instalación conjunta
# falla (un nombre que no existe en esta versión de la distribución hace que
# apt, pacman o zypper rechacen todo), se reintenta uno a uno.
instalar_paquetes() {  # $1 = familia, resto = paquetes
    gestor=$1
    shift
    case "$gestor" in
        debian) como_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq || true ;;
        void) como_root xbps-install -S >/dev/null || true ;;
    esac
    _instalar "$gestor" "$@" && return 0
    [ $# -gt 1 ] || return 1
    aviso "La instalación conjunta falló; se prueba paquete a paquete."
    fallidos=""
    for paquete in "$@"; do
        _instalar "$gestor" "$paquete" >/dev/null 2>&1 || fallidos="$fallidos $paquete"
    done
    if [ -n "$fallidos" ]; then
        aviso "No se pudieron instalar:$fallidos"
        return 1
    fi
}

# --- Python -------------------------------------------------------------------
python_valido() {  # >= 3.10 y con venv + ensurepip
    "$1" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1
}

buscar_python() {
    if [ -n "$PYTHON" ]; then
        if python_valido "$PYTHON"; then command -v "$PYTHON" || echo "$PYTHON"; fi
        return 0
    fi
    for p in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
        if hay "$p" && python_valido "$p"; then
            command -v "$p"
            return 0
        fi
    done
}

version_python() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true; }

origen_ajustelab() {
    if [ -n "$DESDE" ]; then
        printf '%s' "$DESDE"
        return
    fi
    # Ejecutado como fichero dentro del repositorio: se instala esa copia.
    # Con «curl | sh», $0 es «sh» y no hay fichero: se descarga de GitHub.
    if [ -f "$0" ]; then
        dir=$(cd "$(dirname "$0")" && pwd)
        if [ -f "$dir/pyproject.toml" ] && grep -q '^name = "ajustelab"' "$dir/pyproject.toml"; then
            printf '%s' "$dir"
            return
        fi
    fi
    printf '%s' "$REPO/archive/refs/heads/$RAMA.tar.gz"
}

# Lanzador pequeño delante del entorno: si una actualización del sistema cambia la
# versión de Python (habitual en Arch), el entorno deja de funcionar; en vez de
# fallar en silencio desde el menú, avisa (también con una notificación) de cómo
# repararlo.
escribir_lanzador() {  # $1 = ajustelab | ajustelab-cli
    venv_citado=$(printf '%s' "$VENV" | sed "s/'/'\\\\''/g")
    cat >"$DESTINO/bin/$1" <<FIN
#!/bin/sh
# Lanzador generado por instalar.sh de ajustelab: se regenera en cada instalación.
VENV='$venv_citado'
if "\$VENV/bin/python" -c '' >/dev/null 2>&1 && [ -x "\$VENV/bin/$1" ]; then
    exec "\$VENV/bin/$1" "\$@"
fi
mensaje="El entorno de ajustelab ya no funciona (suele pasar cuando se actualiza el Python del sistema). Repáralo volviendo a ejecutar el instalador: curl -fsSL $URL_INSTALADOR | sh"
printf 'ajustelab: %s\n' "\$mensaje" >&2
if [ ! -t 2 ] && command -v notify-send >/dev/null 2>&1; then
    notify-send -a ajustelab -i dialog-warning "ajustelab no puede arrancar" "\$mensaje"
fi
exit 1
FIN
    chmod 755 "$DESTINO/bin/$1"
}

anadir_al_path() {
    # shellcheck disable=SC2016  # las líneas se escriben literales: $HOME se expande al abrir la shell
    case "$(basename "${SHELL:-sh}")" in
        zsh) rc="${ZDOTDIR:-$HOME}/.zshrc"; linea='export PATH="$HOME/.local/bin:$PATH"' ;;
        bash) rc="$HOME/.bashrc"; linea='export PATH="$HOME/.local/bin:$PATH"' ;;
        fish) rc="${XDG_CONFIG_HOME:-$HOME/.config}/fish/conf.d/ajustelab.fish"; linea='fish_add_path -g $HOME/.local/bin' ;;
        *) rc="$HOME/.profile"; linea='export PATH="$HOME/.local/bin:$PATH"' ;;
    esac
    if [ -f "$rc" ] && grep -q '# ajustelab: ~/.local/bin' "$rc"; then
        aviso "Ya está en $rc: abre una terminal nueva para que se aplique."
        return
    fi
    if preguntar "$BIN no está en el PATH. ¿Añadirlo a $rc?" s; then
        mkdir -p "$(dirname "$rc")"
        printf '\n# ajustelab: ~/.local/bin en el PATH\n%s\n' "$linea" >>"$rc"
        ok "Añadido a $rc. Abre una terminal nueva (o ejecuta ahora: $linea)."
    else
        aviso "Para usar «ajustelab» desde la terminal, añade a $rc: $linea"
        aviso "Desde el menú de aplicaciones funciona igualmente."
    fi
}

# --- instalar -----------------------------------------------------------------------
instalar() {
    [ "$(uname -s)" = Linux ] || fallo "Este instalador es para Linux. En Windows y macOS sigue el README."
    familia=$(detectar_familia)
    paso "Sistema: $(leer_os_release PRETTY_NAME) (familia $familia, $(uname -m))"
    case "$familia" in
        alpine) fallo "Alpine usa musl, y PySide6 (Qt para Python) solo publica paquetes para glibc. Usa una distribución con glibc (o distrobox)." ;;
        nixos) fallo "En NixOS los paquetes de PyPI no encuentran las bibliotecas del sistema. Usa python3Packages.pyside6 de nixpkgs o activa programs.nix-ld y vuelve a ejecutar." ;;
    esac

    paso "Python"
    py=$(buscar_python)
    if [ -z "$py" ]; then
        paquetes=$(paquetes_python "$familia")
        if [ -n "$paquetes" ] && preguntar "Falta Python >= 3.10 con venv. ¿Instalar «$paquetes»?" s; then
            # shellcheck disable=SC2086  # lista de paquetes separada por espacios
            instalar_paquetes "$familia" $paquetes || fallo "No se pudo instalar Python."
            py=$(buscar_python)
        fi
    fi
    if [ -z "$py" ]; then
        if [ -n "$PYTHON" ]; then fallo "$PYTHON no es Python >= 3.10 con el módulo venv."; fi
        p=$(paquetes_python "$familia")
        fallo "Hace falta Python >= 3.10 con el módulo venv. Instálalo (${p:+$(orden_paquetes "$familia" "$p")}) y vuelve a ejecutar este script."
    fi
    ok "Python $(version_python "$py") ($py)"

    paso "Entorno en $VENV"
    if [ -e "$VENV" ]; then
        if [ "$(version_python "$VENV/bin/python")" != "$(version_python "$py")" ]; then
            aviso "El entorno usa otra versión de Python o se ha roto (¿actualización del sistema?): se vuelve a crear."
            rm -rf "$VENV"
        fi
    fi
    if [ ! -e "$VENV" ]; then
        mkdir -p "$DESTINO"
        "$py" -m venv "$VENV" || fallo "No se pudo crear el entorno virtual con $py."
        ok "Creado"
    else
        ok "Ya existía: se actualiza"
    fi
    "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip ||
        aviso "No se pudo actualizar pip; se sigue con el que hay."

    origen=$(origen_ajustelab)
    paso "Instalando ajustelab desde $origen"
    echo "  La primera vez se descargan unos 200 MB (Qt, SciPy, SymPy…): puede tardar unos minutos."
    "$VENV/bin/python" -m pip uninstall --quiet --yes ajustelab >/dev/null 2>&1 || true
    "$VENV/bin/python" -m pip install --disable-pip-version-check --progress-bar on "$origen" ||
        fallo "pip no pudo instalar ajustelab. Revisa la conexión a Internet y vuelve a intentarlo."
    ok "$("$VENV/bin/ajustelab" --version)"

    paso "Órdenes en $BIN"
    mkdir -p "$BIN" "$DESTINO/bin"
    for orden in ajustelab ajustelab-cli; do
        escribir_lanzador "$orden"
        destino="$BIN/$orden"
        if [ -e "$destino" ] || [ -L "$destino" ]; then
            actual=$(readlink "$destino" 2>/dev/null || true)
            case "$actual" in
                "$DESTINO/bin/$orden"|"$VENV/bin/$orden") ;;
                *pipx*) aviso "Sustituyo el $orden de pipx (quítalo con «pipx uninstall ajustelab»)." ;;
                *) aviso "Sustituyo $destino de una instalación anterior." ;;
            esac
            rm -f "$destino"
        fi
        ln -s "$DESTINO/bin/$orden" "$destino"
    done
    ok "ajustelab y ajustelab-cli"
    case ":$PATH:" in
        *":$BIN:"*) ok "$BIN está en el PATH" ;;
        *) anadir_al_path ;;
    esac

    if [ "$CON_DEPS" = 1 ]; then
        paso "Bibliotecas del sistema que usa Qt"
        faltan=$("$VENV/bin/ajustelab" --paquetes-sistema 2>/dev/null || true)
        if [ -z "$faltan" ]; then
            if [ "$familia" = desconocida ]; then
                aviso "Distribución no reconocida: revisa el diagnóstico de abajo."
            else
                ok "No falta ninguna"
            fi
        elif [ "$familia" = gentoo ]; then
            aviso "Faltan: $faltan. Instálalos con: $(orden_paquetes gentoo "$faltan")"
        elif preguntar "Faltan paquetes que usa Qt: $faltan. ¿Instalarlos ahora?" s; then
            # shellcheck disable=SC2086  # lista de paquetes separada por espacios
            if instalar_paquetes "$familia" $faltan; then ok "Instalados"; else aviso "No se pudieron instalar."; fi
        else
            aviso "Sin ellos puede fallar al abrir la ventana. Instálalos luego con: $(orden_paquetes "$familia" "$faltan")"
        fi
    fi

    if [ "$CON_MENU" = 1 ]; then
        paso "Menú de aplicaciones"
        if "$VENV/bin/ajustelab" --instalar-escritorio >/dev/null; then
            ok "ajustelab aparece en el menú, con icono; las sesiones .ajustelab se abren con doble clic"
        else
            aviso "No se pudo añadir al menú (prueba luego: ajustelab --instalar-escritorio)."
        fi
    fi

    paso "Comprobación"
    estado=0
    if QT_QPA_PLATFORM=offscreen "$VENV/bin/ajustelab" --probar-interfaz >/dev/null 2>&1; then
        ok "La interfaz carga correctamente"
    else
        estado=1
        aviso "La interfaz no arranca. Diagnóstico:"
        "$VENV/bin/ajustelab" --diagnostico | sed 's/^/    /' || true
    fi
    if [ "$familia" = desconocida ] && [ "$estado" = 0 ]; then
        "$VENV/bin/ajustelab" --diagnostico | sed 's/^/    /' || true
    fi

    if [ "$estado" = 0 ]; then
        printf '\n%s¡Listo!%s Abre ajustelab desde el menú de aplicaciones o escribe «ajustelab» en una terminal.\n' "$VERDE" "$NORMAL"
    else
        printf '\n%sajustelab está instalado, pero la ventana no arranca.%s Instala lo que indica la\n' "$AMARILLO" "$NORMAL"
        echo "  «Solución» del diagnóstico y vuelve a ejecutar este instalador. ajustelab-cli sí funciona."
    fi
    echo "  Actualizar:   vuelve a ejecutar este instalador"
    echo "  Problemas:    ajustelab --diagnostico"
    if [ -f "$0" ]; then
        echo "  Desinstalar:  sh $0 --desinstalar"
    else
        echo "  Desinstalar:  curl -fsSL $URL_INSTALADOR | sh -s -- --desinstalar"
    fi
    case "$(basename "${SHELL:-sh}")" in
        zsh) echo "  (En zsh, si la orden no aparece en esta terminal, ejecuta «rehash».)" ;;
    esac
    return "$estado"
}

# --- desinstalar ----------------------------------------------------------------
desinstalar() {
    paso "Desinstalando ajustelab"
    if [ -x "$VENV/bin/ajustelab" ]; then
        "$VENV/bin/ajustelab" --desinstalar-escritorio >/dev/null 2>&1 || true
    fi
    # Por si el entorno ya no funciona: los mismos ficheros, a mano
    rm -f "$DATOS/applications/ajustelab.desktop" "$DATOS/mime/packages/ajustelab.xml" \
        "$DATOS/icons/hicolor/scalable/apps/ajustelab.svg"
    for n in 16 24 32 48 64 128 256 512; do
        rm -f "$DATOS/icons/hicolor/${n}x$n/apps/ajustelab.png"
    done
    if hay update-mime-database && [ -d "$DATOS/mime" ]; then update-mime-database "$DATOS/mime" >/dev/null 2>&1 || true; fi
    if hay update-desktop-database; then update-desktop-database -q "$DATOS/applications" >/dev/null 2>&1 || true; fi
    ok "Entrada del menú, iconos y tipo de fichero"

    for orden in ajustelab ajustelab-cli; do
        destino="$BIN/$orden"
        if [ -L "$destino" ]; then
            case "$(readlink "$destino")" in
                "$DESTINO/bin/$orden"|"$VENV/bin/$orden") rm -f "$destino" ;;
            esac
        fi
    done
    ok "Órdenes de $BIN"
    rm -rf "$DESTINO"
    ok "Entorno ($DESTINO)"

    configuracion="${XDG_CONFIG_HOME:-$HOME/.config}/WetZap"
    if [ -d "$configuracion" ] && preguntar "¿Borrar también tus ajustes ($configuracion)?" n; then
        rm -rf "$configuracion"
        ok "Ajustes"
    fi
    echo
    echo "ajustelab se ha desinstalado. Tus datos y sesiones .ajustelab no se han tocado."
    echo "Si el instalador añadió ~/.local/bin al PATH, la línea marcada con «# ajustelab» sigue en tu"
    echo "fichero de arranque de la shell (puede quedarse: lo usan otros programas)."
}

principal() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -y|--si|--sí|--yes) SI=1 ;;
            --sin-dependencias) CON_DEPS=0 ;;
            --sin-menu) CON_MENU=0 ;;
            --python) [ $# -ge 2 ] || fallo "--python necesita una ruta"; PYTHON=$2; shift ;;
            --python=*) PYTHON=${1#*=} ;;
            --desde) [ $# -ge 2 ] || fallo "--desde necesita un origen"; DESDE=$2; shift ;;
            --desde=*) DESDE=${1#*=} ;;
            --rama) [ $# -ge 2 ] || fallo "--rama necesita un nombre"; RAMA=$2; shift ;;
            --rama=*) RAMA=${1#*=} ;;
            --desinstalar) ACCION=desinstalar ;;
            -h|--ayuda|--help) ayuda; exit 0 ;;
            *) fallo "Opción desconocida: $1 (usa --ayuda)" ;;
        esac
        shift
    done
    [ -n "${HOME:-}" ] || fallo "La variable HOME no está definida."
    "$ACCION"
}

# Todo va dentro de funciones y la llamada está al final: con «curl | sh» la shell
# no ejecuta nada hasta haber leído el script completo (una descarga cortada no
# deja una instalación a medias). La entrada estándar se cierra para que ningún
# programa se coma el resto del script; las preguntas usan /dev/tty.
principal "$@" </dev/null
