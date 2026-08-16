"""Estado persistente: posicion de lectura por archivo y preferencias.

Vive en `$XDG_STATE_HOME/mdreader/state.json` (por defecto
`~/.local/state/mdreader/`), que es donde el spec XDG pide poner lo que se
puede perder sin romper nada. No va en `~/.config`: si borras esto solo pierde
donde quedaste, no la configuracion.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["ReaderState", "Prefs", "state_path"]

# Cuantos documentos se recuerdan. Sin tope el JSON crece para siempre; con
# tope hay que decidir a quien tirar, y se tira el que hace mas que no se abre.
MAX_TRACKED = 500
MAX_RECENT = 20


def state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "mdreader" / "state.json"


@dataclass
class Prefs:
    """Preferencias de la ventana.

    `theme` en "system" sigue al escritorio; "light"/"dark" lo fuerzan.
    """

    theme: str = "system"
    zoom: float = 1.0
    sidebar_visible: bool = True
    window_width: int = 1100
    window_height: int = 800
    window_maximized: bool = False


@dataclass
class DocState:
    """Lo que se recuerda de un documento."""

    # Fraccion 0..1 en vez de pixeles: sobrevive a cambiar el tamaño de la
    # ventana, el zoom o la fuente, que en pixeles te deja en otro lado.
    scroll: float = 0.0
    opened_at: float = 0.0
    # Permiso de imagenes remotas concedido a mano para ESTE documento.
    allow_remote: bool = False


class ReaderState:
    """Lectura y escritura del estado. Nunca lanza por un archivo corrupto."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_path()
        self.prefs = Prefs()
        self.documents: dict[str, DocState] = {}
        self.recent: list[str] = []
        self._load()

    # -- persistencia --------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Sin archivo, ilegible o JSON roto: se arranca de cero. Perder la
            # posicion de lectura no justifica no abrir el programa.
            return

        prefs = raw.get("prefs")
        if isinstance(prefs, dict):
            known = {f for f in Prefs.__dataclass_fields__}
            self.prefs = Prefs(**{k: v for k, v in prefs.items() if k in known})

        docs = raw.get("documents")
        if isinstance(docs, dict):
            known = {f for f in DocState.__dataclass_fields__}
            for key, value in docs.items():
                if isinstance(value, dict):
                    self.documents[key] = DocState(
                        **{k: v for k, v in value.items() if k in known}
                    )

        recent = raw.get("recent")
        if isinstance(recent, list):
            self.recent = [str(p) for p in recent if isinstance(p, str)][:MAX_RECENT]

    def save(self) -> None:
        """Escribe el estado de forma atomica.

        Con `os.replace` sobre un temporal en el mismo directorio, un corte a
        mitad de escritura deja el archivo viejo intacto en vez de uno truncado.
        """
        self._evict()
        payload = {
            "version": 1,
            "prefs": asdict(self.prefs),
            "documents": {k: asdict(v) for k, v in self.documents.items()},
            "recent": self.recent[:MAX_RECENT],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
            ) as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                temp_name = handle.name
            os.replace(temp_name, self.path)
        except OSError:
            # Un disco lleno o un home de solo lectura no deben matar la app.
            pass

    def _evict(self) -> None:
        if len(self.documents) <= MAX_TRACKED:
            return
        ordered = sorted(self.documents.items(), key=lambda kv: kv[1].opened_at, reverse=True)
        self.documents = dict(ordered[:MAX_TRACKED])

    # -- documentos ----------------------------------------------------------

    @staticmethod
    def _key(path: Path | str) -> str:
        return str(Path(path).expanduser().resolve())

    def get(self, path: Path | str) -> DocState:
        return self.documents.get(self._key(path), DocState())

    def remember(
        self,
        path: Path | str,
        *,
        scroll: float | None = None,
        allow_remote: bool | None = None,
        opened_at: float | None = None,
    ) -> None:
        key = self._key(path)
        entry = self.documents.setdefault(key, DocState())
        if scroll is not None:
            entry.scroll = max(0.0, min(1.0, float(scroll)))
        if allow_remote is not None:
            entry.allow_remote = bool(allow_remote)
        if opened_at is not None:
            entry.opened_at = float(opened_at)

    def push_recent(self, path: Path | str) -> None:
        key = self._key(path)
        if key in self.recent:
            self.recent.remove(key)
        self.recent.insert(0, key)
        del self.recent[MAX_RECENT:]

    def existing_recent(self) -> list[Path]:
        """Recientes que todavia existen en disco."""
        out: list[Path] = []
        for item in self.recent:
            candidate = Path(item)
            if candidate.is_file():
                out.append(candidate)
        return out
