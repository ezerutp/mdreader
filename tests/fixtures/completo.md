---
title: Documento de prueba
autor: ezer
tags: [markdown, prueba]
---

# Documento de prueba

Texto con **negrita**, *cursiva*, ~~tachado~~, `codigo` y un [link externo](https://example.com).

## Formulas

Inline: $E = mc^2$ y en bloque:

$$
\int_0^1 x^2 \, dx = \frac{1}{3}
$$

## Diagrama

```mermaid
graph TD
  A[Inicio] --> B{Decision}
  B -->|si| C[Hacer]
  B -->|no| D[Salir]
```

## Codigo

```python
def saludar(nombre: str) -> str:
    return f"hola {nombre}"
```

## Tabla

| columna | valor | nota |
|---------|------:|:----:|
| alfa    |    10 |  ok  |
| beta    |   200 |  --  |

## Listas

- [ ] pendiente
- [x] hecho
- [x] Tarea larga con `codigo` en linea (`uno`, `dos`, `tres`) que tiene que
  seguir siendo un parrafo y no desarmarse en columnas
- item normal
  - anidado

## Cita y detalles

> Una cita que ocupa
> dos lineas.

<details><summary>Desplegable</summary>Contenido oculto.</details>

<p align="center"><strong>HTML crudo permitido</strong></p>

<script>window.pwned = true;</script>

## Emojis

| Accion | Admin | Recepcion |
|---|:-:|:-:|
| Cobrar | ✅ | ✅ |
| Borrar | ✅ | ❌ |

Texto 🚀 🎉, codigo `ok ✅`, tono 👍🏽, bandera 🇵🇪 y aviso ⚠️.

## Imagenes

![local](local.svg)

![remota](https://example.com/no-existe.png)

## Notas

Referencia[^1]

[^1]: La nota al pie.

## Duplicado
### Duplicado
