#!/usr/bin/env python3
"""
footnotes_rebuild.py — Rebuild Markdown footnotes `[^N]` from OCR output where
superscript reference numbers were split into spaced digits and glued to the
preceding word (e.g. "phlegm.1 1 4" for footnote 114) and the definitions sit
at the page bottom as "114. Some source, p. 3".

Run it PER FILE (per chapter/section). Footnote numbering is scoped to the file,
so split the book into chapters first (see split_chapters.py). The tool is
RESET-AWARE: if numbering restarts inside the file (common in appendices that
concatenate several translated source texts), later blocks get unique labels
`[^bK-N]` so nothing collides.

How it works:
  * Definitions: lines matching `^N. text` become `[^N]: text` (or `[^bK-N]:`).
  * Body markers: for each footnote number that has a definition, in document
    order, find the spaced-digit run glued to a word/closing-punctuation and
    replace it with `[^N]`. Sequential expectation makes this robust against
    stray numbers (years, page refs).
  * A body marker is only linked if its definition exists, so the result never
    contains an orphan `[^N]` without its `[^N]:` (valid Markdown).

Coverage is reported: how many definitions were converted and how many body
markers were linked. On this class of OCR, expect ~100% of definitions and
~80% of body markers in narrative prose; appendices whose superscripts were
lost in the scan end up definition-only (still renders, just not click-linked).

By default runs in REPORT mode (writes nothing). Add --apply to write in place.
Do NOT run on indexes / bibliographies / word-lists (page numbers look like
definitions). Restrict to prose chapters.

Usage:
  python3 footnotes_rebuild.py 03_Chapter.md               # report only
  python3 footnotes_rebuild.py 03_Chapter.md --apply
  for f in 0[2-7]_*.md; do python3 footnotes_rebuild.py "$f" --apply; done
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

DEF_RE = re.compile(r"^(\d{1,3})\.\s+(\S.*)$")

# --- Variante "suelta" (p. ej. libros de AstroArt/Döser) ---------------------
# Otro estilo de OCR: la definición es «N Texto» (número + espacio, SIN punto) en
# una línea propia intercalada entre párrafos, y el marcador en el cuerpo es un
# número suelto delimitado por espacios («…Lilly. 1 Guido…»), NO pegado a la
# palabra. DEF_RE (que exige punto tras el número) no lo detecta. rebuild_bare()
# lo maneja: acepta definiciones sólo si forman una secuencia 1,2,3,… (así los
# números sueltos de prosa —años, páginas— no se confunden con notas).
DEF_BARE_RE = re.compile(r"^(\d{1,3})\s+(\S.*)$")


def rebuild_bare(text):
    lines = text.split("\n")
    # Definiciones candidatas «N Texto» (número + espacio, SIN punto: así NO capta
    # los ítems de listas numeradas «1. …», que sí llevan punto). La numeración de
    # notas suele ser CONTINUA en todo el libro (un capítulo empieza en 14, otro en
    # 109…), no reinicia en 1: tomamos la racha CONSECUTIVA (n == previo+1) más larga.
    cand = [(i, int(m.group(1)), m.group(2))
            for i, ln in enumerate(lines)
            if (m := DEF_BARE_RE.match(ln.strip()))]
    # Las notas están numeradas de forma ESTRICTAMENTE CRECIENTE en orden de archivo
    # (con huecos si el OCR fusionó alguna definición). Nos quedamos con la mayor
    # subsecuencia creciente contigua: un número que rompa la monotonía (p. ej. un
    # ítem de lista o un año al inicio de línea) inicia una racha nueva y se descarta
    # si la suya es más corta.
    best, cur = [], []
    for c in cand:
        if cur and c[1] > cur[-1][1]:
            cur.append(c)
        else:
            if len(cur) > len(best): best = cur
            cur = [c]
    if len(cur) > len(best): best = cur
    if len(best) < 2:                           # no parece este estilo
        return None
    defs = {n: (i, t) for (i, n, t) in best}    # n -> (idx_línea, texto)
    def_idx = {i for (i, _n, _t) in best}

    body = "\n".join(lines)
    # spans de las líneas-definición (para no tomarlas como marcadores)
    def_spans, off = [], 0
    for i, ln in enumerate(lines):
        if i in def_idx:
            def_spans.append((off, off + len(ln)))
        off += len(ln) + 1

    def in_def(p):
        return any(a <= p < b for a, b in def_spans)

    # Marcadores en el cuerpo, en orden: número suelto precedido de espacio o de
    # puntuación/letra (no de otro dígito) y seguido de espacio/puntuación/fin (no
    # de dígito). Así 1970, 30.13 o «casa 6.ª» NO cuentan como marcador.
    replacements, linked_ns, pos = [], set(), 0
    for n in range(min(defs), max(defs) + 1):
        if n not in defs:
            continue
        rx = re.compile(r"(?<=[\s.,;:)\]!?»”’]) ?" + str(n) + r"(?=[\s.,;:)\]]|$)")
        found = next((m for m in rx.finditer(body)
                      if m.start() >= pos and not in_def(m.start())), None)
        if found:
            replacements.append((found.start(), found.end(), n))
            pos = found.end()
            linked_ns.add(n)

    newbody = body
    for s, e, n in sorted(replacements, reverse=True):
        # el span es « N» o «N» (la puntuación previa queda fuera, en el lookbehind);
        # el espacio previo, si lo había, se descarta: «Lilly. 1 Guido» -> «Lilly.[^1] Guido»
        newbody = newbody[:s] + f"[^{n}]" + newbody[e:]

    # definiciones -> «[^N]: Texto», SOLO las notas cuyo marcador se enlazó (si no,
    # quedaría un `[^N]:` huérfano que pandoc descarta = cita perdida). Las demás se
    # quedan como número suelto en línea (sin pérdida de la referencia).
    conv, out = 0, []
    for i, ln in enumerate(newbody.split("\n")):
        m = DEF_BARE_RE.match(ln.strip())
        if i in def_idx and m and int(m.group(1)) in linked_ns:
            out.append(f"[^{int(m.group(1))}]: {m.group(2)}"); conv += 1
        else:
            out.append(ln)
    linked = len(linked_ns)
    final = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    stats = dict(blocks=1, defs=len(defs), linked=linked, converted=conv, unmatched=[])
    return final, stats


def rebuild(text):
    lines = text.split("\n")

    # definitions, grouped into blocks by numbering reset (N <= last seen)
    defs = [(i, int(m.group(1)))
            for i, ln in enumerate(lines)
            if (m := DEF_RE.match(ln.strip()))]
    blocks, cur, last = [], {}, 0
    for idx, n in defs:
        if n <= last and cur:
            blocks.append(cur)
            cur = {}
        cur[n] = idx
        last = n
    if cur:
        blocks.append(cur)
    multi = len(blocks) > 1

    def label(bk, n):
        return f"{n}" if (not multi or bk == 0) else f"b{bk + 1}-{n}"

    body = "\n".join(lines)
    # offsets of definition lines (never treat these as body markers)
    def_spans, off = [], 0
    for ln in lines:
        if DEF_RE.match(ln.strip()):
            def_spans.append((off, off + len(ln)))
        off += len(ln) + 1

    def in_def(i):
        return any(a <= i < b for a, b in def_spans)

    replacements, unmatched = [], []
    pos = 0
    for bk, block in enumerate(blocks):
        for n in range(1, max(block) + 1):
            if n not in block:
                unmatched.append((bk, n, "no-def"))
                continue
            spaced = " ?".join(list(str(n)))
            rx = re.compile(r"(?<=[A-Za-z.'\)’”])(" + spaced + r")(?! ?\d)")
            found = next((m for m in rx.finditer(body, pos) if not in_def(m.start())), None)
            if found:
                replacements.append((found.start(), found.end(), label(bk, n)))
                pos = found.end()
            else:
                unmatched.append((bk, n, "no-marker"))

    newbody = body
    for s, e, lab in sorted(replacements, reverse=True):
        newbody = newbody[:s] + f"[^{lab}]" + newbody[e:]

    # convert definitions to [^lab]:  (recompute block membership per def line)
    idx2lab, last, b, started = {}, 0, 0, False
    for idx, n in defs:
        if n <= last and started:
            b += 1
        idx2lab[idx] = label(b, n)
        last, started = n, True

    conv, out = 0, []
    for i, ln in enumerate(newbody.split("\n")):
        m = DEF_RE.match(ln.strip())
        if m and i in idx2lab:
            out.append(f"[^{idx2lab[i]}]: {m.group(2)}")
            conv += 1
        else:
            out.append(ln)
    final = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    stats = dict(blocks=len(blocks), defs=len(defs),
                 linked=len(replacements), converted=conv, unmatched=unmatched)
    return final, stats


def main():
    ap = argparse.ArgumentParser(description="Rebuild [^N] footnotes from OCR markdown (per file).")
    ap.add_argument("input")
    ap.add_argument("--apply", action="store_true", help="write in place (default: report only)")
    args = ap.parse_args()

    src = Path(args.input)
    raw = src.read_text(encoding="utf-8")
    final, st = rebuild(raw)                      # estilo «N. texto» + marcador pegado
    alt = rebuild_bare(raw)                       # estilo suelto «N texto» + marcador con espacio
    # elegir el que ENLACE más marcadores (evita que un falso positivo del estilo
    # «N.» sobre listas numeradas «1. …» gane sobre el estilo suelto real).
    if alt and alt[1]["linked"] >= st["linked"]:
        final, st = alt
        print(f"  (estilo suelto «N texto» detectado)")
    print(f"{src.name}: blocks={st['blocks']} defs={st['defs']} "
          f"linked={st['linked']} converted={st['converted']} unmatched={len(st['unmatched'])}")
    if st["unmatched"]:
        show = [f"b{bk+1}:{n}({why})" for bk, n, why in st["unmatched"][:25]]
        print("  unmatched:", show)
    if args.apply:
        src.write_text(final, encoding="utf-8")
        print("  written in place.")
    else:
        print("  (report only; use --apply to write)")


if __name__ == "__main__":
    main()
