#!/usr/bin/env python3
"""Descarga KaTeX y Mermaid dentro del paquete.

Por que vendorizados y no por CDN: el lector bloquea las peticiones remotas por
defecto (decision de diseño, ver README). Si KaTeX y Mermaid vinieran de un CDN
serian justamente las dos cosas que el bloqueo rompe. Bajarlos una vez en la
instalacion los deja funcionando offline y sin que abrir un `.md` genere
trafico hacia afuera.

Los archivos van a mdreader/assets/vendor/, que esta en .gitignore: el repo no
guarda binarios, los trae el instalador.

    python scripts/fetch_assets.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

KATEX_VERSION = "0.16.22"
MERMAID_VERSION = "11.12.0"

CDN = "https://cdn.jsdelivr.net/npm"
KATEX_BASE = f"{CDN}/katex@{KATEX_VERSION}/dist"
MERMAID_URL = f"{CDN}/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"

VENDOR = Path(__file__).resolve().parent.parent / "mdreader" / "assets" / "vendor"
FONTS = VENDOR / "fonts"

# Solo woff2: la CSS de KaTeX lista woff2 primero y Chromium no pide los
# formatos siguientes si el primero carga. Bajar woff y ttf triplicaria el
# peso para nada.
FONT_PATTERN = re.compile(r"url\(fonts/([A-Za-z0-9_.-]+\.woff2)\)")

TIMEOUT = 60


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mdreader-fetch-assets"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def write(path: Path, data: bytes, *, force: bool) -> bool:
    """Escribe si hace falta. Devuelve True si toco el disco."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        if hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(data).digest():
            return False
    path.write_bytes(data)
    return True


def human(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebaja todo aunque ya este")
    args = parser.parse_args()

    total = 0
    try:
        print(f"KaTeX {KATEX_VERSION}")
        css = fetch(f"{KATEX_BASE}/katex.min.css")
        total += len(css)
        changed = write(VENDOR / "katex.min.css", css, force=args.force)
        print(f"  katex.min.css      {human(len(css)):>9}{'' if changed else '  (sin cambios)'}")

        js = fetch(f"{KATEX_BASE}/katex.min.js")
        total += len(js)
        changed = write(VENDOR / "katex.min.js", js, force=args.force)
        print(f"  katex.min.js       {human(len(js)):>9}{'' if changed else '  (sin cambios)'}")

        # La lista de fuentes sale de la propia CSS: si KaTeX cambia el set en
        # una version nueva, esto lo sigue sin que haya que tocar el script.
        names = sorted(set(FONT_PATTERN.findall(css.decode("utf-8", "replace"))))
        if not names:
            print("  aviso: no se encontraron fuentes woff2 en la CSS", file=sys.stderr)
        font_bytes = 0
        for name in names:
            data = fetch(f"{KATEX_BASE}/fonts/{name}")
            font_bytes += len(data)
            write(FONTS / name, data, force=args.force)
        total += font_bytes
        print(f"  fonts/ ({len(names):>2})        {human(font_bytes):>9}")

        print(f"Mermaid {MERMAID_VERSION}")
        mermaid = fetch(MERMAID_URL)
        total += len(mermaid)
        changed = write(VENDOR / "mermaid.min.js", mermaid, force=args.force)
        print(f"  mermaid.min.js     {human(len(mermaid)):>9}{'' if changed else '  (sin cambios)'}")

    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"\nError de descarga: {exc}", file=sys.stderr)
        print(
            "Sin estos archivos el lector igual abre: las formulas se ven como\n"
            "TeX y los diagramas como codigo. Volve a correr el script cuando\n"
            "tengas red.",
            file=sys.stderr,
        )
        return 1

    print(f"\nTotal {human(total)} en {VENDOR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
