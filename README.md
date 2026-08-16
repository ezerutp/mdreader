# mdreader

Lector de Markdown de escritorio para Fedora. Doble click en un `.md` y se abre
como un documento: indice lateral, imagenes, formulas, diagramas y navegacion
entre archivos.

No es un editor ni un previsualizador de editor. Es el equivalente a un lector
de PDF, pero para Markdown.

```bash
./scripts/install_ui.sh
```

## Que hace

| | |
|---|---|
| **Doble click** | Se registra como handler de `text/markdown`. Abrir un `.md` desde Archivos lo abre aca |
| **Indice** | Arbol de encabezados a la izquierda, resalta la seccion que estas leyendo, `Ctrl+B` para ocultarlo |
| **Pestañas** | Una sola ventana. Ocho `.md` abiertos son ocho pestañas, no ocho procesos |
| **Navegacion** | Un link a otro `.md` se abre adentro, con historial `Alt+←` / `Alt+→`. Los `http` van al navegador |
| **Render** | GFM completo: tablas, task lists, notas al pie, tachado, codigo con colores, HTML crudo |
| **Formulas** | KaTeX, `$inline$` y `$$bloque$$` |
| **Diagramas** | Mermaid |
| **Live reload** | Guardas el archivo en el editor y la vista se actualiza sin perder el scroll |
| **Memoria** | Vuelve a abrir cada documento donde lo dejaste |
| **Tema** | Sigue al escritorio, o forzas claro/oscuro. El marco y el documento cambian juntos |
| **Imagenes remotas** | Bloqueadas por defecto, con un boton para permitirlas por documento |

Atajos: `Ctrl+O` abrir · `Ctrl+W` cerrar pestaña · `Ctrl+B` indice ·
`Ctrl+±` / `Ctrl+0` zoom · `Ctrl+Shift+T` tema · `Ctrl+Shift+W` ancho completo ·
`Alt+←` / `Alt+→` historial · `Ctrl+Tab` cambiar de pestaña.

## Instalacion

```bash
./scripts/install_ui.sh                       # todo
./scripts/install_ui.sh --use-dnf             # Qt del sistema, mas liviano
./scripts/install_ui.sh --no-default-handler  # sin robarle el .md a nadie
./scripts/install_ui.sh --uninstall
```

Deja un venv en `~/.local/share/mdreader/`, el comando en `~/.local/bin/mdreader`
y el lanzador en `~/.local/share/applications/`. Nada fuera de `~/.local`, y sin
root salvo que uses `--use-dnf`.

### Sobre PySide6

Este proyecto **necesita QtWebEngine**, que vive en `PySide6-Addons` y no en
`PySide6-Essentials`. Es una diferencia deliberada con `aws-manager` y
`redirect`, que se quedaron en Essentials justamente para no arrastrar Qt
entero: aca el motor de Chromium *es* el producto. Sin el no hay flexbox, ni
KaTeX, ni Mermaid, y "respetar el diseño del md" no se cumple.

Hay dos caminos y el instalador prefiere el primero:

1. **`sudo dnf install python3-pyside6`** — el RPM de Fedora ya trae
   `QtWebEngineWidgets`, usa el Qt del sistema y se actualiza con dnf. El venv
   se crea con `--system-site-packages` para verlo.
2. **`pip install PySide6`** — ~250 MB dentro del venv, sin sudo.

### Assets vendorizados

KaTeX y Mermaid **no se cargan de un CDN**: se descargan una vez en la
instalacion a `mdreader/assets/vendor/` (~3 MB) y se sirven localmente.

No es una preferencia estetica, es una consecuencia: el lector bloquea las
peticiones remotas, asi que un KaTeX servido por CDN seria justamente lo que el
bloqueo rompe. Vendorizados funcionan offline y sin generar trafico.

Estan en `.gitignore` — el repo no guarda binarios, los trae el instalador
(`scripts/fetch_assets.py`).

## Decisiones de diseño

### Scroll continuo, no paginas

