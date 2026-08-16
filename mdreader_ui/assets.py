"""Servidor interno de assets bajo el esquema `mdasset:`.

KaTeX pesa 550 KB entre JS, CSS y fuentes; Mermaid 2,6 MB. Inlinearlos en cada
render haria que el live reload se sintiera lento y le impediria al motor
cachear nada. Servirlos por un esquema propio los deja cacheados como
cualquier recurso y, de paso, hace que las URLs relativas a las fuentes que
trae la CSS de KaTeX resuelvan solas.

El esquema tiene que registrarse ANTES de crear la QApplication: Chromium
congela la tabla de esquemas al arrancar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

from mdreader.page import ASSET_SCHEME, assets_dir

__all__ = ["register_asset_scheme", "AssetSchemeHandler"]

_MIME = {
    ".js": b"application/javascript",
    ".css": b"text/css",
    ".woff2": b"font/woff2",
    ".woff": b"font/woff",
    ".ttf": b"font/ttf",
    ".svg": b"image/svg+xml",
    ".png": b"image/png",
    ".json": b"application/json",
}


def register_asset_scheme() -> None:
    """Registra `mdasset:`. Llamar antes de instanciar QApplication."""
    scheme = QWebEngineUrlScheme(ASSET_SCHEME.encode("ascii"))
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class AssetSchemeHandler(QWebEngineUrlSchemeHandler):
    """Sirve archivos de mdreader/assets/ y nada mas."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = assets_dir().resolve()

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802 (API de Qt)
        requested = job.requestUrl().path().lstrip("/")
        target = self._resolve(requested)

        if target is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        try:
            data = target.read_bytes()
        except OSError:
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return

        buffer = QBuffer(job)
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(_MIME.get(target.suffix.lower(), b"application/octet-stream"), buffer)

    def _resolve(self, relative: str) -> Path | None:
        """Resuelve dentro de assets/ o devuelve None.

        El `resolve()` mas la comprobacion de prefijo cortan el recorrido de
        directorios: `mdasset:/../../../etc/passwd` no sale de assets/.
        """
        if not relative:
            return None
        try:
            candidate = (self._root / relative).resolve()
        except OSError:
            return None
        if not candidate.is_relative_to(self._root):
            return None
        if not candidate.is_file():
            return None
        return candidate
