#!/usr/bin/env python3
"""hebreo_sp_a_unicode.py — devuelve a Unicode el hebreo de un PDF que lo compone
con una fuente ASCII de transliteración (SP Tiberian, SuperHebrew, Hebraica…).

Muchas monografías académicas de los años 90-2000 no componen el hebreo en Unicode:
usan una fuente TrueType **mapeada sobre ASCII** (`KQBUDD+SPTiberian`, WinAnsi, sin
`ToUnicode`). El texto se extrae sin error y sin aviso, pero lo que sale es basura
latina: `(K)lmw)` donde el libro imprime `ומלאך`. En un libro sobre cábala eso no es
un adorno perdido —es el objeto del que habla el capítulo—, y **ningún control lo ve**:
el ratio cuadra (los caracteres están, uno por letra), el balance de notas cuadra y el
corrector ortográfico lo toma por una sigla.

**La recuperación es determinista, no una adivinanza**, porque no hay que detectar qué
parece hebreo —cosa que daría falsos positivos (`why`, `myth` y `thy` se escriben solo
con letras del repertorio SP)— sino **preguntarle al PDF qué cadenas van en esa fuente**.
`pdftohtml -xml` da el texto y su `fontspec`; se sustituyen SOLO esas cadenas exactas.

**Y hay que INVERTIR.** El PDF almacena los glifos en orden VISUAL (izquierda→derecha
tal como se imprimen), mientras que el hebreo se lee de derecha a izquierda: la cadena
lógica es la inversa. Invirtiendo la cadena ENTERA —espacios incluidos— se arregla de
paso el orden de las PALABRAS: `hxwd hwhy K)lmw` → `ומלאך יהוה דוחה`.

Uso:
    python3 hebreo_sp_a_unicode.py libro.pdf ./es/*.md            # dry-run
    python3 hebreo_sp_a_unicode.py libro.pdf ./es/*.md --apply
    python3 hebreo_sp_a_unicode.py libro.pdf --listar             # solo inventario
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Esquema Michigan-Claremont / SP: una letra ASCII por consonante hebrea.
MAPA = {
    ")": "א", "b": "ב", "g": "ג", "d": "ד", "h": "ה", "w": "ו", "z": "ז",
    "x": "ח", "+": "ט", "y": "י", "k": "כ", "K": "ך", "l": "ל", "m": "מ",
    "M": "ם", "n": "נ", "N": "ן", "s": "ס", "(": "ע", "p": "פ", "P": "ף",
    "c": "צ", "C": "ץ", "q": "ק", "r": "ר", "#": "ש", "$": "שׁ", "&": "שׂ",
    "t": "ת",
}
FUENTES = "Tiberian|SuperHebrew|Hebraica|Hebrew"


def a_hebreo(s: str) -> str:
    """ASCII en orden VISUAL → hebreo Unicode en orden LÓGICO."""
    return "".join(MAPA.get(c, c) for c in reversed(s))


def patron(s: str) -> str:
    """Regex que exige que la cadena sea un TOKEN entero.

    Sin esto la herramienta destroza el texto: las cadenas de dos o tres letras del
    repertorio —`hy`, `l)`, `ywh`— casan DENTRO de palabras corrientes (*t·hy·s*,
    *t·hy*, *w·hy*). Medido en Lehrich: 405 «restituciones» con `str.replace` a secas
    frente a las ~90 reales, y el inglés habría quedado sembrado de hebreo a media
    palabra. La frontera no puede ser `\\b`, porque `)` y `(` son letras aquí y `\\b`
    las trata como puntuación: se exige explícitamente que no haya letra ni dígito
    pegados a ninguno de los dos lados.
    """
    return r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])"


def runs_del_pdf(pdf: str, fuentes: str = FUENTES) -> list[str]:
    """Cadenas del PDF compuestas con una fuente hebrea ASCII, más largas primero.

    De mayor a menor longitud a propósito: `K)lmw` contiene `lmw`, y sustituir el
    trozo corto antes partiría el largo por la mitad.
    """
    xml = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", pdf],
                         capture_output=True, text=True).stdout
    ids = {m.group(1) for m in
           re.finditer(rf'<fontspec id="(\d+)"[^>]*family="[^"]*(?:{fuentes})', xml)}
    if not ids:
        return []
    vistos: dict[str, None] = {}
    for m in re.finditer(r'<text[^>]*font="(\d+)"[^>]*>(.*?)</text>', xml, re.S):
        if m.group(1) in ids:
            s = re.sub("<[^>]+>", "", m.group(2)).strip()
            if len(s) >= 2 and any(c in MAPA for c in s):
                vistos[s] = None
    return sorted(vistos, key=len, reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    ap.add_argument("--listar", action="store_true", help="solo el inventario del PDF")
    ap.add_argument("--fuentes", default=FUENTES, help="regex de familias hebreas")
    a = ap.parse_args()

    runs = runs_del_pdf(a.pdf, a.fuentes)
    if not runs:
        print("No hay ninguna fuente hebrea ASCII en este PDF (o pdftohtml no la nombra).")
        return 0
    print(f"{len(runs)} cadena(s) hebreas distintas en el PDF:")
    for s in runs[:40]:
        print(f"   {s!r:28} → {a_hebreo(s)}")
    if a.listar or not a.files:
        return 0

    tot = 0
    for f in a.files:
        if not f.is_file():
            print(f"warning: no existe {f}", file=sys.stderr)
            continue
        t = f.read_text(encoding="utf-8")
        n = 0
        for s in runs:
            t, k = re.subn(patron(s), a_hebreo(s), t)
            n += k
        if n:
            tot += n
            if a.apply:
                f.write_text(t, encoding="utf-8")
            print(f"  {f.name}: {n} cadena(s) restituidas")
    print(f"\n{'APLICADO' if a.apply else 'DRY-RUN'} — {tot} restitución(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
