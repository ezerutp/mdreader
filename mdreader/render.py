"""Markdown -> HTML.

Este modulo produce SOLO el fragmento HTML del cuerpo y los metadatos del
documento. El armado de la pagina completa (tema, CSS, scripts) vive en
page.py, y la vista Qt en mdreader_ui.

Esa separacion es a proposito: hoy la vista es scroll continuo, pero paginar
mas adelante es cambiar la hoja de estilos de page.py sin tocar el parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any
from urllib.parse import urlparse

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.gfm import gfm_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from .sanitize import sanitize_html
from .toc import Heading, SlugAllocator, TocNode, build_tree

__all__ = ["RenderResult", "MarkdownRenderer", "PYGMENTS_CSS_CLASS"]

PYGMENTS_CSS_CLASS = "highlight"

# Los fences con estos nombres no se colorean: los dibuja Mermaid en el cliente.
MERMAID_LANGS = frozenset({"mermaid"})

# Esquemas que se consideran "de la maquina". El resto es red y entra en el
# conteo de recursos remotos que la UI bloquea por defecto.
LOCAL_SCHEMES = frozenset({"", "file", "data"})


@dataclass
class RenderResult:
    """Resultado de renderizar un documento."""

    html: str
    headings: list[Heading] = field(default_factory=list)
    toc: list[TocNode] = field(default_factory=list)
    front_matter: dict[str, Any] = field(default_factory=dict)
    front_matter_raw: str = ""
    has_math: bool = False
    has_mermaid: bool = False
    remote_images: int = 0

    @property
    def title(self) -> str | None:
        """Titulo del documento: el del front matter, o el primer h1."""
        declared = self.front_matter.get("title")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
        for heading in self.headings:
            if heading.level == 1:
                return heading.text
        return None


def _parse_front_matter(raw: str) -> dict[str, Any]:
    """Parsea el bloque YAML de cabecera.

    Nunca revienta: un front matter malformado se muestra crudo en vez de
    tirar abajo el documento entero.
    """
    if not raw.strip():
        return {}
    try:
        import yaml

        data = yaml.safe_load(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


class MarkdownRenderer:
    """Convierte Markdown a HTML.

    Es reutilizable entre documentos: el estado por documento (anclas, conteos)
    vive en variables locales de `render`, no en la instancia.
    """

    def __init__(self, *, pygments_style: str = "default") -> None:
        self._formatter = HtmlFormatter(
            style=pygments_style, cssclass=PYGMENTS_CSS_CLASS, nowrap=False
        )
        self._md = self._build_parser()

    # -- construccion del parser --------------------------------------------

    def _build_parser(self) -> MarkdownIt:
        md = MarkdownIt("commonmark", {"linkify": True, "html": True})
        # gfm_plugin trae tablas, tachado, task lists, autolinks y notas al pie.
        # dollarmath y front_matter se piden explicitos.
        md.use(gfm_plugin, dollarmath=True, front_matter=True)
        md.enable("linkify")
        md.add_render_rule("fence", self._render_fence)
        # El HTML crudo del documento pasa por la lista blanca antes de llegar
        # al motor. Ver sanitize.py para el por que.
        md.add_render_rule("html_block", self._render_html)
        md.add_render_rule("html_inline", self._render_html)
        return md

    def _render_html(self, tokens: list[Token], idx: int, options, env) -> str:
        return sanitize_html(tokens[idx].content)

    # -- reglas de render ----------------------------------------------------

    def _render_fence(self, tokens: list[Token], idx: int, options, env) -> str:
        token = tokens[idx]
        info = (token.info or "").strip()
        lang = info.split()[0].lower() if info else ""
        code = token.content

        if lang in MERMAID_LANGS:
            # Mermaid lee el texto del <pre> y lo reemplaza por un SVG.
            # Va escapado: hasta que el script corre, es texto plano.
            env["has_mermaid"] = True
            return f'<pre class="mermaid">{escape(code)}</pre>\n'

        if lang:
            try:
                lexer = get_lexer_by_name(lang)
            except ClassNotFound:
                lexer = None
        else:
            lexer = None

        if lexer is None and not lang:
            # Sin lenguaje declarado no se adivina: guess_lexer sobre tres
            # lineas acierta poco y colorea mal, que se nota mas que no colorear.
            return (
                f'<div class="{PYGMENTS_CSS_CLASS} no-lang">'
                f"<pre><code>{escape(code)}</code></pre></div>\n"
            )

        if lexer is None:
            # Lenguaje declarado pero desconocido (```jsonc, ```hcl viejo...).
            try:
                lexer = guess_lexer(code)
            except ClassNotFound:
                return (
                    f'<div class="{PYGMENTS_CSS_CLASS} no-lang">'
                    f"<pre><code>{escape(code)}</code></pre></div>\n"
                )

        rendered = highlight(code, lexer, self._formatter)
        label = escape(lang) if lang else ""
        return f'<div class="code-block" data-lang="{label}">{rendered}</div>\n'

    # -- recorrido de tokens -------------------------------------------------

    def _assign_anchors(self, tokens: list[Token]) -> list[Heading]:
        """Pone un id unico en cada heading y devuelve la lista para el indice.

        Muta los tokens antes de renderizar, que es la unica forma de que el id
        del HTML y el ancla del indice no puedan divergir.
        """
        allocator = SlugAllocator()
        headings: list[Heading] = []

        for i, token in enumerate(tokens):
            if token.type != "heading_open":
                continue
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline.content.strip() if inline is not None else ""
            # El texto del indice va sin marcas: `## **Config**` se lee "Config".
            plain = _plain_text(inline) if inline is not None else text
            anchor = allocator.allocate(plain or text)
            token.attrSet("id", anchor)
            headings.append(
                Heading(level=int(token.tag[1:]), text=plain or text, anchor=anchor)
            )

        return headings

    def _scan(self, tokens: list[Token], result: RenderResult) -> None:
        """Recolecta front matter, math y recursos remotos."""
        for token in tokens:
            if token.type == "front_matter":
                result.front_matter_raw = token.content
                result.front_matter = _parse_front_matter(token.content)
            elif token.type in ("math_inline", "math_block", "math_inline_double"):
                result.has_math = True
            elif token.type == "fence" and (token.info or "").strip().lower() in MERMAID_LANGS:
                result.has_mermaid = True

            if token.children:
                self._scan(token.children, result)

            if token.type == "image":
                src = token.attrGet("src") or ""
                if _is_remote(str(src)):
                    result.remote_images += 1

    # -- API -----------------------------------------------------------------

    def render(self, text: str) -> RenderResult:
        env: dict[str, Any] = {}
        tokens = self._md.parse(text, env)

        result = RenderResult(html="")
        self._scan(tokens, result)
        result.headings = self._assign_anchors(tokens)
        result.toc = build_tree(result.headings)
        result.html = self._md.renderer.render(tokens, self._md.options, env)

        if env.get("has_mermaid"):
            result.has_mermaid = True

        return result

    def pygments_css(self) -> str:
        return self._formatter.get_style_defs(f".{PYGMENTS_CSS_CLASS}")


def _plain_text(inline: Token) -> str:
    """Texto de un token inline sin marcas ni HTML.

    `## Instalar **rapido**` -> "Instalar rapido".
    """
    if not inline.children:
        return inline.content.strip()
    parts: list[str] = []
    for child in inline.children:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type == "image":
            parts.append(child.attrGet("alt") or "")
        elif child.children:
            parts.append(_plain_text(child))
    return "".join(parts).strip()


def _is_remote(src: str) -> bool:
    """True si el recurso sale a la red."""
    try:
        scheme = urlparse(src).scheme.lower()
    except ValueError:
        return False
    if src.startswith("//"):
        return True
    return scheme not in LOCAL_SCHEMES
