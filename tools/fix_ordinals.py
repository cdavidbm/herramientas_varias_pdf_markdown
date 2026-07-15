#!/usr/bin/env python3
"""
fix_ordinals.py — Repara los ORDINALES que el OCR destroza en libros escaneados
(«4 lh» → «4th», «ll' h» → «11th», «I 1 '» → «1st», «12 ,h» → «12th»).

Por qué importa
---------------
En inglés los ordinales van con letra volada (4^th). Al escanear, el volado se
separa y sus letras se leen mal: `th` → `lh`, `,h`, `'h`, `v`, `},`; `11` → `ll`;
`1` → `I`. En un libro de astrología sobre CASAS («the 4th house»), o en cualquier
texto con siglos/capítulos, eso cambia el sentido y es invisible para un corrector
ortográfico.

La idea clave
-------------
NO se intenta adivinar qué letra quiso decir cada corrupción. El sufijo correcto
se **deriva del propio número** (1→st, 2→nd, 3→rd, 11/12/13→th, resto→th), así que
basta con reconocer «número + basura-donde-iba-el-sufijo» y reescribirlo entero.
Es robusto ante corrupciones nuevas que no estén en la lista.

Guardas (para no romper texto sano)
-----------------------------------
  * Solo números 1-31 (casas 1-12, días, grados). Un «2015 th» no se toca.
  * El sufijo basura debe estar pegado (separado solo por espacio/coma/apóstrofo).
  * Horas («8 41 00 PM»), fechas («Feb 12 1966») y cifras sueltas quedan intactas.

Complementa a `docling_clean.py`, que ya normaliza el caso LIMPIO («5 th» → «5th»)
en material born-digital; este cubre el caso CORRUPTO de escaneo.

Uso
---
    python3 fix_ordinals.py cap.md              # informe (dry-run) + diff
    python3 fix_ordinals.py cap.md --apply      # reescribe en el sitio
    python3 fix_ordinals.py ./markdown --apply  # una carpeta entera
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path


def suffix(n: int) -> str:
    """Sufijo ordinal inglés correcto para n (11/12/13 son 'th', no st/nd/rd)."""
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# Basura que el OCR deja donde iba el volado. Incluye los sufijos correctos (th/st/
# nd/rd) para normalizar de paso el caso «4 th» -> «4th».
JUNK = r"(?:th|st|nd|rd|lh|l\s*h|,\s*h|'\s*h|’\s*h|h|v|\}\s*,|t\s*['’]?\s*I|,\s*t)"

MIN_N, MAX_N = 1, 31


def fix(text: str) -> tuple[str, int]:
    """Devuelve (texto_arreglado, nº de ordinales normalizados)."""
    n = [0]

    # «ll» = 11 cuando hace de número ante basura de sufijo (no toca palabras como
    # «all» o «still» porque exige el sufijo-oide justo detrás).
    text = re.sub(r"\bll(?=\s*['’,]?\s*[h}])", "11", text)
    # «I 1 '» / «I1'» = 1st (la I es un 1 mal leído)
    text = re.sub(r"\bI\s*1\s*['’]", "1st", text)

    def repl(m: re.Match[str]) -> str:
        num = int(m.group(1))
        if not (MIN_N <= num <= MAX_N):
            return m.group(0)
        n[0] += 1
        return f"{num}{suffix(num)}"

    text = re.sub(rf"\b(\d{{1,2}})\s*['’,]?\s*{JUNK}(?=[\s.,;:)\]]|$)", repl, text)
    return text, n[0]


def process(path: Path, apply: bool, show_diff: bool) -> int:
    old = path.read_text(encoding="utf-8")
    new, n = fix(old)
    if apply and n:
        path.write_text(new, encoding="utf-8")
    tag = "escrito" if (apply and n) else "dry-run"
    print(f"{path.name}: {n} ordinal(es) normalizado(s)  ({tag})")
    if show_diff and n and not apply:
        for line in difflib.unified_diff(old.split("\n"), new.split("\n"),
                                         lineterm="", n=0):
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                print("   ", line[:150])
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", type=Path, help="archivo .md o carpeta con .md")
    ap.add_argument("--apply", action="store_true", help="reescribe (si no, dry-run)")
    ap.add_argument("--quiet", action="store_true", help="sin diff en dry-run")
    a = ap.parse_args()

    if a.target.is_dir():
        files = sorted(a.target.glob("*.md"))
        if not files:
            sys.exit(f"error: no hay .md en {a.target}")
    elif a.target.is_file():
        files = [a.target]
    else:
        sys.exit(f"error: no existe {a.target}")

    total = sum(process(f, a.apply, not a.quiet) for f in files)
    print(f"\nTOTAL: {total} ordinal(es) en {len(files)} archivo(s)"
          f"{'' if a.apply else '  (usa --apply para escribir)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
