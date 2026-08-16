"""Armado de la pagina HTML completa.

render.py entrega el cuerpo; aca se le pone el tema, los estilos y los scripts.
La separacion es la que deja la puerta abierta a paginar: una vista paginada
seria otro builder con otra hoja de estilos, con el mismo cuerpo de entrada.

Los assets pesados (KaTeX, Mermaid) no se inlinean: se sirven por el esquema
`mdasset:` que registra la UI. Inlinear 3 MB de Mermaid en cada render haria
que guardar un archivo con live reload se sintiera lento, y el motor no podria
cachear nada entre recargas.
"""

from __future__ import annotations

import html as html_mod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pygments.formatters import HtmlFormatter

from .render import PYGMENTS_CSS_CLASS, RenderResult

__all__ = ["ASSET_SCHEME", "assets_dir", "PageBuilder", "PageOptions"]

ASSET_SCHEME = "mdasset"

LIGHT_STYLE = "friendly"
DARK_STYLE = "github-dark"


def assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"


def vendor_dir() -> Path:
    return assets_dir() / "vendor"


@lru_cache(maxsize=1)
def _read_asset(name: str) -> str:
    try:
        return (assets_dir() / name).read_text(encoding="utf-8")
    except OSError:
        return ""


@lru_cache(maxsize=1)
def _pygments_css() -> str:
    """CSS de Pygments para los dos temas, en una sola hoja.

    El tema oscuro se emite con un prefijo de selector mas especifico, asi
    cambiar de tema es cambiar un atributo en <html> y no recargar la pagina.
    """
    light = HtmlFormatter(style=LIGHT_STYLE, cssclass=PYGMENTS_CSS_CLASS)
    dark = HtmlFormatter(style=DARK_STYLE, cssclass=PYGMENTS_CSS_CLASS)
    return "\n".join(
        [
            light.get_style_defs(f".{PYGMENTS_CSS_CLASS}"),
            dark.get_style_defs(f':root[data-theme="dark"] .{PYGMENTS_CSS_CLASS}'),
        ]
    )


def has_vendor(name: str) -> bool:
    return (vendor_dir() / name).is_file()


@dataclass
class PageOptions:
    theme: str = "light"
    full_width: bool = False
    title: str = "mdreader"


class PageBuilder:
    """Ensambla el documento HTML final."""

    def __init__(self, *, webchannel_js: str = "") -> None:
        # qwebchannel.js lo provee Qt como recurso; la UI lo lee y lo pasa aca
        # para no acoplar este modulo a PySide6 (asi el core se testea sin Qt).
        self._webchannel_js = webchannel_js

    def build(self, result: RenderResult, options: PageOptions) -> str:
        theme = "dark" if options.theme == "dark" else "light"
        body_class = "full-width" if options.full_width else ""

        head_links: list[str] = []
        scripts: list[str] = []

        # KaTeX y Mermaid solo se cargan si el documento los usa. La mayoria de
        # los .md no tienen ni formulas ni diagramas y no deberian pagar por eso.
        if result.has_math and has_vendor("katex.min.css"):
            head_links.append(
                f'<link rel="stylesheet" href="{ASSET_SCHEME}:/vendor/katex.min.css">'
            )
        if result.has_math and has_vendor("katex.min.js"):
            scripts.append(f'<script src="{ASSET_SCHEME}:/vendor/katex.min.js"></script>')
        if result.has_mermaid and has_vendor("mermaid.min.js"):
            scripts.append(f'<script src="{ASSET_SCHEME}:/vendor/mermaid.min.js"></script>')

        if self._webchannel_js:
            scripts.append(f"<script>{self._webchannel_js}</script>")

        parts = [
            "<!doctype html>",
            f'<html lang="es" data-theme="{theme}">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            # Sin conexiones salientes desde el documento. El bloqueo real lo
            # hace el interceptor de Qt; esto es la segunda linea, por si un
            # documento intenta algo que el interceptor no cubre.
            self._csp(result),
            f"<title>{html_mod.escape(options.title)}</title>",
            f"<style>{_read_asset('reader.css')}</style>",
            f"<style>{_pygments_css()}</style>",
            *head_links,
            "</head>",
            f'<body class="{body_class}">',
            '<div class="paper">',
            _front_matter_html(result),
            result.html or '<div class="empty-doc">Documento vacio</div>',
            "</div>",
            *scripts,
            f"<script>{_read_asset('reader.js')}</script>",
            "</body>",
            "</html>",
        ]
        return "\n".join(p for p in parts if p)

    def _csp(self, result: RenderResult) -> str:
        """Content-Security-Policy del documento.

        `img-src` deja pasar http/https porque el permiso por documento se
        gestiona en el interceptor de Qt, que sabe si el usuario apreto
        "cargar imagenes". Lo que se corta duro es todo lo demas: nada de
        scripts externos, nada de frames, nada de formularios.
        """
        directives = [
            f"default-src 'none'",
            f"img-src 'self' file: data: {ASSET_SCHEME}: http: https:",
            f"style-src 'unsafe-inline' {ASSET_SCHEME}:",
            f"font-src {ASSET_SCHEME}: data:",
            f"script-src 'unsafe-inline' {ASSET_SCHEME}: qrc:",
            "frame-src 'none'",
            "object-src 'none'",
            "form-action 'none'",
            "base-uri 'none'",
        ]
        content = "; ".join(directives)
        return f'<meta http-equiv="Content-Security-Policy" content="{content}">'


def _front_matter_html(result: RenderResult) -> str:
    """Muestra el front matter como una ficha arriba del documento."""
    if not result.front_matter_raw.strip():
        return ""

    if not result.front_matter:
        # YAML que no parsea: se muestra crudo en vez de tragarselo.
        escaped = html_mod.escape(result.front_matter_raw.strip())
        return f'<div class="front-matter"><pre>{escaped}</pre></div>'

    rows: list[str] = []
    for key, value in result.front_matter.items():
        rows.append(f"<dt>{html_mod.escape(str(key))}</dt>")
        rows.append(f"<dd>{html_mod.escape(_format_value(value))}</dd>")
    return f'<div class="front-matter"><dl>{"".join(rows)}</dl></div>'


def _format_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_value(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_format_value(v)}" for k, v in value.items())
    if isinstance(value, bool):
        return "si" if value else "no"
    return str(value)
