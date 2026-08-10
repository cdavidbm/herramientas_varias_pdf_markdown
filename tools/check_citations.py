#!/usr/bin/env python3
"""
check_citations.py — Verifica la consistencia de claves de cita en markdown.

Cruza las citas [@clave] del texto contra las entradas de un .bib (o CSL-JSON) y
reporta: claves citadas SIN entrada (error) y entradas NUNCA citadas (huérfanas).
pandoc avisa de las primeras pero no lista las huérfanas; esto hace ambas.

Uso:
    python3 check_citations.py referencias.bib capitulo.md [mas.md ...]

Sale con código 1 si hay citas sin entrada (error duro).
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

# Citas pandoc: @clave  /  [@clave]  /  [-@clave, p. 3]  /  [@a; @b]
CITE = re.compile(r'(?<!\w)-?@([A-Za-z0-9_][\w:.#&+?/%-]*)')
BIB_ENTRY = re.compile(r'@\w+\s*\{\s*([^,\s]+)\s*,')
FENCE = re.compile(r'^\s*```')


def keys_from_bib(path: Path) -> list[str]:
    text = path.read_text(encoding='utf-8', errors='replace')
    if path.suffix.lower() == '.json':            # CSL-JSON
        try:
            return [str(e["id"]) for e in json.loads(text) if "id" in e]
        except Exception:
            return []
    return BIB_ENTRY.findall(text)                # BibTeX


def cites_from_md(path: Path) -> set[str]:
    found: set[str] = set()
    in_fence = False
    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r'`[^`]*`', '', raw)        # ignora código en línea
        line = re.sub(r'\S+@\S+\.\w+', '', line)  # ignora emails
        found.update(CITE.findall(line))
    return found


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    bib = Path(sys.argv[1])
    mds = [Path(a) for a in sys.argv[2:]]
    if not bib.is_file():
        print(f"error: no existe la base bibliográfica {bib}")
        return 2

    bib_keys = keys_from_bib(bib)
    bib_set = set(bib_keys)
    dups = sorted({k for k in bib_keys if bib_keys.count(k) > 1})

    cited: set[str] = set()
    for m in mds:
        if m.is_file():
            cited |= cites_from_md(m)
        else:
            print(f"(omito {m}: no existe)")

    sin_entrada = sorted(cited - bib_set)
    huerfanas = sorted(bib_set - cited)

    print(f"== Citas: {len(cited)} clave(s) citada(s) | {len(bib_set)} entrada(s) en {bib.name} ==\n")
    if dups:
        print(f"🔴 Claves DUPLICADAS en el .bib: {dups}")
    if sin_entrada:
        print(f"🔴 Citadas SIN entrada en el .bib ({len(sin_entrada)}):")
        for k in sin_entrada:
            print(f"   - @{k}")
    if huerfanas:
        print(f"🟡 Entradas NUNCA citadas (huérfanas, {len(huerfanas)}):")
        for k in huerfanas:
            print(f"   - {k}")
    if not (dups or sin_entrada or huerfanas):
        print("🟢 Todas las citas tienen entrada y todas las entradas se usan.")

    return 1 if sin_entrada else 0


if __name__ == "__main__":
    sys.exit(main())
