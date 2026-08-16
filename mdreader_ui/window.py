"""Ventana principal: pestañas, indice y barra de herramientas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from mdreader.page import PageBuilder
from mdreader.render import MarkdownRenderer
from mdreader.state import ReaderState

from .icons import app_icon
from .network import RemoteBlocker
from .sidebar import TocSidebar
from .theme import apply_qt_color_scheme, resolve_theme
from .viewer import MARKDOWN_SUFFIXES, DocumentView

__all__ = ["MainWindow"]

ZOOM_STEPS = (0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)

FILE_FILTER = "Markdown (*.md *.markdown *.mdown *.mkd *.mdwn *.mkdn);;Todos (*)"


class RemoteBanner(QFrame):
    """Aviso de imagenes remotas bloqueadas, con el boton para permitirlas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 8, 7)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self.button = QPushButton("Cargar imagenes")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self._label, 1)
        layout.addWidget(self.button, 0)
        self.hide()

    def update_for(self, count: int, allowed: bool) -> None:
        if count <= 0 or allowed:
            self.hide()
            return
        plural = "es" if count != 1 else ""
        self._label.setText(
            f"{count} imagen{plural} remota{plural} bloqueada{plural}. "
            "Cargarlas le avisa al servidor que abriste este documento."
        )
        self.show()


