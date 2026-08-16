"""Punto de entrada.

Instancia unica: la segunda invocacion no levanta otra ventana, le pasa las
rutas a la que ya esta corriendo y sale. Sin esto, abrir ocho `.md` desde el
explorador levantaria ocho procesos con su propio Chromium adentro.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

__all__ = ["main"]

VERSION = "0.1.0"


def _server_name() -> str:
    # Por usuario: dos sesiones distintas en la misma maquina no se pisan.
    return f"mdreader-{os.getuid()}"


def _forward_to_running(paths: list[Path]) -> bool:
    """Le pasa las rutas a la instancia viva. True si habia una."""
    from PySide6.QtCore import QByteArray
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(400):
        return False

    payload = json.dumps([str(p) for p in paths]) + "\n"
    socket.write(QByteArray(payload.encode("utf-8")))
    socket.flush()
    socket.waitForBytesWritten(2000)
    socket.disconnectFromServer()
    return True


class _Listener:
    """Recibe rutas de las invocaciones siguientes."""

    def __init__(self, window) -> None:
        from PySide6.QtNetwork import QLocalServer

        self._window = window
        self._buffers: dict[object, bytearray] = {}
        self._server = QLocalServer()
        # Un cierre sucio (kill -9, cuelgue) deja el socket huerfano y el
        # listen falla para siempre. Se limpia antes de escuchar.
        QLocalServer.removeServer(_server_name())
        self._server.listen(_server_name())
        self._server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        self._buffers[socket] = bytearray()
        socket.readyRead.connect(lambda s=socket: self._on_ready(s))
        socket.disconnected.connect(lambda s=socket: self._finish(s))

    def _on_ready(self, socket) -> None:
        buffer = self._buffers.get(socket)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll().data()))
        if b"\n" in buffer:
            self._finish(socket)

    def _finish(self, socket) -> None:
        buffer = self._buffers.pop(socket, None)
        socket.deleteLater()
        if not buffer:
            return
        try:
            paths = json.loads(bytes(buffer).split(b"\n", 1)[0].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if isinstance(paths, list):
            self._window.open_paths([Path(str(p)) for p in paths])
        self._raise_window()

    def _raise_window(self) -> None:
        window = self._window
        window.setWindowState(
            (window.windowState() & ~_minimized()) | _active()
        )
        window.show()
        window.raise_()
        window.activateWindow()


def _minimized():
    from PySide6.QtCore import Qt

    return Qt.WindowState.WindowMinimized


def _active():
    from PySide6.QtCore import Qt

    return Qt.WindowState.WindowActive


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mdreader", description="Lector de Markdown de escritorio."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="archivos .md a abrir")
    parser.add_argument("--version", action="version", version=f"mdreader {VERSION}")
    parser.add_argument(
        "--install-desktop-entry",
        action="store_true",
        help="registra el lanzador, el icono y la asociacion con .md",
    )
    parser.add_argument(
        "--uninstall-desktop-entry",
        action="store_true",
        help="quita el lanzador y los iconos",
    )
    parser.add_argument(
        "--no-default-handler",
        action="store_true",
        help="con --install-desktop-entry: no se pone como handler por defecto",
    )
    parser.add_argument(
        "--no-single-instance",
        action="store_true",
        help="fuerza una ventana nueva en vez de reusar la que ya corre",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    # Las tareas de escritorio no necesitan levantar la interfaz entera, pero
    # si una QGuiApplication: el icono se dibuja con QPainter.
    if args.install_desktop_entry or args.uninstall_desktop_entry:
        from PySide6.QtGui import QGuiApplication

        from .desktop import install_desktop_entry, uninstall_desktop_entry

        _app = QGuiApplication(["mdreader"])
        if args.uninstall_desktop_entry:
            for path in uninstall_desktop_entry():
                print(f"quitado  {path}")
        else:
            for path in install_desktop_entry(set_default=not args.no_default_handler):
                print(f"escrito  {path}")
        return 0

    paths = [p for p in args.paths]

    if not args.no_single_instance and _forward_to_running(paths):
        return 0

    # El esquema de assets tiene que registrarse antes de la QApplication:
    # Chromium congela la tabla de esquemas cuando arranca.
    from .assets import AssetSchemeHandler, register_asset_scheme

    register_asset_scheme()

    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWidgets import QApplication

    from mdreader.page import ASSET_SCHEME
    from mdreader.state import ReaderState

    from .icons import app_icon
    from .network import RemoteBlocker
    from .theme import apply_qt_color_scheme, resolve_theme
    from .window import MainWindow

    QApplication.setApplicationName("mdreader")
    QApplication.setApplicationDisplayName("mdreader")
    QApplication.setDesktopFileName("mdreader")
    QApplication.setOrganizationName("mdreader")

    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())

    profile = QWebEngineProfile.defaultProfile()
    handler = AssetSchemeHandler(app)
    profile.installUrlSchemeHandler(ASSET_SCHEME.encode("ascii"), handler)

    blocker = RemoteBlocker(app)
    profile.setUrlRequestInterceptor(blocker)

    state = ReaderState()
    window = MainWindow(state, blocker)

    # Mantener referencias vivas: sin esto el recolector se lleva el handler
    # y el interceptor, y el motor queda apuntando a memoria liberada.
    window._asset_handler = handler  # noqa: SLF001

    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(lambda _s: window.on_system_theme_changed())
    apply_qt_color_scheme(state.prefs.theme)
    window.apply_theme(resolve_theme(state.prefs.theme))

    listener = None
    if not args.no_single_instance:
        listener = _Listener(window)
        window._listener = listener  # noqa: SLF001

    window.show()
    if paths:
        window.open_paths(paths)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
