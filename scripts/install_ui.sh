#!/usr/bin/env bash
# Instala mdreader para el usuario actual: su propio virtualenv bajo
# ~/.local/share, un comando `mdreader` en ~/.local/bin, un lanzador en la
# lista de aplicaciones y la asociacion con los archivos .md.
# Sin root (salvo que pidas --use-dnf o --use-apt) y sin tocar nada fuera de
# ~/.local.
#
# Sobre PySide6: este proyecto necesita QtWebEngine, que vive en
# PySide6-Addons y no en PySide6-Essentials. Hay tres caminos y el script
# prefiere el del sistema si esta disponible:
#
#   1. RPM python3-pyside6 de Fedora: ya trae QtWebEngineWidgets, usa el Qt
#      del sistema y se actualiza con dnf. El venv se crea con
#      --system-site-packages para verlo.
#   2. paquetes python3-pyside6.* de Debian/Ubuntu: mismo trato, pero
#      repartido en varios .deb (uno por modulo de Qt) que hay que pedir
#      juntos.
#   3. pip install PySide6: ~250 MB dentro del venv, sin sudo.
set -Eeuo pipefail

APP_NAME="mdreader"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
APP_INSTALL_DIR="${APP_INSTALL_DIR:-$HOME/.local/share/$APP_NAME}"
APPLICATIONS_DIR="${APPLICATIONS_DIR:-$HOME/.local/share/applications}"
ICON_ROOT="${ICON_ROOT:-$HOME/.local/share/icons/hicolor}"
STATE_DIR="${STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/$APP_NAME}"
SKIP_TESTS="${SKIP_TESTS:-0}"

VENV="$APP_INSTALL_DIR/venv"
LAUNCHER="$INSTALL_DIR/$APP_NAME"
DESKTOP_FILE="$APPLICATIONS_DIR/$APP_NAME.desktop"

QT_SOURCE="auto"      # auto | dnf | apt | pip

# Modulos de Qt que usa el codigo (mdreader_ui/*.py): QtCore, QtGui,
# QtWidgets, QtNetwork, QtWebChannel, QtWebEngineCore, QtWebEngineWidgets.
# En Debian/Ubuntu cada uno es un .deb aparte y apt no siempre arrastra los
# que no son dependencia dura de QtWebEngineWidgets (QtNetwork, QtWebChannel),
# asi que se piden todos explicitamente.
APT_PACKAGES=(
  python3-pyside6.qtcore
  python3-pyside6.qtgui
  python3-pyside6.qtwidgets
  python3-pyside6.qtnetwork
  python3-pyside6.qtwebchannel
  python3-pyside6.qtwebenginecore
  python3-pyside6.qtwebenginewidgets
)
SET_DEFAULT=1

log()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'aviso: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------

usage() {
  cat <<EOF
uso: $0 [opciones]

  --use-dnf            instala python3-pyside6 con dnf (pide sudo) y lo reusa
  --use-apt            instala python3-pyside6.* con apt-get (pide sudo) y lo reusa
  --use-pip            fuerza PySide6 por pip dentro del venv (~250 MB)
  --no-default-handler no se registra como programa por defecto para .md
  --uninstall          quita todo lo instalado
  -h, --help           esta ayuda

Entorno: PYTHON_BIN, INSTALL_DIR, APP_INSTALL_DIR, APPLICATIONS_DIR,
         ICON_ROOT, SKIP_TESTS=1
EOF
}

refresh_desktop_caches() {
  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -tqf "$ICON_ROOT" >/dev/null 2>&1 || true
}

