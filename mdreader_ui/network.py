"""Bloqueo de peticiones remotas.

Abrir un `.md` no deberia generar trafico hacia afuera. Un documento con
`![](https://tracker/pixel.png)` le avisa al que lo escribio que lo abriste,
desde que IP y cuando. Por eso todo lo que no sea local se corta, y el permiso
se concede por documento con un boton.

Cuidado con los hilos: en Qt 6 el interceptor del perfil corre en el hilo de
I/O, no en el de la GUI. Por eso el permiso no se lee del ReaderState (que
muta desde la GUI) sino de un frozenset que se reemplaza entero: leer un
atributo y preguntar por pertenencia sobre un objeto inmutable es seguro sin
tener que tomar un lock en cada request.
"""

from __future__ import annotations

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from mdreader.page import ASSET_SCHEME

__all__ = ["RemoteBlocker"]

# Esquemas que nunca salen a la red.
LOCAL_SCHEMES = frozenset({"file", ASSET_SCHEME, "data", "blob", "qrc", "about"})

REMOTE_SCHEMES = frozenset({"http", "https", "ftp", "ws", "wss"})


class RemoteBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._allowed: frozenset[str] = frozenset()

    def set_allowed(self, paths: set[str]) -> None:
        """Reemplaza el conjunto de documentos con permiso. Llamar desde la GUI."""
        self._allowed = frozenset(paths)

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:  # noqa: N802
        scheme = info.requestUrl().scheme().lower()

        if scheme in LOCAL_SCHEMES:
            return

        if scheme in REMOTE_SCHEMES:
            first_party = info.firstPartyUrl().toLocalFile()
            if first_party and first_party in self._allowed:
                return
            info.block(True)
            return

        # Un esquema desconocido no tiene por que llegar hasta aca.
        info.block(True)
