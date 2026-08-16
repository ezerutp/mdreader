"""Saneado del HTML crudo embebido en el Markdown.

Por que existe: el parser corre con `html: True` porque sin eso los READMEs
reales se ven rotos -- `<p align="center">`, `<details>`, `<img>` con ancho,
badges. Pero un `.md` asociado al doble click puede venir de cualquier lado, y
el documento se renderiza dentro de un motor Chromium con JavaScript activo
(lo necesitan Mermaid y KaTeX). Sin filtro, un `<script>` dentro de un `.md`
correria con los mismos permisos que la UI.

El filtro es por lista blanca, no negra: lo que no esta explicitamente
permitido se escapa y se muestra como texto. Es la unica forma que no envejece
mal, porque no depende de haber enumerado todos los vectores.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

__all__ = ["sanitize_html", "ALLOWED_TAGS"]

# Etiquetas que aportan al diseño de un documento y no ejecutan nada.
ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "col",
        "colgroup", "dd", "del", "details", "div", "dl", "dt", "em", "figcaption",
        "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
        "kbd", "li", "mark", "ol", "p", "picture", "pre", "q", "s", "samp",
        "section", "small", "source", "span", "strong", "sub", "summary", "sup",
        "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var",
    }
)

# Etiquetas cuyo contenido tambien se descarta. Sin esto, escapar solo el
# `<script>` dejaria el codigo JavaScript visible como texto en la pagina.
DROP_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "template"})

VOID_TAGS = frozenset({"br", "hr", "img", "col", "source"})

_GLOBAL_ATTRS = frozenset({"id", "class", "title", "align", "dir", "lang", "style"})

_TAG_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "name", "target", "rel"}),
    "img": frozenset({"src", "alt", "width", "height", "loading", "srcset"}),
    "source": frozenset({"src", "srcset", "type", "media"}),
    "td": frozenset({"colspan", "rowspan", "valign"}),
    "th": frozenset({"colspan", "rowspan", "valign", "scope"}),
    "col": frozenset({"span", "width"}),
    "colgroup": frozenset({"span"}),
    "ol": frozenset({"start", "type", "reversed"}),
    "details": frozenset({"open"}),
    "del": frozenset({"datetime"}),
    "ins": frozenset({"datetime"}),
}

# Esquemas aceptados en href/src. `data:` solo para imagenes: `data:text/html`
# es una via directa a ejecutar HTML arbitrario con el origen de la pagina.
_SAFE_SCHEMES = frozenset({"http", "https", "mailto", "file", "tel", ""})

_URL_ATTRS = frozenset({"href", "src", "srcset"})


def _safe_url(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()

    if lowered.startswith("data:"):
        return lowered.startswith("data:image/")

    # Un "\n" en el medio de "java\nscript:" lo colapsa el navegador.
    collapsed = "".join(lowered.split())
    if collapsed.startswith(("javascript:", "vbscript:")):
        return False

    try:
        scheme = urlparse(stripped).scheme.lower()
    except ValueError:
        return False
    return scheme in _SAFE_SCHEMES


def _safe_style(value: str) -> bool:
    lowered = "".join(value.lower().split())
    return not any(bad in lowered for bad in ("javascript:", "expression(", "@import", "behavior:"))


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        # convert_charrefs=False conserva las entidades tal cual las escribio el
        # autor (&nbsp;, &copy;) en vez de resolverlas y volver a escaparlas.
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self._suppress_depth = 0
        self._suppressing: str | None = None

    # -- helpers -------------------------------------------------------------

    def _emit(self, text: str) -> None:
        if self._suppressing is None:
            self.out.append(text)

    def _clean_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = _GLOBAL_ATTRS | _TAG_ATTRS.get(tag, frozenset())
        parts: list[str] = []

        for name, value in attrs:
            name = name.lower()
            if name.startswith("on"):
                continue
            if name not in allowed:
                continue
            if value is None:
                parts.append(name)
                continue
            if name in _URL_ATTRS and not _safe_url(value):
                continue
            if name == "style" and not _safe_style(value):
                continue
            parts.append(f'{name}="{escape(value, quote=True)}"')

        return (" " + " ".join(parts)) if parts else ""

    # -- callbacks -----------------------------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()

        if self._suppressing is not None:
            if tag == self._suppressing:
                self._suppress_depth += 1
            return

        if tag in DROP_CONTENT_TAGS:
            self._suppressing = tag
            self._suppress_depth = 1
            return

        if tag not in ALLOWED_TAGS:
            # No se borra: se muestra tal cual lo escribio el autor, escapado.
            self.out.append(escape(self.get_starttag_text() or f"<{tag}>"))
            return

        closer = " />" if tag in VOID_TAGS else ">"
        self.out.append(f"<{tag}{self._clean_attrs(tag, attrs)}{closer}")

    def handle_startendtag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self._suppressing is not None:
            return
        if tag not in ALLOWED_TAGS:
            self.out.append(escape(self.get_starttag_text() or f"<{tag}/>"))
            return
        self.out.append(f"<{tag}{self._clean_attrs(tag, attrs)} />")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if self._suppressing is not None:
            if tag == self._suppressing:
                self._suppress_depth -= 1
                if self._suppress_depth <= 0:
                    self._suppressing = None
            return

        if tag not in ALLOWED_TAGS:
            self.out.append(escape(f"</{tag}>"))
            return
        if tag in VOID_TAGS:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._emit(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self._emit(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._emit(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        # Los comentarios se descartan enteros: no aportan al render y son el
        # lugar clasico donde se esconde markup para saltear filtros.
        return


def sanitize_html(fragment: str) -> str:
    """Devuelve el fragmento con solo etiquetas y atributos de la lista blanca.

    Tolera fragmentos incompletos (`<span class="x">` suelto), que es como
    markdown-it entrega los tokens `html_inline`.
    """
    if not fragment:
        return ""
    parser = _Sanitizer()
    try:
        parser.feed(fragment)
        parser.close()
    except Exception:
        # Ante cualquier duda, texto plano: nunca dejar pasar el crudo.
        return escape(fragment)
    return "".join(parser.out)