uninstall() {
  log "Quitando $APP_NAME"
  pkill -f "$VENV/bin/$APP_NAME" 2>/dev/null || true

  if [ -x "$VENV/bin/$APP_NAME" ]; then
    MDREADER_APPLICATIONS_DIR="$APPLICATIONS_DIR" MDREADER_ICON_ROOT="$ICON_ROOT" \
      "$VENV/bin/$APP_NAME" --uninstall-desktop-entry >/dev/null 2>&1 || true
  fi

  rm -rf "$APP_INSTALL_DIR"
  rm -f "$LAUNCHER" "$DESKTOP_FILE"
  rm -f "$ICON_ROOT"/*/apps/"$APP_NAME".png
  refresh_desktop_caches

  printf '\nEliminado:\n  %s\n  %s\n  %s\n' "$APP_INSTALL_DIR" "$LAUNCHER" "$DESKTOP_FILE"
  printf '\nLa posicion de lectura guardada en %s quedo intacta.\n' "$STATE_DIR"
  printf 'Borrala con: rm -rf %s\n' "$STATE_DIR"
}

ensure_python() {
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "no se encontro $PYTHON_BIN. Defini PYTHON_BIN."
  "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "$PYTHON_BIN es anterior al Python 3.10 requerido."
}

# Devuelve 0 si el interprete del sistema ya tiene QtWebEngine.
system_has_webengine() {
  "$PYTHON_BIN" -c 'import PySide6.QtWebEngineWidgets' >/dev/null 2>&1
}

setup_venv() {
  log "Creando el virtualenv en $VENV"
  mkdir -p "$APP_INSTALL_DIR"
  rm -rf "$VENV"

  local use_system=0

  case "$QT_SOURCE" in
    dnf)
      command -v dnf >/dev/null 2>&1 || die "--use-dnf pero no hay dnf en el sistema"
      log "Instalando python3-pyside6 (trae QtWebEngine, usa el Qt del sistema)"
      sudo dnf install -y python3-pyside6
      system_has_webengine || die "python3-pyside6 quedo instalado pero $PYTHON_BIN no lo ve"
      use_system=1
      ;;
    apt)
      command -v apt-get >/dev/null 2>&1 || die "--use-apt pero no hay apt-get en el sistema"
      log "Instalando ${APT_PACKAGES[*]} (trae QtWebEngine, usa el Qt del sistema)"
      sudo apt-get install -y "${APT_PACKAGES[@]}"
      system_has_webengine || die "los paquetes quedaron instalados pero $PYTHON_BIN no ve QtWebEngine"
      use_system=1
      ;;
    pip)
      use_system=0
      ;;
    auto)
      if system_has_webengine; then
        log "QtWebEngine ya disponible en el sistema: se reusa"
        use_system=1
      else
        log "Sin QtWebEngine en el sistema: se instala PySide6 por pip (~250 MB)"
        if command -v dnf >/dev/null 2>&1; then
          printf '     (mas liviano: %s --use-dnf, que instala python3-pyside6)\n' "$0"
        elif command -v apt-get >/dev/null 2>&1; then
          printf '     (mas liviano: %s --use-apt, que instala python3-pyside6.*)\n' "$0"
        fi
        use_system=0
      fi
      ;;
  esac

  if [ "$use_system" -eq 1 ]; then
    "$PYTHON_BIN" -m venv --system-site-packages "$VENV"
  else
    "$PYTHON_BIN" -m venv "$VENV"
  fi

  "$VENV/bin/python" -m pip install --upgrade pip --quiet

  # setuptools reusa build/lib entre builds y no borra lo que dejo de existir:
  # sin esta limpieza, un paquete renombrado se cuela con su nombre viejo.
  rm -rf "$PROJECT_ROOT/build/lib" "$PROJECT_ROOT/build/bdist."* "$PROJECT_ROOT"/*.egg-info

  if [ "$use_system" -eq 1 ]; then
    log "Instalando $APP_NAME (sin Qt: ya esta en el sistema)"
    "$VENV/bin/python" -m pip install --quiet "$PROJECT_ROOT"
  else
    log "Instalando $APP_NAME y PySide6"
    "$VENV/bin/python" -m pip install --quiet "$PROJECT_ROOT[ui]"
  fi

  "$VENV/bin/python" -c 'import PySide6.QtWebEngineWidgets' \
    || die "QtWebEngine no quedo disponible en el venv"
}

fetch_assets() {
  # KaTeX y Mermaid no se pueden servir por CDN: el lector bloquea la red por
  # defecto, asi que se bajan una vez y quedan dentro del paquete.
  log "Descargando KaTeX y Mermaid (~3 MB)"

  if ! "$VENV/bin/python" "$PROJECT_ROOT/scripts/fetch_assets.py"; then
    warn "no se pudieron descargar: las formulas se veran como TeX y los"
    warn "diagramas como codigo. Volve a correr el instalador con red."
    return 0
  fi

  # El `cd /` no es cosmetico: `python -c` mete el cwd en sys.path, asi que
  # parado en el checkout `import mdreader` resuelve al paquete del repo y no
  # al instalado en el venv. Sin esto, origen y destino son el mismo directorio
  # y el cp falla.
  local target
  target="$(cd / && "$VENV/bin/python" -c \
    'import mdreader, pathlib; print(pathlib.Path(mdreader.__file__).parent)')"

  local src="$PROJECT_ROOT/mdreader/assets/vendor"
  local dst="$target/assets/vendor"

  if [ "$(readlink -f "$src")" = "$(readlink -f "$dst")" ]; then
    printf '  ya estan en su destino (%s)\n' "$dst"
    return 0
  fi

  # Se borra primero: con el destino ya existente, `cp -r src dir/` anida y
  # deja vendor/vendor. Ademas saca los archivos de una version anterior.
  rm -rf "$dst"
  mkdir -p "$target/assets"
  cp -r "$src" "$target/assets/"
  printf '  copiados a %s\n' "$dst"
}

run_tests() {
  [ "$SKIP_TESTS" = "1" ] && return 0
  log "Corriendo las pruebas"
  (cd "$PROJECT_ROOT" && env PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
    "$VENV/bin/python" -m unittest discover -s tests -t . -q)
}

install_launcher() {
  log "Escribiendo el lanzador en $LAUNCHER"
  mkdir -p "$INSTALL_DIR"
  cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/$APP_NAME" "\$@"
EOF
  chmod +x "$LAUNCHER"
}

register_desktop() {
  log "Registrando la aplicacion y la asociacion con .md"
  mkdir -p "$APPLICATIONS_DIR" "$ICON_ROOT"

  local args=(--install-desktop-entry)
  [ "$SET_DEFAULT" -eq 1 ] || args+=(--no-default-handler)

  MDREADER_APPLICATIONS_DIR="$APPLICATIONS_DIR" \
  MDREADER_ICON_ROOT="$ICON_ROOT" \
  MDREADER_EXEC="$LAUNCHER" \
  QT_QPA_PLATFORM=offscreen \
    "$VENV/bin/$APP_NAME" "${args[@]}"

  refresh_desktop_caches

  if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_FILE" && printf '  .desktop valido\n'
  fi
}

report() {
  printf '\nInstalado:\n'
  printf '  comando   %s\n' "$LAUNCHER"
  printf '  lanzador  %s\n' "$DESKTOP_FILE"
  printf '  app       %s\n' "$VENV"

  local handler=""
  command -v xdg-mime >/dev/null 2>&1 && handler="$(xdg-mime query default text/markdown 2>/dev/null || true)"
  printf '  handler   text/markdown -> %s\n' "${handler:-(ninguno)}"

  case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
      printf '\nAgrega esto a tu ~/.zshrc para que `%s` resuelva:\n' "$APP_NAME"
      printf '  export PATH="%s:$PATH"\n' "$INSTALL_DIR"
      ;;
  esac

  printf '\nProbalo: %s %s\n' "$APP_NAME" "$PROJECT_ROOT/tests/fixtures/completo.md"
  printf 'O hace doble click en cualquier .md desde Archivos.\n'
  printf 'Desinstalalo con: %s --uninstall\n' "$0"
}

main() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --use-dnf)            QT_SOURCE="dnf" ;;
      --use-apt)            QT_SOURCE="apt" ;;
      --use-pip)            QT_SOURCE="pip" ;;
      --no-default-handler) SET_DEFAULT=0 ;;
      --uninstall)          uninstall; return 0 ;;
      -h|--help)            usage; return 0 ;;
      *)                    die "argumento desconocido: $1" ;;
    esac
    shift
  done

  ensure_python
  log "Usando $("$PYTHON_BIN" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
  setup_venv
  fetch_assets
  run_tests
  install_launcher
  register_desktop
  report
}

main "$@"
