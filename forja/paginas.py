"""forja.paginas — la página impresa: folios, titulillos y unión de renglones.

Por qué existe
--------------
`pdf_book_to_markdown` y `pdf_chapters_to_markdown` tenían SEIS funciones con el
mismo nombre. Tres eran idénticas carácter por carácter; las otras tres habían
**divergido en silencio**, y las dos peores son justamente las que deciden qué
líneas se BORRAN:

* `is_running_head`: uno usaba `p.search(s)` y el otro `p.match(s)`. Con
  `search`, cualquier línea que CONTENGA el patrón del titulillo desaparece —
  incluida prosa legítima que lo mencione a media frase.
* `is_page_number`: uno hacía `.strip()` antes de comparar y el otro no, así que
  un folio sangrado se colaba como ruido en el markdown.

Cada archivo acertaba en una y fallaba en la otra, y el mismo libro salía
distinto según qué conversor lo hubiera tocado. Es el mismo accidente que ya
había pasado con las once copias de `slugify`.

Aquí queda UNA versión con lo correcto de cada una, y con su test.

El criterio al borrar: PECAR DE CONSERVADOR
--------------------------------------------
Los dos errores no cuestan lo mismo. Un titulillo que sobrevive se ve al leer y
se quita después; una línea de cuerpo borrada por el filtro **no deja rastro**:
el markdown se lee sin sobresaltos y el hueco solo aparece cotejando con el PDF.
Medido en Kaske & Clark: 14 páginas y 194 palabras perdidas, siempre a mitad de
frase. Por eso el titulillo se ancla al PRINCIPIO de la línea y nunca se busca
suelto por dentro.
"""
from __future__ import annotations

import re

# Folio: cifras arábigas o romanas, con la ornamentación habitual alrededor.
NUM_PAGINA = re.compile(r"^[\s•·\.\-]*(\d{1,3}|[ivxIVX]{1,5})[\s•·\.\-]*$")


def es_numero_pagina(linea: str) -> bool:
    """¿La línea es solo un folio?

    Se normaliza con `.strip()` ANTES de comparar: sin eso, un folio sangrado
    —que es lo normal en las páginas pares de muchas maquetas— no se reconoce y
    acaba impreso en mitad del markdown.
    """
    return bool(NUM_PAGINA.match(linea.strip()))


def es_titulillo(linea: str, patrones) -> bool:
    """¿La línea es un titulillo de página?

    Se ancla con `match`, no con `search`. Buscar el patrón suelto por dentro de
    la línea borra prosa legítima que mencione el título de la obra o el nombre
    del autor a media frase, y esa pérdida es invisible al leer el markdown.
    """
    s = linea.strip()
    if not s:
        return False
    return any(p.match(s) for p in patrones)


def une_renglones(lineas: list[str]) -> str:
    """Une los renglones de un párrafo deshaciendo el corte de palabra.

    El guion suave (U+00AD) se elimina siempre; el guion normal solo se absorbe
    si lo que sigue empieza en MINÚSCULA, porque en `al-Rijāl` o `Ibn al-ʿArabī`
    el guion es parte del nombre y unirlo destruiría la palabra.
    """
    if not lineas:
        return ""
    out = lineas[0]
    for sig in lineas[1:]:
        if out.endswith("­"):
            out = out[:-1] + sig.lstrip()
            continue
        if out.endswith("-") and sig[:1].isalpha() and sig[:1].islower():
            out = out[:-1] + sig.lstrip()
            continue
        out = out + " " + sig
    return re.sub(r"­\s+", "", out)


def une_parrafo(texto: str) -> str:
    """Lo mismo, sobre un bloque ya en forma de texto."""
    texto = re.sub(r"(\w)­\n(\w)", r"\1\2", texto)
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    texto = re.sub(r"\s*\n\s*", " ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto.strip()
