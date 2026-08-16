"""Icono de la aplicacion, dibujado en tiempo de ejecucion.

Se dibuja en vez de guardar un PNG en el repo por lo mismo que los assets se
descargan: el repositorio no guarda binarios. Ademas escala a cualquier tamaño
que pida el escritorio sin quedar borroso.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

__all__ = ["app_icon", "icon_pixmap"]

_PAPER = QColor("#ffffff")
_EDGE = QColor("#c9d1d9")
_ACCENT = QColor("#2f6feb")
_INK = QColor("#3d444d")


def icon_pixmap(size: int = 256) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    unit = size / 256.0
    sheet = QRectF(38 * unit, 20 * unit, 180 * unit, 216 * unit)
    fold = 46 * unit

    # Hoja con la esquina superior derecha doblada.
    body = QPainterPath()
    body.moveTo(sheet.left(), sheet.top())
    body.lineTo(sheet.right() - fold, sheet.top())
    body.lineTo(sheet.right(), sheet.top() + fold)
    body.lineTo(sheet.right(), sheet.bottom())
    body.lineTo(sheet.left(), sheet.bottom())
    body.closeSubpath()

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_PAPER))
    painter.drawPath(body)

    corner = QPainterPath()
    corner.moveTo(sheet.right() - fold, sheet.top())
    corner.lineTo(sheet.right(), sheet.top() + fold)
    corner.lineTo(sheet.right() - fold, sheet.top() + fold)
    corner.closeSubpath()
    painter.setBrush(QBrush(_EDGE))
    painter.drawPath(corner)

    # Franja de color: la marca del lector.
    painter.setBrush(QBrush(_ACCENT))
    painter.drawRect(QRectF(sheet.left(), sheet.bottom() - 40 * unit, sheet.width(), 40 * unit))

    # Renglones que sugieren texto.
    painter.setBrush(QBrush(_INK))
    for index, width in enumerate((0.78, 0.62, 0.70, 0.45)):
        top = sheet.top() + (74 + index * 26) * unit
        painter.drawRoundedRect(
            QRectF(sheet.left() + 22 * unit, top, sheet.width() * width - 30 * unit, 9 * unit),
            4 * unit,
            4 * unit,
        )

    # "M" de Markdown sobre la franja.
    font = QFont()
    font.setBold(True)
    font.setPixelSize(int(30 * unit))
    painter.setFont(font)
    painter.setPen(_PAPER)
    painter.drawText(
        QRectF(sheet.left(), sheet.bottom() - 41 * unit, sheet.width(), 40 * unit),
        Qt.AlignmentFlag.AlignCenter,
        "MD",
    )

    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon
