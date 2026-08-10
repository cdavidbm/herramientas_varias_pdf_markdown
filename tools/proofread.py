#!/usr/bin/env python3
"""
proofread.py — Chequeos MECÁNICOS de tipografía y forma sobre markdown.

Atrapa lo objetivo y exhaustivo (espacios, comillas, guiones, repeticiones) para
que el agente se concentre en lo de criterio (voz, registro, consistencia real).
Pensado para textos académicos en español. NO altera el archivo: solo reporta.

Uso:
    python3 proofread.py archivo.md [archivo2.md ...]

Cada hallazgo sale como  archivo:línea:  tipo — detalle
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

FENCE = re.compile(r'^\s*```')
INLINE_CODE = re.compile(r'`[^`]*`')
URL = re.compile(r'https?://\S+|\]\([^)]*\)')


def clean(line: str) -> str:
    """Quita código en línea y URLs para no marcar falsos positivos."""
    line = INLINE_CODE.sub('', line)
    line = URL.sub('', line)
    return line


CHECKS = [
    # (nombre, regex sobre la línea limpia, detalle)
    ("doble-espacio",      re.compile(r'\S  +\S'),          "dos o más espacios seguidos"),
    ("espacio-final",      re.compile(r' +$'),              "espacio(s) al final de la línea"),
    ("espacio-antes-punt", re.compile(r'\s[,.;:!?]'),       "espacio antes de signo de puntuación"),
    ("comilla-recta",      re.compile(r'["\']'),            "comilla recta (¿usar « » o tipográficas?)"),
    ("puntos-suspensivos", re.compile(r'\.\.\.'),           "'...' en vez de '…'"),
    ("guion-como-raya",    re.compile(r'\s-\s'),            "guion suelto ' - ' (¿raya — o –?)"),
    ("espacio-antes-nota", re.compile(r'\s\[\^'),           "espacio antes de la nota [^N]"),
    ("apertura-sin-cierre",re.compile(r'¿[^?]*$|¡[^!]*$'),  "¿ o ¡ sin cierre en la línea"),
]

# Palabra repetida consecutiva: "de de", "que que" (ignora números y una lista breve legítima)
REPEAT = re.compile(r'\b(\w{2,})\s+\1\b', re.IGNORECASE)
LEGIT_REPEAT = {"muy", "no", "sí", "si", "ya", "tan", "cha"}


def check_file(path: Path) -> list[str]:
    out: list[str] = []
    in_fence = False
    blanks = 0
    for n, raw in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Líneas en blanco de más (3+ seguidas)
        if not raw.strip():
            blanks += 1
            if blanks == 3:
                out.append(f"{path}:{n}:  lineas-en-blanco — 3+ líneas vacías seguidas")
            continue
        blanks = 0

        line = clean(raw)
        if not line.strip():
            continue

        for name, rx, detail in CHECKS:
            if rx.search(line):
                out.append(f"{path}:{n}:  {name} — {detail}")

        for m in REPEAT.finditer(line):
            if m.group(1).lower() not in LEGIT_REPEAT:
                out.append(f"{path}:{n}:  palabra-repetida — «{m.group(0)}»")

    return out


def main() -> int:
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        print(__doc__)
        return 2
    total = 0
    for f in files:
        if not f.is_file():
            print(f"(omito {f}: no existe)")
            continue
        hallazgos = check_file(f)
        total += len(hallazgos)
        print(f"\n== {f.name}: {len(hallazgos)} hallazgo(s) mecánico(s) ==")
        for h in hallazgos:
            print("  " + h)
    print(f"\nTotal: {total}. (Lo de criterio —voz, registro, consistencia— lo revisa el agente.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
