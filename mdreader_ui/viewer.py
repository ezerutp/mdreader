"""La vista de un documento: motor web, puente, recarga y navegacion.

Un DocumentView es una pestaña. Tiene su propio historial (los links a otros
`.md` navegan adentro), su propio watcher para el live reload y su propio
permiso de imagenes remotas.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from mdreader.page import PageBuilder, PageOptions
from mdreader.render import MarkdownRenderer, RenderResult
from mdreader.state import ReaderState

__all__ = ["DocumentView", "MARKDOWN_SUFFIXES"]

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkd", ".mdwn", ".mkdn"})

# Los editores guardan de formas distintas: algunos escriben en el lugar, otros
# renombran encima. Un margen chico agrupa la rafaga de eventos y evita
# renderizar un archivo a medio escribir.
RELOAD_DEBOUNCE_MS = 180


class Bridge(QObject):
    """Objeto expuesto al documento por QWebChannel."""

    activeHeadingChanged = Signal(str)
    scrollChanged = Signal(float)
    documentReady = Signal()

    @Slot(str)
    def setActiveHeading(self, anchor: str) -> None:
        self.activeHeadingChanged.emit(anchor)

    @Slot(float)
    def setScroll(self, value: float) -> None:
        self.scrollChanged.emit(value)

    @Slot()
    def ready(self) -> None:
        self.documentReady.emit()


class ReaderPage(QWebEnginePage):
    """Decide que hacer con cada navegacion.

    Nada sale del lector por accidente: los links externos van al navegador del
    sistema, los `.md` se abren adentro y cualquier otra cosa se delega al
    escritorio.
    """

    internalLinkClicked = Signal(Path)
    externalLinkClicked = Signal(QUrl)

    def acceptNavigationRequest(  # noqa: N802 (API de Qt)
        self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
            return True

        if not is_main_frame:
            return False

        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            # setHtml() entra por aca como NavigationTypeOther y tiene que pasar.
            return True

        scheme = url.scheme().lower()

        if scheme in ("http", "https", "mailto", "tel"):
            self.externalLinkClicked.emit(url)
            return False

        if scheme == "file":
            path = Path(url.toLocalFile())
            if path.suffix.lower() in MARKDOWN_SUFFIXES:
                self.internalLinkClicked.emit(path)
            else:
                # Un PDF, una imagen o una carpeta: que lo abra quien
                # corresponda segun el escritorio.
                self.externalLinkClicked.emit(url)
            return False

        return False

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:  # noqa: N802
        # Silencio: los documentos no deberian ensuciar la salida de la app.
        return


class DocumentView(QWebEngineView):
    """Una pestaña: un documento, su historial y su estado."""

    titleResolved = Signal(str)
    tocChanged = Signal(object)          # RenderResult
    activeHeadingChanged = Signal(str)
    remoteBlockedChanged = Signal(int, bool)  # cantidad, permitido
    pathChanged = Signal(Path)
    historyChanged = Signal(bool, bool)  # puede atras, puede adelante

    def __init__(
        self,
        state: ReaderState,
        renderer: MarkdownRenderer,
        builder: PageBuilder,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._renderer = renderer
        self._builder = builder

        self.path: Path | None = None
        self.result: RenderResult | None = None
        self._back: list[Path] = []
        self._forward: list[Path] = []
        self._scroll = 0.0
        self._pending_scroll = 0.0
        self._theme = "light"
        self._full_width = False
        self._loaded = False
        self._pending_scripts: list[str] = []

        self._page = ReaderPage(self)
        self.setPage(self._page)
        self._configure_settings()

        self._bridge = Bridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._bridge.activeHeadingChanged.connect(self.activeHeadingChanged)
        self._bridge.scrollChanged.connect(self._on_scroll)
        self._page.internalLinkClicked.connect(self.navigate_to)
        self._page.externalLinkClicked.connect(QDesktopServices.openUrl)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)

        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self._reload_from_disk)

        self.loadFinished.connect(self._on_load_finished)

    # -- configuracion -------------------------------------------------------

    def _configure_settings(self) -> None:
        settings = self._page.settings()
        A = QWebEngineSettings.WebAttribute
        # JavaScript hace falta para KaTeX, Mermaid y el indice. Lo que llega
        # del documento ya paso por la lista blanca de sanitize.py.
        settings.setAttribute(A.JavascriptEnabled, True)
        # Un documento no tiene por que leer otros archivos del disco.
        settings.setAttribute(A.LocalContentCanAccessFileUrls, False)
        # Tiene que estar en True, aunque suene al reves: la pagina se carga con
        # un origen file: y KaTeX/Mermaid se sirven por `mdasset:`, que para
        # Chromium no es local. En False, esos dos scripts nunca se piden.
        # Quien decide sobre la red sigue siendo RemoteBlocker, que corta todo
        # http(s) salvo que el usuario lo habilite para ese documento; este
        # atributo no lo puede saltear.
        settings.setAttribute(A.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(A.JavascriptCanOpenWindows, False)
        settings.setAttribute(A.JavascriptCanAccessClipboard, False)
        settings.setAttribute(A.AllowRunningInsecureContent, False)
        settings.setAttribute(A.ScreenCaptureEnabled, False)
        settings.setAttribute(A.WebGLEnabled, False)
        settings.setAttribute(A.PdfViewerEnabled, False)
        settings.setAttribute(A.FullScreenSupportEnabled, False)
        settings.setAttribute(A.LocalStorageEnabled, False)
        settings.setAttribute(A.ErrorPageEnabled, False)
        settings.setAttribute(A.ScrollAnimatorEnabled, True)

    # -- carga ---------------------------------------------------------------

    def open_path(self, path: Path, *, remember_history: bool = True) -> bool:
        path = Path(path).expanduser()
        try:
            path = path.resolve(strict=True)
        except OSError:
            return False

        if remember_history and self.path is not None and self.path != path:
            self._back.append(self.path)
            self._forward.clear()

        self._set_path(path)
        return self._render_current(restore=True)

    def navigate_to(self, path: Path) -> None:
        self.open_path(path, remember_history=True)

    def go_back(self) -> None:
        if not self._back:
            return
        if self.path is not None:
            self._forward.append(self.path)
        target = self._back.pop()
        self._set_path(target)
        self._render_current(restore=True)

    def go_forward(self) -> None:
        if not self._forward:
            return
        if self.path is not None:
            self._back.append(self.path)
        target = self._forward.pop()
        self._set_path(target)
        self._render_current(restore=True)

    def _set_path(self, path: Path) -> None:
        old = self._watcher.files()
        if old:
            self._watcher.removePaths(old)
        self.path = path
        self._watcher.addPath(str(path))
        self.pathChanged.emit(path)
        self._emit_history()

    def _emit_history(self) -> None:
        self.historyChanged.emit(bool(self._back), bool(self._forward))

    def _render_current(self, *, restore: bool) -> bool:
        if self.path is None:
            return False
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.setHtml(f"<p>No se pudo leer el archivo: {exc}</p>")
            return False

        self.result = self._renderer.render(text)

        doc_state = self._state.get(self.path)
        self._pending_scroll = doc_state.scroll if restore else self._scroll

        title = self.result.title or self.path.stem
        html = self._builder.build(
            self.result,
            PageOptions(theme=self._theme, full_width=self._full_width, title=title),
        )

        # baseUrl es la URL del archivo, no la del directorio: asi las imagenes
        # y los links relativos resuelven igual que los resolveria un navegador
        # abriendo ese mismo archivo.
        self._loaded = False
        self._pending_scripts.clear()
        self.setHtml(html, QUrl.fromLocalFile(str(self.path)))

        self._state.remember(self.path, opened_at=time.time())
        self._state.push_recent(self.path)

        self.titleResolved.emit(title)
        self.tocChanged.emit(self.result)
        allowed = self._state.get(self.path).allow_remote
        self.remoteBlockedChanged.emit(self.result.remote_images, allowed)
        return True

    # -- live reload ---------------------------------------------------------

    @Slot(str)
    def _on_file_changed(self, _path: str) -> None:
        self._reload_timer.start()

    def _reload_from_disk(self) -> None:
        if self.path is None:
            return
        # Guardar con rename (vim, la mayoria de los editores) borra el inode
        # que estaba vigilado y QFileSystemWatcher suelta la ruta. Hay que
        # volver a engancharla o el segundo guardado ya no dispara nada.
        if str(self.path) not in self._watcher.files() and self.path.exists():
            self._watcher.addPath(str(self.path))

        if not self.path.exists():
            return

        # restore=False mantiene la posicion actual en vez de la guardada:
        # editar y guardar no debe saltar a otro lado.
        self._render_current(restore=False)

    # -- estado --------------------------------------------------------------

    @Slot(float)
    def _on_scroll(self, value: float) -> None:
        self._scroll = value
        if self.path is not None:
            self._state.remember(self.path, scroll=value)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        self._loaded = True
        pending, self._pending_scripts = self._pending_scripts, []
        for script in pending:
            self._page.runJavaScript(script)
        self.set_theme(self._theme)
        if self._pending_scroll > 0.0:
            self._run(f"window.mdreader.restoreScroll({self._pending_scroll});")
            self._pending_scroll = 0.0

    def _run(self, script: str) -> None:
        """Ejecuta en el documento, o lo encola si todavia no cargo.

        La ventana configura tema y ancho apenas crea la pestaña, antes de que
        el motor haya evaluado reader.js. Sin la cola, esas llamadas explotan
        contra un `window.mdreader` que todavia no existe.
        """
        if not self._loaded:
            self._pending_scripts.append(script)
            return
        self._page.runJavaScript(script)

    # -- API para la ventana -------------------------------------------------

    def scroll_to_anchor(self, anchor: str) -> None:
        safe = anchor.replace("\\", "\\\\").replace('"', '\\"')
        self._run(f'window.mdreader.scrollToAnchor("{safe}");')

    def set_theme(self, theme: str) -> None:
        self._theme = "dark" if theme == "dark" else "light"
        self._run(f'window.mdreader.setTheme("{self._theme}");')

    def set_full_width(self, on: bool) -> None:
        self._full_width = bool(on)
        self._run(f"window.mdreader.setFullWidth({'true' if on else 'false'});")

    def allow_remote_images(self) -> None:
        if self.path is None:
            return
        self._state.remember(self.path, allow_remote=True)
        self._render_current(restore=False)

    def can_go_back(self) -> bool:
        return bool(self._back)

    def can_go_forward(self) -> bool:
        return bool(self._forward)
