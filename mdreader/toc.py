"""Encabezados y arbol del indice.

El indice se arma en el mismo paso que el render (ver render.py): recorrer los
tokens una sola vez evita tener que parsear el HTML despues para encontrar los
headings, que es fragil en cuanto aparece HTML crudo dentro del Markdown.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

__all__ = ["Heading", "TocNode", "SlugAllocator", "slugify", "build_tree"]


@dataclass(frozen=True)
class Heading:
    """Un encabezado del documento, ya con su ancla asignada."""

    level: int
    text: str
    anchor: str


@dataclass
class TocNode:
    """Nodo del arbol del indice."""

    heading: Heading
    children: list["TocNode"] = field(default_factory=list)


_NON_WORD = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACES = re.compile(r"[-\s]+")


def slugify(text: str) -> str:
    """Convierte el texto de un heading en un ancla estable para la URL.

    Se normaliza a NFKD y se descartan los diacriticos para que "Instalación" y
    "Instalacion" den la misma ancla: los links `#instalacion` escritos a mano
    siguen funcionando, que es como los escribe la mayoria.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = _NON_WORD.sub("", ascii_text).strip().lower()
    slug = _SPACES.sub("-", cleaned)
    return slug or "section"


class SlugAllocator:
    """Reparte anclas unicas dentro de un documento.

    Dos headings con el mismo texto son comunes ("Ejemplo", "Notas"). El segundo
    recibe `-1`, el tercero `-2`, igual que GitHub, para que los links no
    apunten siempre al primero.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def allocate(self, text: str) -> str:
        base = slugify(text)
        seen = self._counts.get(base, 0)
        self._counts[base] = seen + 1
        return base if seen == 0 else f"{base}-{seen}"


def build_tree(headings: list[Heading]) -> list[TocNode]:
    """Anida los headings por nivel.

    Tolera documentos que arrancan en h2 o que saltan niveles (h1 -> h3), que es
    lo normal en READMEs reales. Un salto no crea niveles intermedios falsos:
    el h3 simplemente cuelga del h1.
    """
    roots: list[TocNode] = []
    stack: list[TocNode] = []

    for heading in headings:
        node = TocNode(heading=heading)

        while stack and stack[-1].heading.level >= heading.level:
            stack.pop()

        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)

        stack.append(node)

    return roots
