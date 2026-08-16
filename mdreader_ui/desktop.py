"""Integracion con el escritorio: lanzador, icono y asociacion de archivos.

Esto es lo que hace que el doble click funcione. Tres piezas:

  1. un `.desktop` que declara `MimeType=text/markdown` y recibe rutas con %F
  2. el icono en el tema hicolor
  3. `xdg-mime default`, que le dice al escritorio que este es EL programa
     para abrir Markdown

`text/markdown` ya viene registrado en el shared-mime-info de Fedora y no
tiene handler por defecto, asi que no se le pisa el lugar a nadie.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .icons import icon_pixmap

__all__ = ["install_desktop_entry", "uninstall_desktop_entry", "APP_ID"]

APP_ID = "mdreader"

MIME_TYPES = ("text/markdown", "text/x-markdown")

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

TEMPLATE = """[Desktop Entry]
Type=Application
Version=1.0
Name=mdreader
GenericName=Lector de Markdown
Comment=Lee archivos Markdown con indice, imagenes y navegacion entre documentos
Exec={exec_line} %F
Icon={app_id}
Terminal=false
Categories=Office;Viewer;
MimeType={mimetypes}
Keywords=markdown;md;lector;documento;readme;
StartupNotify=true
StartupWMClass={app_id}
"""


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def applications_dir() -> Path:
    return Path(os.environ.get("MDREADER_APPLICATIONS_DIR") or (_data_home() / "applications"))


def icons_root() -> Path:
    return Path(os.environ.get("MDREADER_ICON_ROOT") or (_data_home() / "icons" / "hicolor"))


def desktop_file() -> Path:
    return applications_dir() / f"{APP_ID}.desktop"


def _exec_line() -> str:
    """Comando que va en Exec=.

    Se prefiere la variable que pone el instalador: apunta al lanzador estable
    de ~/.local/bin y no al ejecutable del venv, que puede moverse.
    """
    override = os.environ.get("MDREADER_EXEC")
    if override:
        return override
    launcher = Path.home() / ".local" / "bin" / APP_ID
    if launcher.exists():
        return str(launcher)
    return sys.argv[0] if sys.argv and sys.argv[0] else APP_ID


def _run(args: list[str]) -> None:
    """Corre una herramienta del escritorio si esta. Nunca es fatal."""
    if shutil.which(args[0]) is None:
        return
    try:
        subprocess.run(args, check=False, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


def install_desktop_entry(*, set_default: bool = True) -> list[Path]:
    """Escribe lanzador e iconos. Devuelve lo que dejo en disco."""
    written: list[Path] = []

    apps = applications_dir()
    apps.mkdir(parents=True, exist_ok=True)
    target = desktop_file()
    target.write_text(
        TEMPLATE.format(
            exec_line=_exec_line(),
            app_id=APP_ID,
            mimetypes=";".join(MIME_TYPES) + ";",
        ),
        encoding="utf-8",
    )
    target.chmod(0o755)
    written.append(target)

    for size in ICON_SIZES:
        directory = icons_root() / f"{size}x{size}" / "apps"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{APP_ID}.png"
        icon_pixmap(size).save(str(path), "PNG")
        written.append(path)

    _run(["update-desktop-database", str(apps)])
    _run(["gtk-update-icon-cache", "-tqf", str(icons_root())])

    if set_default:
        for mime in MIME_TYPES:
            _run(["xdg-mime", "default", f"{APP_ID}.desktop", mime])

    return written


def uninstall_desktop_entry() -> list[Path]:
    removed: list[Path] = []

    target = desktop_file()
    if target.exists():
        target.unlink()
        removed.append(target)

    for size in ICON_SIZES:
        path = icons_root() / f"{size}x{size}" / "apps" / f"{APP_ID}.png"
        if path.exists():
            path.unlink()
            removed.append(path)

    _run(["update-desktop-database", str(applications_dir())])
    _run(["gtk-update-icon-cache", "-tqf", str(icons_root())])
    return removed
