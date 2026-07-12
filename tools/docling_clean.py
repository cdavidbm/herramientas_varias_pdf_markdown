#!/usr/bin/env python3
"""
docling_clean.py — Limpia los ARTEFACTOS SISTEMÁTICOS que introduce Docling al
convertir back-matter académico born-digital (notas finales, índices a 2
columnas). Docling ordena bien las columnas —por eso se usa para eso— pero mete
sus propios defectos:

  * acentos partidos:      'Acade ´mie' → 'Académie'   'Franc ¸ois' → 'François'
  * mayúscula R partida:   'R itual' → 'Ritual'        'R osy' → 'Rosy'
  * espaciado de citas:    '5 th' → '5th'  '1 -24' → '1-24'  '8 : 3' → '8:3'  ' ;' → ';'
  * ligaduras con espacio: 'O Y cina' → 'Officina'  'Bu V y' → 'Buffy'  'W eld' → 'field'
    (mayúscula-ligadura W/V/X/Y/Z AISLADA entre espacios; Docling solo aísla las
     ligaduras, no las mayúsculas reales, por eso es seguro expandirlas)
  * filas de tabla vacías ('|') que deja al vectorizar el índice

Con --title '# Notes' reemplaza el primer encabezado de Docling por ese H1.

Complementa a fix_diacritics.py (que cubre ı/€). Uso:

    python3 docling_clean.py entrada.md salida.md [--title '# Notes']
"""
from __future__ import annotations
import argparse
import re
import sys

ACUTE = dict(zip("aeiouAEIOU", "áéíóúÁÉÍÓÚ"))
GRAVE = dict(zip("aeiouAEIOU", "àèìòùÀÈÌÒÙ"))
DIA   = dict(zip("aeiouAEIOU", "äëïöüÄËÏÖÜ"))
CIRC  = dict(zip("aeiouAEIOU", "âêîôûÂÊÎÔÛ"))
LIG   = {"W": "fi", "V": "ff", "X": "fl", "Y": "ffi", "Z": "ffl"}
UML   = {"o": "ö", "u": "ü", "a": "ä", "O": "Ö", "U": "Ü", "A": "Ä"}


def fix_accents(t: str) -> str:
    t = re.sub(r"c ?[¸̧]", "ç", t); t = re.sub(r"C ?[¸̧]", "Ç", t)
    t = re.sub(r"([aeiouAEIOU]) ?[´́]", lambda m: ACUTE[m.group(1)], t)
    t = re.sub(r"([aeiouAEIOU]) ?[`̀]", lambda m: GRAVE[m.group(1)], t)
    t = re.sub(r"([aeiouAEIOU]) ?[¨̈]", lambda m: DIA[m.group(1)],   t)
    t = re.sub(r"([aeiouAEIOU]) ?[̂]",  lambda m: CIRC[m.group(1)],  t)
    t = t.replace("ı€", "ï")
    t = re.sub(r"€\s?([ouaOUA])", lambda m: UML[m.group(1)], t)
    return t


def fix_spacing(t: str) -> str:
    t = re.sub(r"\bR (?=[a-z])", "R", t)              # mayúscula R partida
    t = re.sub(r"(\d) (th|st|nd|rd)\b", r"\1\2", t)   # 5 th → 5th
    t = re.sub(r"(\d) ?: ?(\d)", r"\1:\2", t)         # 8 : 3 → 8:3
    t = re.sub(r"(\d) ?- ?(\d)", r"\1-\2", t)         # 1 -24 → 1-24
    t = re.sub(r"(\w) ([,;:.)\]])", r"\1\2", t)       # espacio antes de puntuación
    t = re.sub(r"([(\[]) (\w)", r"\1\2", t)           # espacio tras apertura
    t = re.sub(r" +", " ", t)
    return t


def fix_space_ligatures(t: str) -> str:
    """'letra ESPACIO cap ESPACIO resto' → une+expande (Docling solo aísla ligaduras)."""
    pat = re.compile(r"([A-Za-z]) ([WVXYZ]) ([a-z]+)")
    for _ in range(2):                                 # algunas encadenan
        t = pat.sub(lambda m: m.group(1) + LIG[m.group(2)] + m.group(3), t)
    t = re.sub(r"\bthefirst\b", "the first", t)        # glue-up ocasional
    return t


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--title", help="H1 a poner (reemplaza el 1º heading de Docling)")
    args = ap.parse_args()

    t = open(args.src, encoding="utf-8").read()
    t = fix_accents(t)
    t = fix_spacing(t)
    t = fix_space_ligatures(t)
    t = "\n".join(ln for ln in t.split("\n") if ln.strip() not in ("|", "| |", "||"))
    if args.title:
        t = re.sub(r"^#+\s+\w.*\n", "", t, count=1).lstrip("\n")
        t = args.title + "\n\n" + t
    open(args.dst, "w", encoding="utf-8").write(t)
    print(f"limpiado → {args.dst} ({len(t)//1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
