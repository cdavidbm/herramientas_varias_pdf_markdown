#!/usr/bin/env python3
"""glifos_janus_a_unicode.py — restituye los glifos astrológicos de un PDF compuesto
con la fuente **Janus** (u otra fuente de símbolos con `ToUnicode` roto).

Mismo defecto silencioso que el hebreo en fuente ASCII ([[hebreo_sp_a_unicode.py]]):
la fuente declara un `ToUnicode`, así que `pdftotext` extrae SIN error… pero lo que
devuelve son los caracteres Windows-1252 de los bytes originales. Una carta natal
queda así:

    ‚ 06 Ú 02   ƒ 09 Ø 19   ˆ 07 Ø 34      →   ☉ 06 ♌ 02   ☽ 09 ♊ 19   ♄ 07 ♊ 34

Ningún control lo ve: el ratio cuadra (hay un carácter por glifo), el balance de notas
cuadra y el corrector lo toma por signos de puntuación. Pero las tablas de horas
planetarias, las cartas y los cuadros de dignidades quedan **ilegibles**.

## Cómo se derivó el mapeo (y cómo derivar el de otra fuente)

No se adivina: se contrasta el texto extraído contra la PÁGINA RENDERIZADA.

1. `pdffonts` sobre el PDF fuente da el nombre de la fuente (`CLSONT+Janus`).
2. `pdftohtml -xml` da los runs que van en ella, con su posición.
3. Se elige una página con contenido CONOCIDO y se renderiza. Aquí sirvieron dos:
   · la tabla de **horas planetarias** (el lunes empieza por la Luna, el domingo por
     el Sol: eso fija los siete planetas de una vez);
   · una **carta natal identificable** —la de Mussolini, 29-VII-1883— cuyas
     posiciones son públicas: Sol 6° Leo, Luna 9° Géminis, Venus 21° Cáncer.
4. Los puntos de la carta se confirman por GEOMETRÍA, que no depende de leer nada:
   `¡` y `¢` aparecen siempre a 180° exactos → son los nodos ☊ y ☋.
5. Los aspectos los rotula el propio libro: «la **oposición** (Â) 180°».

Uso:
    python3 glifos_janus_a_unicode.py ./es/*.md            # dry-run
    python3 glifos_janus_a_unicode.py ./es/*.md --apply
    python3 glifos_janus_a_unicode.py ./es/*.md --restos   # qué queda sin mapear
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

# Verificado contra la tabla de horas planetarias y la carta de Mussolini.
JANUS = {
    # planetas — 0x82..0x88
    "‚": "☉", "ƒ": "☽", "„": "☿", "…": "♀",
    "†": "♂", "‡": "♃", "ˆ": "♄",
    # puntos de la carta — 0xA1..0xA8
    "¡": "☊", "¢": "☋", "£": "⊗", "§": "AS", "¨": "MC",
    # aspectos — el propio texto los rotula
    "³": "⚹", "¸": "□", "»": "△", "Â": "☍",
    # signos — 0xD6..0xE1, Aries..Piscis
    "Ö": "♈", "×": "♉", "Ø": "♊", "Ù": "♋",
    "Ú": "♌", "Û": "♍", "Ü": "♎", "Ý": "♏",
    "Þ": "♐", "ß": "♑", "à": "♒", "á": "♓",
    # retrogradación
    "Æ": "℞",
}
# Rangos donde vive la fuente: lo que quede ahí SIN mapear hay que mirarlo.
SOSPECHOSOS = re.compile("[\u00a1-\u00ff\u0152-\u0178\u2013-\u2122]")

# **LA GUARDA IMPRESCINDIBLE.** Varios de estos códigos son LETRAS CORRIENTES en
# español: `á` (más, está, día), `Á`, `à`, `ß`, `Ö`, `Ü`. Sustituir a secas convierte
# cada «á» del libro en el signo de Piscis y lo DESTRUYE — medido: 13.880
# «restituciones», de las que la inmensa mayoría eran texto normal. Es la misma
# trampa que en el hebreo (`hebreo_sp_a_unicode.py`): sin frontera de token, el mapa
# arrasa la prosa.
#
# El discriminante es el CONTEXTO: un glifo de carta va rodeado de cifras, grados y
# espacios (`‚ 06 Ú 02`, `¡20Ø12`), mientras que una letra acentuada va DENTRO de una
# palabra. Se convierte solo si NINGUNO de los dos vecinos es letra.
LETRA = re.compile(r"[^\W\d_]", re.UNICODE)


# `»` es, en un texto español, la COMILLA DE CIERRE mucho más a menudo que el
# trígono: medido en Zoller, 172 de 172 apariciones fuera de palabra eran «…?».
# Para él —y para cualquier código ambiguo— no basta con que no haya letras al lado:
# se exige que un vecino (saltando espacios) sea una CIFRA u otro glifo del mapa,
# que es como se escriben los datos de carta (`‚ 06 Ú 02`, `ƒ09×53`).
AMBIGUOS = set("»«×§°")


def _vecino_util(t: str, i: int, paso: int) -> str:
    j = i + paso
    while 0 <= j < len(t) and t[j] == " ":
        j += paso
    return t[j] if 0 <= j < len(t) else ""


def _es_glifo(t: str, i: int) -> bool:
    izq = t[i - 1] if i else ""
    der = t[i + 1] if i + 1 < len(t) else ""
    if izq and LETRA.match(izq):
        return False
    if der and LETRA.match(der):
        return False
    if t[i] in AMBIGUOS:
        vs = (_vecino_util(t, i, -1), _vecino_util(t, i, 1))
        return any(v.isdigit() or v in JANUS for v in vs if v)
    return True


def _pasada(t: str) -> tuple[str, int]:
    out, n = [], 0
    for i, c in enumerate(t):
        if c in JANUS and _es_glifo(t, i):
            out.append(JANUS[c]); n += 1
        else:
            out.append(c)
    return "".join(out), n


def convierte(t: str) -> tuple[str, int]:
    """Itera hasta que no cambia nada.

    Una sola pasada no basta: en `°Ü‡19` el `‡` está pegado a `Ü`, que TODAVÍA es
    una letra cuando se le mira, así que la guarda lo bloquea; convertido `Ü` en ♎
    —que ya no es letra— la siguiente pasada sí lo restituye. Medido en Zoller: 2.802
    glifos en la primera vuelta y 84 más en la segunda.
    """
    total = 0
    for _ in range(6):
        t, n = _pasada(t)
        total += n
        if not n:
            break
    return t, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restos", action="store_true",
                    help="lista los caracteres del rango que NO están mapeados")
    a = ap.parse_args()

    tot = 0
    restos: collections.Counter = collections.Counter()
    for f in a.files:
        if not f.is_file():
            print(f"warning: no existe {f}", file=sys.stderr)
            continue
        t = f.read_text(encoding="utf-8")
        nuevo, n = convierte(t)
        for c in SOSPECHOSOS.findall(nuevo):
            restos[c] += 1
        if n:
            tot += n
            if a.apply:
                f.write_text(nuevo, encoding="utf-8")
            print(f"  {f.name}: {n} glifo(s) restituidos")
    print(f"\n{'APLICADO' if a.apply else 'DRY-RUN'} — {tot} glifo(s)")
    if a.restos and restos:
        print("Caracteres del rango SIN mapear (revísalos contra la página):")
        for c, k in restos.most_common(20):
            print(f"   {c!r} U+{ord(c):04X} ×{k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