Un PDF trae la paginacion adentro; un `.md` es flujo continuo y no tiene
paginas. Inventarlas es una decision, no una propiedad del formato.

v1 usa **scroll continuo con estetica de hoja**: hoja centrada, ancho de
lectura fijo, margenes, sombra. Se ve como un lector de PDF, pero no corta
bloques de codigo ni tablas al medio, que es el problema caro de paginar.

La puerta queda abierta sin deuda: `render.py` produce solo el cuerpo y
`page.py` lo viste. Paginar de verdad es agregar una hoja de estilos con
`break-inside: avoid` y alto fijo, sin tocar el parser.

### El HTML crudo se sanea

El parser corre con `html: True` porque sin eso los READMEs reales se ven rotos
(`<p align="center">`, `<details>`, badges). Pero un `.md` asociado al doble
click puede venir de cualquier lado, y se renderiza en un motor Chromium con
JavaScript activo — que hace falta para KaTeX y Mermaid.

`sanitize.py` filtra por **lista blanca**: lo que no esta permitido se escapa y
se muestra como texto. Denylist no sirve, envejece mal.

Cubierto por 16 pruebas de vectores concretos: `<script>`, `onerror=`,
`javascript:` (incluido partido con un salto de linea), `data:text/html`,
`expression()` en `style`, `<iframe>`, markup escondido en comentarios.

### Imagenes remotas bloqueadas

`![](https://tracker/pixel.png)` en un `.md` le avisa al que lo escribio que lo
abriste, cuando y desde que IP. Se bloquea por defecto y hay un boton para
permitirlas, con el permiso recordado por documento.

Un detalle contraintuitivo del codigo: `LocalContentCanAccessRemoteUrls` esta en
**True**. Suena al reves, pero la pagina se carga con origen `file:` y KaTeX y
Mermaid se sirven por `mdasset:`, que para Chromium no es local — en `False`
esos dos scripts nunca se piden. Quien decide sobre la red es `RemoteBlocker`,
que ese atributo no puede saltear.

## Arquitectura

```
mdreader/           nucleo, sin Qt: se testea sin levantar la interfaz
├── render.py       Markdown -> HTML + indice + deteccion de recursos
├── sanitize.py     lista blanca del HTML crudo
├── toc.py          encabezados, anclas y arbol
├── page.py         arma la pagina: tema, CSS, scripts, CSP
├── state.py        posicion de lectura y preferencias
└── assets/         reader.css, reader.js, vendor/ (descargado)

mdreader_ui/        interfaz Qt
├── app.py          entrada, instancia unica por socket
├── window.py       pestañas, barra, indice
├── viewer.py       una pestaña: motor, historial, live reload
├── sidebar.py      arbol del indice
├── network.py      bloqueo de peticiones remotas
├── assets.py       esquema mdasset: para servir KaTeX/Mermaid
├── theme.py        claro/oscuro, documento y marco juntos
├── desktop.py      .desktop, iconos, asociacion con .md
└── icons.py        icono dibujado, no un PNG en el repo
```

El nucleo no importa PySide6. Por eso 61 de las 67 pruebas corren sin Qt; las 6
de `test_desktop.py` son las unicas que lo necesitan, y escriben en
directorios temporales — nunca tocan tu `~/.local/share` ni tus asociaciones.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[ui]"
.venv/bin/python scripts/fetch_assets.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python -m mdreader_ui tests/fixtures/completo.md
```

`tests/fixtures/completo.md` ejercita todo: front matter, formulas, Mermaid,
tablas alineadas, task lists, notas al pie, HTML crudo, un `<script>` que debe
quedar neutralizado, una imagen remota y anclas duplicadas.

## Estado

v1 funcional. Lo que quedo afuera a proposito, decidido al definir el alcance:

- **Busqueda en el documento** (`Ctrl+F`). WebEngine la da casi gratis con
  `findText()`; entra cuando haga falta.
- **Exportar a PDF**. Tambien barato con `printToPdf()`, y es donde la
  paginacion tendria sentido sin complicar la vista.
- **Edicion**. Es un lector.
