"""Panel del indice.

Muestra el arbol de encabezados del documento activo y sigue el scroll: la
seccion que estas leyendo queda resaltada. El seguimiento se apaga mientras
navegas a mano, para que la vista del arbol no salte debajo del cursor.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from mdreader.render import RenderResult
from mdreader.toc import TocNode

__all__ = ["TocSidebar"]

ANCHOR_ROLE = Qt.ItemDataRole.UserRole


class TocSidebar(QWidget):
    anchorActivated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: dict[str, QTreeWidgetItem] = {}
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._empty = QLabel("Sin encabezados")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setEnabled(False)
        self._empty.setContentsMargins(12, 24, 12, 24)
        self._empty.setWordWrap(True)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setUniformRowHeights(True)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.itemClicked.connect(self._on_clicked)
        self._tree.itemActivated.connect(self._on_clicked)

        layout.addWidget(self._empty)
        layout.addWidget(self._tree)
        self._show_empty(True)

    # -- contenido -----------------------------------------------------------

    def set_document(self, result: RenderResult | None) -> None:
        self._tree.clear()
        self._items.clear()

        if result is None or not result.toc:
            self._show_empty(True)
            return

        self._show_empty(False)
        for node in result.toc:
            self._tree.addTopLevelItem(self._build(node))
        self._tree.expandAll()

    def _build(self, node: TocNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.heading.text or "(sin titulo)"])
        item.setData(0, ANCHOR_ROLE, node.heading.anchor)
        item.setToolTip(0, node.heading.text)
        self._items[node.heading.anchor] = item
        for child in node.children:
            item.addChild(self._build(child))
        return item

    def _show_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._tree.setVisible(not empty)

    # -- interaccion ---------------------------------------------------------

    def _on_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._syncing:
            return
        anchor = item.data(0, ANCHOR_ROLE)
        if anchor:
            self.anchorActivated.emit(str(anchor))

    def highlight(self, anchor: str) -> None:
        """Marca la seccion activa sin disparar la señal de click."""
        item = self._items.get(anchor)
        if item is None:
            return
        self._syncing = True
        try:
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item, QTreeWidget.ScrollHint.EnsureVisible)
        finally:
            self._syncing = False
