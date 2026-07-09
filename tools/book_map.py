#!/usr/bin/env python3
"""
book_map.py — Mapa estructural compacto de una carpeta de markdown (o un .md).

Da orientación BARATA sin leer el contenido: por archivo, su título, nº de
palabras, encabezados y notas al pie. El agente se orienta con este mapa y luego
lee solo lo que necesita — ahorra tokens sin tocar calidad.

Uso:
    python3 book_map.py <carpeta_o_archivo.md>
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

H1 = re.compile(r'^#\s+(.*)')
ANYH = re.compile(r'^#{1,6}\s')
FN_REF = re.compile(r'(?<!\])\[\^[^\]]+\](?!:)')


def first_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = H1.match(line)
        if m:
            return re.sub(r'[*_`]', '', m.group(1)).strip()[:60]
    for line in text.splitlines():
        if ANYH.match(line):
            return re.sub(r'^#+\s*', '', line).strip()[:60]
    return fallback


def analyze(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "file": path.name,
        "title": first_title(text, path.stem),
        "words": len(text.split()),
        "headings": sum(1 for l in text.splitlines() if ANYH.match(l)),
        "footnotes": len(FN_REF.findall(text)),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 2
    target = Path(sys.argv[1])
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(p for p in target.rglob("*.md"))
    else:
        sys.exit(f"error: no existe {target}")
    if not files:
        sys.exit("no hay archivos .md")

    rows = [analyze(f) for f in files]
    tw = max((len(r["title"]) for r in rows), default=5)
    fw = max((len(r["file"]) for r in rows), default=5)
    total_w = sum(r["words"] for r in rows)

    print(f"== Mapa: {target.name} · {len(rows)} archivo(s) · {total_w:,} palabras ==\n")
    print(f"  {'archivo'.ljust(fw)}  {'título'.ljust(tw)}  {'palabras':>8}  enc  notas")
    print(f"  {'-'*fw}  {'-'*tw}  {'-'*8}  ---  -----")
    for r in rows:
        print(f"  {r['file'].ljust(fw)}  {r['title'].ljust(tw)}  {r['words']:>8,}  "
              f"{r['headings']:>3}  {r['footnotes']:>5}")
    print(f"\n  Total: {total_w:,} palabras en {len(rows)} archivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
