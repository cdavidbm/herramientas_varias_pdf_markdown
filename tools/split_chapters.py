#!/usr/bin/env python3
"""
split_chapters.py — Split a single Markdown file into one file per chapter.

Two modes:

  1. PLAN mode (precise, recommended for real books):
     Pass a JSON plan describing each chapter by the *exact* heading text that
     starts it (or by 1-based line number). Front matter before the first
     chapter becomes section 00.
         {
           "sections": [
             {"slug": "00_Front",  "title": "Front matter"},           // no start = file start
             {"slug": "01_Preface","title": "Preface", "heading": "## Preface"},
             {"slug": "02_Intro",  "title": "Introduction", "line": 199}
           ]
         }
     Each output file gets an H1 `# NN — <title>` (section 00 is emitted as-is).

  2. AUTO mode (--by-heading LEVEL):
     Split at every heading of the given level (default 2 = `##`). Each chunk is
     named NN_<slugified-heading>.md. Good for a quick pass; less precise than a
     hand-checked plan.

Output files are written to --out (default: alongside the input, in ./markdown/).
The input is never modified.

Usage:
  python3 split_chapters.py book.md --plan plan.json --out markdown/
  python3 split_chapters.py book.md --by-heading 2 --out markdown/
  python3 split_chapters.py book.md --plan plan.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slugify(text, maxlen=40):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:maxlen] or "section"


def find_start(lines, sec):
    if "line" in sec:
        return sec["line"] - 1
    if "heading" in sec:
        target = sec["heading"].strip()
        for i, ln in enumerate(lines):
            if ln.strip() == target:
                return i
        raise SystemExit(f"heading not found: {target!r}")
    return 0  # front matter


def split_by_plan(lines, plan):
    secs = plan["sections"]
    starts = [find_start(lines, s) for s in secs]
    # find_start devuelve la PRIMERA coincidencia del heading. Si un título se repite
    # (índice + cuerpo) o el plan está desordenado, starts[k] > starts[k+1] daría una
    # rebanada de longitud NEGATIVA → capítulo vacío y texto PERDIDO en silencio.
    # Abortar señalando qué secciones colisionan en vez de escribir basura.
    for k in range(len(starts) - 1):
        if starts[k] > starts[k + 1]:
            a = secs[k].get("title", secs[k].get("slug", f"#{k}"))
            b = secs[k + 1].get("title", secs[k + 1].get("slug", f"#{k+1}"))
            raise SystemExit(
                f"ERROR: los encabezados no van en orden en el documento: "
                f"«{a}» (línea {starts[k]}) aparece DESPUÉS de «{b}» (línea {starts[k+1]}).\n"
                "  Causa típica: un título repetido (índice + cuerpo) o el plan.json "
                "desordenado.\n  Ajusta el 'heading' de esas secciones para que sean "
                "únicos, o reordena el plan. No se escribe nada para no perder texto.")
    starts.append(len(lines))
    out = []
    for k, sec in enumerate(secs):
        body = "\n".join(lines[starts[k]:starts[k + 1]]).strip("\n")
        title = sec.get("title", sec.get("slug", f"section {k}"))
        slug = sec.get("slug", f"{k:02d}_{slugify(title)}")
        if k == 0 and "heading" not in sec and "line" not in sec:
            content = body + "\n"           # front matter as-is
        else:
            content = f"# {k:02d} — {title}\n\n{body}\n"
        out.append((slug, re.sub(r"\n{3,}", "\n\n", content), len(body.split())))
    return out


def split_by_heading(lines, level):
    marker = "#" * level + " "
    idxs = [i for i, ln in enumerate(lines) if ln.startswith(marker)]
    if not idxs:
        raise SystemExit(f"no level-{level} headings found")
    bounds = ([0] if idxs[0] > 0 else []) + idxs + [len(lines)]
    out, seq = [], 0
    for a, b in zip(bounds, bounds[1:]):
        body = "\n".join(lines[a:b]).strip("\n")
        if not body:
            continue
        head = lines[a].lstrip("#").strip() if lines[a].startswith(marker) else "front"
        slug = f"{seq:02d}_{slugify(head)}"
        out.append((slug, body + "\n", len(body.split())))
        seq += 1
    return out


def main():
    ap = argparse.ArgumentParser(description="Split a markdown book into chapters.")
    ap.add_argument("input")
    ap.add_argument("--plan", help="JSON plan (PLAN mode)")
    ap.add_argument("--by-heading", type=int, metavar="LEVEL",
                    help="AUTO mode: split at every heading of this level (e.g. 2)")
    ap.add_argument("--out", default="markdown", help="output directory (default ./markdown)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lines = Path(args.input).read_text(encoding="utf-8").split("\n")
    if args.plan:
        pieces = split_by_plan(lines, json.loads(Path(args.plan).read_text(encoding="utf-8")))
    elif args.by_heading:
        pieces = split_by_heading(lines, args.by_heading)
    else:
        raise SystemExit("choose one: --plan plan.json  OR  --by-heading LEVEL")

    outdir = Path(args.out)
    total = 0
    for slug, content, wc in pieces:
        total += wc
        print(f"{slug:36s} {wc:6d} words" + ("  (dry-run)" if args.dry_run else ""))
        if not args.dry_run:
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / f"{slug}.md").write_text(content, encoding="utf-8")
    print(f"\n{len(pieces)} sections, {total} words"
          + (f" -> {outdir}/" if not args.dry_run else " (nothing written)"))


if __name__ == "__main__":
    main()
