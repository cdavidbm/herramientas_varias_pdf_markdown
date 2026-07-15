#!/usr/bin/env python3
"""
index_rebuild.py — Reconstruye el ÍNDICE ANALÍTICO de un libro contra el PDF que
de verdad vas a leer.

EL PROBLEMA
-----------
Traduces un libro y maquetas tu propio PDF. El índice analítico del original ya no
sirve: sus números remiten a la paginación de OTRA edición. Y no se puede
renumerar, porque el OCR de un índice a 2 columnas suele entrelazarlas y entonces
NO hay forma de saber qué página pertenece a qué entrada.

Da igual: esos números no hacen falta. El índice es del libro que uno tiene en las
manos. Lo único que se aprovecha del viejo es QUÉ TÉRMINOS merecen indexarse; las
páginas se buscan en el PDF nuevo.

POR QUÉ NO ES UN grep
---------------------
Un encabezado de índice NO es una cadena literal del texto. Está curado:
  - va invertido        `al-Rijāl, Ah ibn`   → el texto dice «Ali ibn al-Rijāl»
  - agrupa variantes    `África, africanos`  → el texto las usa por separado
  - normaliza flexión   `Abasíes`            → el texto dice «abasí»
  - lleva glosa         `al-qubūl (recepción)` → la glosa no está en el texto
Buscar el encabezado tal cual falla en ~43% de las entradas (medido). Por eso se
prueban VARIANTES de cada uno (ver `variants()`).

El «¿aparece en el texto?» hace además de filtro: la basura que el OCR dejó en el
índice viejo (`c c`, `x al-jamc`, restos de columnas fusionadas) no aparece en
ninguna página y cae sola. Lo no encontrado se reporta —no se esconde— con
`--report`, para que lo revises.

LÍMITES (dilos, no los tapes)
-----------------------------
- **Índice PLANO.** Si el OCR entrelazó las columnas, la jerarquía
  entrada/subentrada ya venía destruida; no se inventa.
- **Es una concordancia curada**, no el índice del autor: lista dónde aparece cada
  término, no solo las menciones significativas. En términos muy frecuentes
  («Dios») la entrada será larga. `--max-pages` los descarta si molestan.
- Los encabezados de página (running heads) se descuentan: si no, el título del
  capítulo casaría en todas sus páginas.

USO
---
    python3 index_rebuild.py viejo_indice.md libro.pdf --out nuevo_indice.md
    python3 index_rebuild.py viejo.md libro.pdf --out nuevo.md --report faltan.txt
    python3 index_rebuild.py viejo.md libro.pdf --out nuevo.md --dry-run

El PDF debe ser el YA maquetado. Pon el índice AL FINAL del libro: así añadirlo no
desplaza la paginación que acabas de medir (verifícalo igual).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from forja_common import require_tool

# Un "page-run" del índice viejo: números y romanos, con rangos y comas.
# Romanos de >=2 letras: `l` suelta partiría `aḥwālu-l-qamar` por la mitad.
_PAGE = r"(?:\d{1,3}|[ivxlcIVXL]{2,7})(?:\s*[-–—]\s*(?:\d{1,3}|[ivxlcIVXL]{2,7}))?"
# `(?<![\w-])` / `(?![\w-])`: nunca dentro de una palabra con guion.
_RUN = rf"(?<![\w-]){_PAGE}(?:\s*,\s*{_PAGE})*(?![\w-])"


def page_texts(pdf: Path) -> list[str]:
    """Texto por página, SIN el running head (1ª línea no vacía de cada página)."""
    require_tool("pdftotext", "apt: poppler-utils")
    out = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"],
                                  text=True, errors="replace")
    pages = []
    for raw in out.split("\f"):
        lines = raw.split("\n")
        for i, l in enumerate(lines):
            if l.strip():
                raw = "\n".join(lines[i + 1:])
                break
        pages.append(" ".join(raw.split()))
    while pages and not pages[-1]:
        pages.pop()
    return pages


def extract_terms(index_md: str) -> list[str]:
    """Encabezados del índice viejo. Los números se TIRAN: remiten a otra edición."""
    text = index_md
    # Fuera el encabezado markdown, las notas del traductor (>) y los comentarios.
    text = re.sub(r"^#.*$", " ", text, flags=re.M)
    text = re.sub(r"^>.*$", " ", text, flags=re.M)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"[*_]", "", text)
    text = re.sub(r"\bÍNDICE\b|\bINDEX\b", " ", text)
    parts = re.split(rf"(?:,\s*)?{_RUN}\.?", text)
    return [p.strip(" ,.;:—-") for p in parts if p.strip(" ,.;:—-")]


def plausible_head(head: str) -> bool:
    """¿Esto puede ser el encabezado de una entrada, o es resto del OCR?

    Rechaza lo que NO puede serlo nunca: vacío, restos de numeración (`40- X`),
    símbolos sueltos (`°`), ruido de una o dos letras (`c c`, `is`). No juzga el
    contenido: un encabezado válido raro se conserva.
    """
    h = " ".join(head.split())
    if len(h) < 3:
        return False
    # Un encabezado es corto. Si mide un párrafo, es prosa que se coló: los OCR de
    # índices suelen arrastrar la CONTRAPORTADA y la biografía del autor al final.
    if len(h) > 90 or len(h.split()) > 12:
        return False
    if not re.match(r"^[^\W\d_]", h, flags=re.UNICODE):   # debe EMPEZAR por letra
        return False
    letters = re.sub(r"[\W\d_]", "", h, flags=re.UNICODE)
    if len(letters) < 3:
        return False
    return True


def variants(term: str) -> list[str]:
    """Formas REALES en que un encabezado puede aparecer en el texto.

    Devuelve regex ya listos (los literales van escapados; la flexión no).
    """
    t = re.split(r"\.\s*(?:Véase|See)\b", term)[0]   # `X. Véase Y` → solo X
    t = re.sub(r"\([^)]*\)", " ", t)                 # la glosa no está en el texto
    t = " ".join(t.split()).strip(" ,.;:")
    if len(t) < 3 or not re.search(r"[^\W\d_]", t):
        return []

    forms: list[str] = [t]
    if "," in t:            # `África, africanos` · `al-Rijāl, Ah ibn`
        forms += [s.strip() for s in t.split(",") if len(s.strip()) >= 3]

    out = [re.escape(f) for f in forms]
    for f in forms:         # flexión española: Abasíes → abasí\w{0,3}
        m = re.match(r"^(.{4,}?)(?:es|s)$", f)
        if m:
            out.append(re.escape(m.group(1)) + r"\w{0,3}")
    return out


def find_pages(rxs: list[str], pages: list[str], offset: int) -> list[int]:
    """Páginas (1-based + offset) donde casa CUALQUIERA de las variantes."""
    for rx in rxs:
        try:
            pat = re.compile(rf"(?<!\w)(?:{rx})(?!\w)", re.IGNORECASE)
        except re.error:
            continue
        hits = [i + 1 + offset for i, p in enumerate(pages) if pat.search(p)]
        if hits:
            return hits
    return []


def collapse(nums: list[int]) -> str:
    """[5,6,7,12] → '5-7, 12'"""
    if not nums:
        return ""
    runs: list[list[int]] = [[nums[0]]]
    for n in nums[1:]:
        if n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return ", ".join(str(r[0]) if len(r) == 1 else f"{r[0]}-{r[-1]}" for r in runs)


def sort_key(term: str) -> tuple:
    """Alfabético español, ignorando acentos y el artículo árabe `al-`."""
    t = term.lower().strip()
    t = re.sub(r"^(?:al|ad|ar|as|at|az)-", "", t)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return (t, term)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old_index", type=Path, help="índice viejo (.md): de aquí salen los TÉRMINOS")
    ap.add_argument("pdf", type=Path, help="el PDF YA maquetado: de aquí salen las PÁGINAS")
    ap.add_argument("--out", type=Path, help="markdown de salida (def: stdout)")
    ap.add_argument("--title", default="Índice analítico", help="encabezado del índice")
    ap.add_argument("--report", type=Path, metavar="FILE",
                    help="escribe ahí los términos NO encontrados (revísalos)")
    ap.add_argument("--max-pages", type=int, default=0, metavar="N",
                    help="descarta términos con más de N páginas (0 = sin límite)")
    ap.add_argument("--page-offset", type=int, default=0,
                    help="suma a los números de página (si el PDF lleva preliminares aparte)")
    ap.add_argument("--dry-run", action="store_true", help="solo el resumen")
    args = ap.parse_args()

    for f in (args.old_index, args.pdf):
        if not f.is_file():
            sys.exit(f"error: no existe {f}")

    terms = extract_terms(args.old_index.read_text(encoding="utf-8"))
    pages = page_texts(args.pdf)
    print(f"Índice viejo : {args.old_index.name} → {len(terms)} encabezados candidatos")
    print(f"PDF          : {args.pdf.name} → {len(pages)} páginas")

    entries: list[tuple[str, list[int]]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for t in terms:
        vs = variants(t)
        if not vs:
            continue
        # OJO: normalizar SIEMPRE aquí. El candidato viene del índice viejo con los
        # saltos de línea dentro, y una entrada con `\n` se derrama por el markdown.
        head = " ".join(re.split(r"\.\s*(?:Véase|See)\b", t)[0].split()).strip(" ,.;:")
        if not plausible_head(head):
            continue
        k = sort_key(head)
        if k in seen:
            continue
        pg = find_pages(vs, pages, args.page_offset)
        if not pg:
            missing.append(head)
            continue
        if args.max_pages and len(pg) > args.max_pages:
            missing.append(f"{head}  (descartado: {len(pg)} págs > --max-pages)")
            continue
        seen.add(k)
        entries.append((head, pg))

    entries.sort(key=lambda e: sort_key(e[0]))
    print(f"  entradas con páginas : {len(entries)}")
    print(f"  sin localizar        : {len(missing)}"
          f"{'  (--report para verlas)' if not args.report else ''}")

    if args.report:
        args.report.write_text("\n".join(missing) + "\n", encoding="utf-8")
        print(f"  no encontrados → {args.report}")

    lines = [f"# {args.title}", ""]
    letter = None
    for head, pg in entries:
        first = sort_key(head)[0][:1].upper()
        if first != letter:
            letter = first
            lines += [f"## {letter}", ""]
        lines.append(f"{head}, {collapse(pg)}")
        lines.append("")
    md = "\n".join(lines)

    if args.dry_run:
        print("\n(dry-run: no se escribió nada)")
        return 0
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"\nEscrito: {args.out} ({len(entries)} entradas)")
    else:
        print()
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
