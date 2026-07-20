#!/usr/bin/env python3
"""
agy_consolidate.py — Cose las transcripciones POR PÁGINA de agy/Gemini (o de
cualquier motor visual con el mismo contrato) en el markdown de UN capítulo/Book.

El motor de transcripción emite, para cada página, un bloque:

    === pdfNNN-NNN.png ===
    # Título (opcional, solo en la 1ª página del Book)
    ## §N: Encabezado de sección
    Párrafo como UNA línea…

    [^12]: definición de nota al pie (al fondo de esa página)

Este script, dado esos bloques EN ORDEN de página, produce el capítulo limpio:
  - Separa el CUERPO de las DEFINICIONES de nota (`[^N]:`) de cada página.
  - Une el cuerpo A TRAVÉS del salto de página: si la última línea de una página no
    termina en puntuación terminal (y no es encabezado), se une con la primera línea
    de la siguiente (des-hyphenando si acaba en «-»). Así una frase partida por el
    pie de página vuelve a ser un solo párrafo.
  - Reúne TODAS las definiciones de nota al final, ordenadas por número (sin
    encabezado «Notas»: md_to_pdf las renderiza como notas al pie). Los marcadores
    `[^N]` del cuerpo quedan intactos y anclados.

NO renumera: dentro de un Book la numeración impresa de notas ya es única (el libro
reinicia por Book). Si consolidas TRAMOS de un mismo Book numerados 1-based locales,
usa antes un desplazado por offset (ver paradigma), no este script.

Uso:
  python3 agy_consolidate.py out.md  A.out B.out C.out        # ficheros en orden de página
  python3 agy_consolidate.py out.md  A.out B.out --title "Introduction"
  # --title fuerza/inserta el H1; si no, se respeta el `# …` que traiga la 1ª página.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PAGE_RE = re.compile(r"^===\s*(.+?)\s*===\s*$")
FNDEF_RE = re.compile(r"^\[\^([0-9]+)\]:\s?(.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s")
TERMINAL = ('.', '!', '?', ':', '"', '”', '»', ')', ']', '—', '-')


def parse_pages(raw: str) -> list[list[str]]:
    """Divide el texto crudo (varios ficheros ya concatenados) en páginas."""
    pages, cur = [], None
    for ln in raw.split("\n"):
        m = PAGE_RE.match(ln)
        if m:
            if cur is not None:
                pages.append(cur)
            cur = []
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        pages.append(cur)
    return pages


def split_body_notes(lines: list[str]) -> tuple[list[str], list[tuple[int, str]]]:
    """Separa el cuerpo de las definiciones de nota de UNA página.

    Desde la primera línea `[^N]:` hacia abajo, todo es aparato de notas; las líneas
    que no abren una def nueva se anexan como continuación de la def anterior.
    """
    body, notes = [], []
    in_notes = False
    for ln in lines:
        m = FNDEF_RE.match(ln)
        if m:
            in_notes = True
            notes.append([int(m.group(1)), m.group(2).rstrip()])
        elif in_notes:
            if ln.strip() and notes:
                notes[-1][1] = (notes[-1][1] + " " + ln.strip()).strip()
            # líneas en blanco dentro del bloque de notas se ignoran
        else:
            body.append(ln)
    # normaliza a tuplas
    return body, [(n, t) for n, t in notes]


def strip_trailing_blanks(lines: list[str]) -> list[str]:
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def join_bodies(pages_body: list[list[str]]) -> list[str]:
    """Concatena los cuerpos uniendo el párrafo partido por el salto de página.

    Al empalmar página P con P+1 hay tres casos entre out[-1] y la 1ª línea de P+1:
      1) out[-1] acaba en «-» → des-hyphena y une sin espacio.
      2) out[-1] no acaba en puntuación terminal y ninguna es encabezado → une con espacio
         (la frase continuaba tras el pie de página).
      3) en otro caso → párrafo nuevo: inserta una línea en blanco de separación.
    """
    out: list[str] = []
    for body in pages_body:
        body = strip_trailing_blanks(list(body))
        while body and not body[0].strip():   # quita blancos iniciales
            body.pop(0)
        if not body:
            continue
        if out:
            last, first = out[-1], body[0]
            if last.rstrip().endswith('-') and first[:1].isalpha():
                out[-1] = last.rstrip()[:-1] + first          # caso 1
                body = body[1:]
            elif (last.strip() and not last.rstrip().endswith(TERMINAL)
                  and not HEADING_RE.match(last) and not first.startswith("#")):
                out[-1] = last.rstrip() + " " + first         # caso 2
                body = body[1:]
            else:
                out.append("")                                # caso 3: separación de párrafo
        out.extend(body)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Consolida transcripciones por página (agy/Gemini) en un capítulo.")
    ap.add_argument("out", type=Path, help="markdown de salida")
    ap.add_argument("inputs", nargs="+", type=Path, help="ficheros .out de agy EN ORDEN de página")
    ap.add_argument("--title", default=None, help="fuerza el H1 del capítulo")
    args = ap.parse_args()

    raw = ""
    for f in args.inputs:
        if not f.exists():
            sys.exit(f"No existe: {f}")
        raw += f.read_text(encoding="utf-8") + "\n"

    pages = parse_pages(raw)
    if not pages:
        sys.exit("No se encontraron delimitadores `=== … ===`; ¿formato correcto?")

    bodies, all_notes = [], []
    for pg in pages:
        b, notes = split_body_notes(pg)
        bodies.append(b)
        all_notes.extend(notes)

    body_lines = join_bodies(bodies)
    body_text = "\n".join(body_lines)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()

    # H1
    if args.title:
        body_text = re.sub(r"^#\s+.*\n+", "", body_text)  # quita H1 previo si lo hay
        body_text = f"# {args.title}\n\n" + body_text

    # Notas al final, ordenadas y sin duplicar
    seen, defs = set(), []
    for n, t in sorted(all_notes, key=lambda x: x[0]):
        if n in seen:
            continue
        seen.add(n)
        defs.append(f"[^{n}]: {t}")

    out = body_text
    if defs:
        out += "\n\n" + "\n".join(defs) + "\n"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")

    # informe: balance de notas (refs inline vs defs)
    refs = set(int(m) for m in re.findall(r"\[\^(\d+)\](?!:)", body_text))
    defset = set(seen)
    print(f"OK  {args.out}")
    print(f"    páginas={len(pages)}  párrafos≈{body_text.count(chr(10)+chr(10))+1}  "
          f"notas def={len(defs)}")
    missing_def = sorted(refs - defset)
    orphan_def = sorted(defset - refs)
    if missing_def:
        print(f"    ⚠ refs SIN definición: {missing_def}")
    if orphan_def:
        print(f"    ⚠ defs SIN referencia: {orphan_def}")
    if not missing_def and not orphan_def:
        print(f"    ✓ balance de notas OK (refs == defs == {len(defset)})")


if __name__ == "__main__":
    main()