class WelcomePage(QWidget):
    """Pantalla cuando no hay ningun documento abierto."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(14)

        title = QLabel("mdreader")
        font = title.font()
        font.setPointSize(font.pointSize() + 9)
        font.setBold(True)
        title.setFont(font)

        hint = QLabel("Abri un archivo con Ctrl+O, o hace doble click en un .md.")
        hint.setEnabled(False)

        self.recents = QListWidget()
        self.recents.setFrameShape(QFrame.Shape.NoFrame)
        self.recents.setAlternatingRowColors(True)

        self._recents_label = QLabel("Recientes")
        self._recents_label.setEnabled(False)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(18)
        layout.addWidget(self._recents_label)
        layout.addWidget(self.recents, 1)

    def set_recents(self, paths: list[Path]) -> None:
        self.recents.clear()
        visible = bool(paths)
        self._recents_label.setVisible(visible)
        self.recents.setVisible(visible)
        for path in paths:
            item = QListWidgetItem(f"{path.name}   —   {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.recents.addItem(item)


class MainWindow(QMainWindow):
    def __init__(self, state: ReaderState, blocker: RemoteBlocker) -> None:
        super().__init__()
        self._state = state
        self._blocker = blocker
        self._renderer = MarkdownRenderer()
        self._builder = PageBuilder(webchannel_js=_webchannel_js())
        self._theme = resolve_theme(state.prefs.theme)

        self.setWindowTitle("mdreader")
        self.setWindowIcon(app_icon())
        self.resize(state.prefs.window_width, state.prefs.window_height)
        if state.prefs.window_maximized:
            self.showMaximized()

        self._build_ui()
        self._build_actions()
        self._sync_allowed_paths()
        self._refresh_welcome()

    # -- construccion --------------------------------------------------------

    def _build_ui(self) -> None:
        self._sidebar = TocSidebar()
        self._sidebar.anchorActivated.connect(self._on_anchor)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self.close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._banner = RemoteBanner()
        self._banner.button.clicked.connect(self._on_allow_remote)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._banner)
        right_layout.addWidget(self._tabs, 1)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([260, 840])
        self._splitter.setChildrenCollapsible(False)

        self._welcome = WelcomePage()
        self._welcome.recents.itemActivated.connect(self._on_recent_activated)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._welcome)
        self._stack.addWidget(self._splitter)
        self.setCentralWidget(self._stack)

        self._sidebar.setVisible(self._state.prefs.sidebar_visible)

    def _build_actions(self) -> None:
        bar = QToolBar("Principal")
        bar.setMovable(False)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(bar)

        self._act_back = self._action("‹  Atras", "Alt+Left", self._on_back, bar)
        self._act_forward = self._action("Adelante  ›", "Alt+Right", self._on_forward, bar)
        bar.addSeparator()

        self._act_open = self._action("Abrir", QKeySequence.StandardKey.Open, self.open_dialog, bar)
        bar.addSeparator()

        self._act_sidebar = self._action("Indice", "Ctrl+B", self._toggle_sidebar, bar, checkable=True)
        self._act_sidebar.setChecked(self._state.prefs.sidebar_visible)

        self._act_width = self._action("Ancho completo", "Ctrl+Shift+W", self._toggle_width, bar, checkable=True)
        self._act_theme = self._action(
            _theme_label(self._state.prefs.theme), "Ctrl+Shift+T", self._cycle_theme, bar
        )

        # Sin boton: atajos que no necesitan ocupar la barra.
        self._add_shortcut("Ctrl+W", self._close_current)
        self._add_shortcut(QKeySequence.StandardKey.ZoomIn, lambda: self._zoom(1))
        self._add_shortcut("Ctrl+=", lambda: self._zoom(1))
        self._add_shortcut(QKeySequence.StandardKey.ZoomOut, lambda: self._zoom(-1))
        self._add_shortcut("Ctrl+0", self._zoom_reset)
        self._add_shortcut(QKeySequence.StandardKey.Quit, self.close)
        self._add_shortcut("Ctrl+Tab", lambda: self._cycle_tab(1))
        self._add_shortcut("Ctrl+Shift+Tab", lambda: self._cycle_tab(-1))

        self._update_history_actions(False, False)

    def _action(self, text, shortcut, slot, bar, *, checkable=False) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        bar.addAction(action)
        self.addAction(action)
        return action

    def _add_shortcut(self, shortcut, slot) -> None:
        action = QAction(self)
        action.setShortcut(shortcut)
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action.triggered.connect(slot)
        self.addAction(action)

    # -- documentos ----------------------------------------------------------

    def open_paths(self, paths: list[Path]) -> int:
        opened = 0
        for path in paths:
            if self.open_path(path):
                opened += 1
        return opened

    def open_path(self, path: Path) -> bool:
        path = Path(path).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return False

        # Ya abierto: se trae la pestaña al frente en vez de duplicarla.
        for index in range(self._tabs.count()):
            view = self._tabs.widget(index)
            if isinstance(view, DocumentView) and view.path == resolved:
                self._tabs.setCurrentIndex(index)
                self._show_tabs()
                return True

        view = DocumentView(self._state, self._renderer, self._builder, self)
        view.setZoomFactor(self._state.prefs.zoom)
        view.set_theme(self._theme)
        view.titleResolved.connect(lambda title, v=view: self._on_title(v, title))
        view.tocChanged.connect(lambda result, v=view: self._on_toc(v, result))
        view.activeHeadingChanged.connect(lambda anchor, v=view: self._on_active(v, anchor))
        view.remoteBlockedChanged.connect(lambda n, ok, v=view: self._on_remote(v, n, ok))
        view.historyChanged.connect(lambda b, f, v=view: self._on_history(v, b, f))

        if not view.open_path(resolved):
            view.deleteLater()
            return False

        index = self._tabs.addTab(view, resolved.stem)
        self._tabs.setTabToolTip(index, str(resolved))
        self._tabs.setCurrentIndex(index)
        view.set_full_width(self._act_width.isChecked())
        self._show_tabs()
        return True

    def open_dialog(self) -> None:
        current = self._current_view()
        start = str(current.path.parent) if current and current.path else str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(self, "Abrir Markdown", start, FILE_FILTER)
        self.open_paths([Path(p) for p in paths])

    def close_tab(self, index: int) -> None:
        view = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if isinstance(view, DocumentView):
            view.setParent(None)
            view.deleteLater()
        if self._tabs.count() == 0:
            self._refresh_welcome()
            self._stack.setCurrentWidget(self._welcome)
            self._sidebar.set_document(None)

    def _close_current(self) -> None:
        if self._tabs.count():
            self.close_tab(self._tabs.currentIndex())

    def _cycle_tab(self, step: int) -> None:
        count = self._tabs.count()
        if count < 2:
            return
        self._tabs.setCurrentIndex((self._tabs.currentIndex() + step) % count)

    def _current_view(self) -> DocumentView | None:
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, DocumentView) else None

    def _show_tabs(self) -> None:
        self._stack.setCurrentWidget(self._splitter)

    def _refresh_welcome(self) -> None:
        self._welcome.set_recents(self._state.existing_recent())

    # -- señales de las vistas -----------------------------------------------

    def _on_title(self, view: DocumentView, title: str) -> None:
        index = self._tabs.indexOf(view)
        if index >= 0:
            self._tabs.setTabText(index, title)
        if view is self._current_view():
            self.setWindowTitle(f"{title} — mdreader")

    def _on_toc(self, view: DocumentView, result) -> None:
        if view is self._current_view():
            self._sidebar.set_document(result)

    def _on_active(self, view: DocumentView, anchor: str) -> None:
        if view is self._current_view():
            self._sidebar.highlight(anchor)

    def _on_remote(self, view: DocumentView, count: int, allowed: bool) -> None:
        if view is self._current_view():
            self._banner.update_for(count, allowed)

    def _on_history(self, view: DocumentView, back: bool, forward: bool) -> None:
        if view is self._current_view():
            self._update_history_actions(back, forward)

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        view = self._current_view()
        if view is None:
            self._sidebar.set_document(None)
            self._banner.hide()
            self._update_history_actions(False, False)
            return
        self._sidebar.set_document(view.result)
        self._update_history_actions(view.can_go_back(), view.can_go_forward())
        if view.result is not None and view.path is not None:
            allowed = self._state.get(view.path).allow_remote
            self._banner.update_for(view.result.remote_images, allowed)
        if view.path is not None:
            self.setWindowTitle(f"{self._tabs.tabText(index)} — mdreader")

    def _update_history_actions(self, back: bool, forward: bool) -> None:
        self._act_back.setEnabled(back)
        self._act_forward.setEnabled(forward)

    # -- acciones ------------------------------------------------------------

    def _on_anchor(self, anchor: str) -> None:
        view = self._current_view()
        if view is not None:
            view.scroll_to_anchor(anchor)

    def _on_back(self) -> None:
        view = self._current_view()
        if view is not None:
            view.go_back()

    def _on_forward(self) -> None:
        view = self._current_view()
        if view is not None:
            view.go_forward()

    def _on_recent_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_path(Path(str(path)))

    def _on_allow_remote(self) -> None:
        view = self._current_view()
        if view is None:
            return
        view.allow_remote_images()
        self._sync_allowed_paths()
        self._banner.hide()
        # El permiso lo aplica el interceptor, que ya tiene la ruta: recargar
        # hace que las imagenes se vuelvan a pedir, ahora sin bloqueo.
        view.reload()

    def _sync_allowed_paths(self) -> None:
        allowed = {
            key for key, doc in self._state.documents.items() if doc.allow_remote
        }
        self._blocker.set_allowed(allowed)

    def _toggle_sidebar(self, checked: bool) -> None:
        self._sidebar.setVisible(checked)
        self._state.prefs.sidebar_visible = checked

    def _toggle_width(self, checked: bool) -> None:
        for index in range(self._tabs.count()):
            view = self._tabs.widget(index)
            if isinstance(view, DocumentView):
                view.set_full_width(checked)

    def _cycle_theme(self) -> None:
        order = ("system", "light", "dark")
        current = self._state.prefs.theme
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else "system"
        self._state.prefs.theme = nxt
        apply_qt_color_scheme(nxt)
        self.apply_theme(resolve_theme(nxt))
        self._act_theme.setText(_theme_label(nxt))

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        for index in range(self._tabs.count()):
            view = self._tabs.widget(index)
            if isinstance(view, DocumentView):
                view.set_theme(theme)

    def on_system_theme_changed(self) -> None:
        if self._state.prefs.theme == "system":
            self.apply_theme(resolve_theme("system"))

    def _zoom(self, direction: int) -> None:
        current = self._state.prefs.zoom
        steps = list(ZOOM_STEPS)
        closest = min(range(len(steps)), key=lambda i: abs(steps[i] - current))
        index = max(0, min(len(steps) - 1, closest + direction))
        self._set_zoom(steps[index])

    def _zoom_reset(self) -> None:
        self._set_zoom(1.0)

    def _set_zoom(self, factor: float) -> None:
        self._state.prefs.zoom = factor
        for index in range(self._tabs.count()):
            view = self._tabs.widget(index)
            if isinstance(view, DocumentView):
                view.setZoomFactor(factor)

    # -- cierre --------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._state.prefs.window_maximized = self.isMaximized()
        if not self.isMaximized():
            self._state.prefs.window_width = self.width()
            self._state.prefs.window_height = self.height()
        self._state.save()
        super().closeEvent(event)


def _theme_label(preference: str) -> str:
    return {
        "system": "Tema: sistema",
        "light": "Tema: claro",
        "dark": "Tema: oscuro",
    }.get(preference, "Tema")


def _webchannel_js() -> str:
    """Lee qwebchannel.js del recurso que trae Qt.

    Viene embebido en QtWebChannel; no hay que distribuirlo ni buscarlo en
    disco.
    """
    from PySide6.QtCore import QFile, QIODevice

    handle = QFile(":/qtwebchannel/qwebchannel.js")
    if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    try:
        return bytes(handle.readAll().data()).decode("utf-8", "replace")
    finally:
        handle.close()
