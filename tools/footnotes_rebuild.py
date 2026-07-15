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
_LONE_NUM_RE = re.compile(r"^(\d{1,3}),?$")          # línea que es SOLO un número
_MONTHS = (r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
           r"septiembre|setiembre|octubre|noviembre|diciembre")


def _merge_split_defs(lines):
    """Une las definiciones PARTIDAS por el OCR: una línea que es solo un número
    («19») seguida (tras posibles líneas en blanco) de la línea con el texto de la
    cita («Lilly, p. 122,») -> «19 Lilly, p. 122,». Así la definición queda en una
    sola línea y el número suelto no se confunde luego con un marcador."""
    out, i = [], 0
    while i < len(lines):
        m = _LONE_NUM_RE.match(lines[i].strip())
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                nxt = lines[j].strip()
                if nxt and not _LONE_NUM_RE.match(nxt) and nxt[0] not in "#|![":
                    out.append(f"{m.group(1)} {nxt}")
                    i = j + 1
                    continue
        out.append(lines[i]); i += 1
    return out


def _is_prose(line):
    s = line.strip()
    return bool(s) and s[0] not in "#|![" and not _LONE_NUM_RE.match(s) and not s.startswith("[^")


def rebuild_bare(text):
    lines = _merge_split_defs(text.split("\n"))
    # Definiciones candidatas «N Texto» (número + espacio, SIN punto: así NO capta
    # los ítems de listas numeradas «1. …», que sí llevan punto). La numeración de
    # notas suele ser CONTINUA en todo el libro (un capítulo empieza en 14, otro en
    # 109…), no reinicia en 1, y es ESTRICTAMENTE CRECIENTE en orden de archivo (con
    # huecos): nos quedamos con la mayor subsecuencia creciente contigua.
    cand = [(i, int(m.group(1)), m.group(2))
            for i, ln in enumerate(lines)
            if (m := DEF_BARE_RE.match(ln.strip()))]
    # Subsecuencia estrictamente creciente MÁS LARGA (LIS propia, no contigua): así
    # un número duplicado (p. ej. dos notas «25» por un OCR que leyó «26» como «25»)
    # o un candidato espurio intercalado NO trunca la serie; se salta y se conserva
    # el resto (14…24 no se pierden por un tropiezo en 25).
    N = len(cand)
    if N < 2:
        return None
    dp = [1] * N
    prev = [-1] * N
    for i in range(N):
        for j in range(i):
            if cand[j][1] < cand[i][1] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                prev[i] = j
    end = max(range(N), key=lambda k: dp[k])
    best = []
    while end != -1:
        best.append(cand[end])
        end = prev[end]
    best.reverse()
    if len(best) < 2:                           # no parece este estilo
        return None
    defs = {n: (i, t) for (i, n, t) in best}
    def_idx = {i for (i, _n, _t) in best}

    body = "\n".join(lines)
    def_spans, off = [], 0
    for i, ln in enumerate(lines):
        if i in def_idx:
            def_spans.append((off, off + len(ln)))
        off += len(ln) + 1

    def in_def(p):
        return any(a <= p < b for a, b in def_spans)

    # Marcadores: búsqueda GLOBAL hacia adelante en orden numérico (los marcadores
    # aparecen en el texto en el mismo orden que su número). Guardas contra falsos
    # positivos: fechas («17 de septiembre»), horas/grados («5:50», «17º»), y números
    # pegados a otro dígito (años, decimales). El cursor `pos` sólo avanza al acertar.
    replacements, linked_ns, pos = [], set(), 0
    for n in sorted(defs):
        rx = re.compile(r"(?<![\d.,])(?<=[\s.,;:)\]!?»”’])" + str(n) + r"(?=[\s.;)\]!?»]|$)")
        found = None
        for m in rx.finditer(body):
            if m.start() < pos or in_def(m.start()):
                continue
            after = body[m.end():m.end() + 20]
            if re.match(r"\s+de\s+(" + _MONTHS + r")", after):    # fecha
                continue
            if re.match(r"\s*[:hº]\s*\d", after):                 # hora/grado
                continue
            found = m
            break
        if found:
            replacements.append((found.start(), found.end(), n))
            pos = found.end()
            linked_ns.add(n)

    newbody = body
    for s, e, n in sorted(replacements, reverse=True):
        newbody = newbody[:s] + f"[^{n}]" + newbody[e:]
    lines = newbody.split("\n")

    # Respaldo: la nota sin marcador hallado se cuelga al final del último párrafo de
    # prosa anterior a su definición (así nunca queda un `[^N]:` huérfano que pandoc
    # descartaría; la cita va al pie, junto al párrafo que la referencia).
    for n, (idx, _t) in defs.items():
        if n in linked_ns:
            continue
        for w in range(idx - 1, -1, -1):
            if _is_prose(lines[w]):
                lines[w] = lines[w].rstrip() + f"[^{n}]"
                linked_ns.add(n)
                break

    conv = 0
    for i, ln in enumerate(lines):
        if i in def_idx and (m := DEF_BARE_RE.match(ln.strip())):
            lines[i] = f"[^{int(m.group(1))}]: {m.group(2)}"; conv += 1
    final = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    stats = dict(blocks=1, defs=len(best), linked=len(replacements),
                 converted=conv, unmatched=[])
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
    # Guarda anti-misfire: si se «convirtieron» definiciones pero NO se enlazó ningún
    # marcador en el cuerpo, casi seguro que el patrón `N.` capturó una LISTA NUMERADA
    # de prosa («1. Primer punto») en vez de notas reales. Reescribir destruiría la
    # lista. Se rechaza la escritura aunque venga --apply.
    if st["converted"] > 0 and st["linked"] == 0:
        print("  ⚠️  MISFIRE probable: se detectaron 'definiciones' pero 0 marcadores en el "
              "cuerpo\n     (¿una lista numerada «1. …», no notas?). NO se escribe. "
              "Revisa el archivo; si de verdad son notas sin marcador, edítalas a mano.",
              file=sys.stderr)
        return
    if args.apply:
        src.write_text(final, encoding="utf-8")
        print("  written in place.")
    else:
        print("  (report only; use --apply to write)")


if __name__ == "__main__":
    main()
