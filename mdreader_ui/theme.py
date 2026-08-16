"""Tema claro/oscuro siguiendo al escritorio.

Qt 6.5 expone el esquema de color del sistema en QStyleHints y avisa cuando
cambia, asi que no hace falta hablar con GNOME por dconf ni sondear nada.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

__all__ = ["resolve_theme", "system_theme", "apply_qt_color_scheme", "dark_palette"]


def system_theme() -> str:
    hints = QGuiApplication.styleHints()
    if hints is None:
        return "light"
    try:
        scheme = hints.colorScheme()
    except AttributeError:
        return "light"
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def resolve_theme(preference: str) -> str:
    """Convierte la preferencia guardada en el tema concreto a aplicar."""
    if preference in ("light", "dark"):
        return preference
    return system_theme()


def apply_qt_color_scheme(preference: str) -> None:
    """Pone el marco de la aplicacion en el mismo tema que el documento.

    Sin esto, forzar el tema oscuro deja el documento oscuro pero el indice, la
    barra y las pestañas claras, que se ve peor que no tener la opcion.

    Se hace en dos pasos porque `setColorScheme` depende del tema de la
    plataforma: bajo GNOME lo respeta, pero con otros estilos (o sin tema de
    plataforma) no repinta nada. La paleta explicita garantiza el resultado en
    cualquier caso; en "system" se limpia para volver a seguir al escritorio.
    """
    app = QGuiApplication.instance()
    hints = QGuiApplication.styleHints()

    if hints is not None and hasattr(hints, "setColorScheme"):
        hints.setColorScheme(
            {
                "dark": Qt.ColorScheme.Dark,
                "light": Qt.ColorScheme.Light,
            }.get(preference, Qt.ColorScheme.Unknown)
        )

    if app is None:
        return

    effective = resolve_theme(preference)
    if effective == "dark":
        app.setPalette(dark_palette())
    else:
        # Volver al default del estilo en vez de inventar una paleta clara:
        # asi se respeta el tema de iconos y acentos del escritorio.
        app.setPalette(QPalette())


def dark_palette() -> QPalette:
    """Paleta oscura alineada con los tokens de reader.css."""
    bg = QColor("#1b1d21")
    base = QColor("#131417")
    text = QColor("#e3e6ea")
    muted = QColor("#7d8792")
    accent = QColor("#3b6fd4")

    palette = QPalette()
    roles = QPalette.ColorRole
    groups = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive)

    for group in groups:
        palette.setColor(group, roles.Window, bg)
        palette.setColor(group, roles.WindowText, text)
        palette.setColor(group, roles.Base, base)
        palette.setColor(group, roles.AlternateBase, QColor("#202329"))
        palette.setColor(group, roles.Text, text)
        palette.setColor(group, roles.Button, bg)
        palette.setColor(group, roles.ButtonText, text)
        palette.setColor(group, roles.ToolTipBase, bg)
        palette.setColor(group, roles.ToolTipText, text)
        palette.setColor(group, roles.Highlight, accent)
        palette.setColor(group, roles.HighlightedText, QColor("#ffffff"))
        palette.setColor(group, roles.Link, QColor("#6ea8fe"))
        palette.setColor(group, roles.PlaceholderText, muted)

    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, roles.WindowText, muted)
    palette.setColor(disabled, roles.Text, muted)
    palette.setColor(disabled, roles.ButtonText, muted)
    return palette
