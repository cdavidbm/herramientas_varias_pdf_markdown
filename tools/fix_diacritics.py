#!/usr/bin/env python3
"""
fix_diacritics.py — Repara la corrupción de DIACRÍTICOS típica de PDF de
editoriales académicas (OUP/Distiller) y de Docling, y normaliza a Unicode NFC.

Corrige tres patrones observados en textos con nombres alemanes/franceses/
españoles (frecuentes en bibliografía clásica, medieval y esotérica):

  1. i-sin-punto (ı, U+0131) + acento desplazado:
        Martı´n → Martín   Marı́a → María   Galigaı̈ → Galigaï   Nı̂mes → Nîmes
     (tolera un espacio: "Martı ´n" de Docling también se arregla)
  2. Umlaut renderizado como '€' delante de la vocal:
        Wolfenb€ uttel → Wolfenbüttel   H€ollenzwang → Höllenzwang   S€ oren → Sören
        Caraı€be → Caraïbe
  3. Acento suelto tras vocal + espacio (típico de Docling):
        Acade ´mie → Académie   Franc ¸ois → François   Schu ¨rer → Schürer

Finalmente normaliza a NFC (compone "e"+U+0301 → "é"), lo que evita fallos de
búsqueda/edición por caracteres descompuestos.

Estos son cambios SEGUROS y deterministas (mapeos de corrupción conocida), no
heurísticos: se pueden aplicar en bloque. Uso:

    python3 fix_diacritics.py cap.md [cap2.md ...]      # in situ
    python3 fix_diacritics.py cap.md --report           # solo cuenta, no escribe
"""
from __future__ import annotations
import argparse
import re
import sys
import unicodedata
from pathlib import Path

ACUTE = dict(zip("aeiouAEIOU", "áéíóúÁÉÍÓÚ"))
GRAVE = dict(zip("aeiouAEIOU", "àèìòùÀÈÌÒÙ"))
DIA   = dict(zip("aeiouAEIOU", "äëïöüÄËÏÖÜ"))
CIRC  = dict(zip("aeiouAEIOU", "âêîôûÂÊÎÔÛ"))
UML   = {"o": "ö", "u": "ü", "a": "ä", "O": "Ö", "U": "Ü", "A": "Ä"}


def fix(text: str) -> tuple[str, int]:
    before = text

    # 1) i-sin-punto (ı) + marca (con espacio opcional). Orden: compuestos antes.
    text = re.sub(r"ı\s*[€¨̈]", "ï", text)          # diéresis / € → ï
    text = re.sub(r"ı\s*[´́]", "í", text)            # agudo → í
    text = re.sub(r"ı\s*[`̀]", "ì", text)            # grave → ì
    text = re.sub(r"ı\s*[̂]",  "î", text)             # circunflejo → î
    text = text.replace("ı", "i")                    # i-sin-punto suelta → i

    # 2) umlaut como '€' delante de vocal
    text = re.sub(r"€\s?([ouaOUA])", lambda m: UML[m.group(1)], text)

    # 3) acento suelto tras vocal (+ espacio opcional). Cedilla para c/C.
    text = re.sub(r"c\s?[¸̧]", "ç", text); text = re.sub(r"C\s?[¸̧]", "Ç", text)
    text = re.sub(r"([aeiouAEIOU])\s?[´́]", lambda m: ACUTE[m.group(1)], text)
    text = re.sub(r"([aeiouAEIOU])\s?[`̀]", lambda m: GRAVE[m.group(1)], text)
    text = re.sub(r"([aeiouAEIOU])\s?[¨̈]", lambda m: DIA[m.group(1)],   text)
    text = re.sub(r"([aeiouAEIOU])\s?[̂]",  lambda m: CIRC[m.group(1)],  text)

    text = unicodedata.normalize("NFC", text)
    # contar caracteres cambiados de forma aproximada
    n = sum(1 for a, b in zip(before, text) if a != b) + abs(len(before) - len(text))
    return text, (0 if text == before else max(1, n))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--report", action="store_true", help="solo cuenta, no escribe")
    args = ap.parse_args()

    for path in args.files:
        text = path.read_text(encoding="utf-8")
        out, n = fix(text)
        if not args.report:
            path.write_text(out, encoding="utf-8")
        print(f"{path.name}: {'cambios' if n else 'sin cambios'}"
              + (f" (~{n} caracteres)" if n else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
