#!/usr/bin/env python3
"""
chapter_bounds.py — Encuentra el límite REAL de cada capítulo en un markdown de
Docling usando como ancla la PRIMERA PROSA de su página de inicio en el PDF.

El problema que resuelve
------------------------
Docling no siempre marca bien los capítulos, y emparejar por TÍTULO falla cuando:
  * el libro repite el título como **running header** de página y Docling lo
    promueve a encabezado (a veces incrustado a mitad de una frase);
  * el mismo título vuelve a usarse como **subtítulo** más adelante
    («Transits to the Lots» ×4 en un libro de ejemplos de cartas);
  * el título va **centrado y partido en dos líneas** y Docling no lo detecta.
En esos casos el troceo por encabezado corta donde no debe y se pierde/mezcla texto
(`split_chapters.py` aborta si los límites no son monótonos: esta herramienta te da
los límites correctos para que no llegue a ese punto).

La idea
-------
El índice del libro da la página de cada capítulo → se extrae de ESA página del PDF
su primera frase de prosa (saltando título, folio y running header) → se busca esa
frase en el markdown. Es DETERMINISTA: no depende de que el título esté bien.
La búsqueda se hace sobre el flujo GLOBAL de palabras (no línea a línea) porque el
ancla suele cruzar el encabezado y su prosa, que en el md son líneas distintas.

Entrada: un JSON de secciones con la página del LIBRO (no la del PDF):

    [ {"title": "PREFACE", "page": 1},
      {"title": "1: FINANCIAL SIGNIFICATORS", "page": 8}, ... ]

Con `--offset N` se convierte a página de PDF (pág_pdf = pág_libro + N). Averigua N
comparando el folio impreso de una página con su índice en el PDF.

Uso
---
    # 1) informe: ¿se localizan todas y en orden?
    python3 chapter_bounds.py libro.pdf clean.md --sections secs.json --offset 4

    # 2) aplicar: inserta «# TÍTULO» en cada límite y borra los encabezados
    #    espurios que repitan esos títulos (running headers)
    python3 chapter_bounds.py libro.pdf clean.md --sections secs.json --offset 4 \
            --apply --out book_prepped.md

Después: `split_chapters.py book_prepped.md --by-heading 1 --out markdown`
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ANCHOR_WORDS = 10          # palabras de la frase de apertura usadas como ancla
FALLBACKS = (10, 8, 6, 5)  # se acorta el ancla si no se encuentra


def norm(s: str) -> str:
    """Normaliza para comparar: minúsculas, sin puntuación ni espacios raros."""
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def page_text(pdf: Path, p: int) -> str:
    r = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: pdftotext falló en la página {p} de {pdf}\n{r.stderr[:400]}")
    return r.stdout


def anchor_for(pdf: Path, title: str, pdf_page: int) -> str | None:
    """Primeras ANCHOR_WORDS palabras de prosa de la página, saltando el título."""
    tnorm = norm(title)
    out: list[str] = []
    for ln in (l.strip() for l in page_text(pdf, pdf_page).split("\n")):
        n = norm(ln)
        if not n or n.isdigit():
            continue                       # línea vacía o folio
        if n in tnorm or tnorm in n:
            continue                       # el título (puede venir partido)
        if len(n.split()) < 3:
            continue                       # ruido suelto
        out.extend(n.split())
        if len(out) >= ANCHOR_WORDS:
            break
    return " ".join(out[:ANCHOR_WORDS]) if len(out) >= 5 else None


def build_stream(lines: list[str]):
    """Flujo global de palabras -> línea de origen (el ancla cruza líneas)."""
    words: list[str] = []
    wline: list[int] = []
    for i, l in enumerate(lines):
        for w in norm(l).split():
            words.append(w)
            wline.append(i)
    stream = " ".join(words)
    starts, pos = [], 0
    for w in words:
        starts.append(pos)
        pos += len(w) + 1
    return stream, starts, wline


def find_from(anchor: str, min_line: int, stream: str, starts: list[int],
              wline: list[int]) -> int | None:
    pos_of = {s: k for k, s in enumerate(starts)}
    for nw in FALLBACKS:
        a = " ".join(anchor.split()[:nw])
        if not a:
            continue
        c = stream.find(a)
        while c != -1:
            wi = pos_of.get(c)
            if wi is not None and wline[wi] > min_line:
                return wline[wi]
            c = stream.find(a, c + 1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("md", type=Path, help="markdown de Docling (ya limpio)")
    ap.add_argument("--sections", type=Path, required=True,
                    help="JSON: [{'title':…, 'page': nº de página DEL LIBRO}, …]")
    ap.add_argument("--offset", type=int, default=0,
                    help="pág_pdf = pág_libro + offset (def. 0)")
    ap.add_argument("--apply", action="store_true",
                    help="inserta los # y borra encabezados espurios")
    ap.add_argument("--out", type=Path, help="destino con --apply (def: sobrescribe)")
    a = ap.parse_args()

    secs = json.loads(a.sections.read_text(encoding="utf-8"))
    if isinstance(secs, dict):                       # admite {"sections": [...]}
        secs = secs["sections"]
    lines = a.md.read_text(encoding="utf-8").split("\n")
    stream, starts, wline = build_stream(lines)

    print(f"{'sección':<48} {'pág.libro':>9} {'línea md':>9}  ancla")
    print("-" * 110)
    found: dict[int, str] = {}
    prev, missing = -1, []
    for s in secs:
        title, bp = s["title"], s["page"]
        anc = anchor_for(a.pdf, title, bp + a.offset)
        idx = find_from(anc, prev, stream, starts, wline) if anc else None
        print(f"{title:<48} {bp:>9} {str(idx):>9}  "
              f"{(anc or 'SIN ANCLA (¿página de solo imagen/tabla?)')[:52]}")
        if idx is None:
            missing.append(title)
            continue
        found[idx] = title
        prev = idx

    idxs = sorted(found)
    mono = all(idxs[i] < idxs[i + 1] for i in range(len(idxs) - 1))
    print(f"\nlocalizadas: {len(found)}/{len(secs)}   monótonas: {mono}")
    if missing:
        print("SIN localizar (ponlas a mano):", ", ".join(missing))
    if not mono:
        sys.exit("ERROR: límites NO monótonos; revisa el índice/offset antes de aplicar.")

    if not a.apply:
        print("\n(informe; usa --apply para insertar los encabezados)")
        return 0

    # Encabezados espurios = los que repiten un título de sección (running headers).
    spurious = {norm(t) for t in found.values()}
    out: list[str] = []
    for i, ln in enumerate(lines):
        if i in found:
            out.append(f"# {found[i]}")
            out.append("")
        m = re.match(r"^#{1,6}\s+(.*\S)\s*$", ln)
        if m and norm(m.group(1)) in spurious:
            continue
        out.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    dst = a.out or a.md
    dst.write_text(text, encoding="utf-8")
    print(f"\n-> {dst}: {len(re.findall(r'(?m)^# ', text))} capítulos (#) insertados")
    print("   siguiente: split_chapters.py --by-heading 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
