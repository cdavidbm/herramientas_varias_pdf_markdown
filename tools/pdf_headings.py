#!/usr/bin/env python3
"""
pdf_headings.py — Recover heading HIERARCHY from a DIGITAL pdf by font size.

Text bisturíes (and pdftotext) lose font info, so they can only guess headings
from ALL-CAPS and flatten everything to one level. For born-digital PDFs the font
SIZE (and weight) of a line is a reliable signal: a chapter title is set larger
than a section head, which is larger than body text. This tool reads per-line font
sizes with pdfminer, finds the body size, and classifies every larger standalone
short line into heading tiers (level 1 = biggest … down to body).

Two modes:
  (default)      print the detected heading outline (page · level · text)
  --apply-md DIR mark those headings in the markdown already in DIR: a standalone
                 line whose text matches a detected heading gets `##`/`###`… by
                 tier (H1/`#` is left to the chapter title the converter set).

Only useful on DIGITAL pdfs (pdffonts shows real embedded fonts). On image scans
(2 fonts / OCR) there is no size signal — fall back to the caps/heuristic path.

SUPERVISED, not blind: font size is a strong hint, not ground truth. The intended
flow is `--dry-run` first, eyeball the outline (are these real headings? right
depth?), THEN `--apply-md`, then re-read a chapter. The tool proposes; you decide.
`--apply-md` levels PER FILE relative to that file's `#` title (top size present →
`##`, next → `###`), so absolute front-matter sizes don't create false depth.

Usage:
  python3 pdf_headings.py book.pdf                       # show outline
  python3 pdf_headings.py book.pdf --min-gap 0.4         # size delta vs body (pt)
  python3 pdf_headings.py book.pdf --apply-md ./markdown # mark existing markdown
"""
from __future__ import annotations
import argparse, re, sys, unicodedata
from collections import Counter
from pathlib import Path


def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def iter_lines(pdf):
    """Yield (page_index, text, size, bold) for every text line."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTChar
    for pno, page in enumerate(extract_pages(pdf)):
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for line in el:
                if not hasattr(line, "__iter__"):
                    continue
                chs = [c for c in line if isinstance(c, LTChar)]
                if not chs:
                    continue
                out, prev = [], None
                for c in chs:                       # rebuild spaces from x-gaps
                    if prev is not None and c.x0 - prev > c.size * 0.25:
                        out.append(" ")
                    out.append(c.get_text()); prev = c.x1
                txt = re.sub(r"\s+", " ", "".join(out)).strip()
                if not txt:
                    continue
                size = round(sum(c.size for c in chs) / len(chs), 1)
                fn = Counter(c.fontname for c in chs).most_common(1)[0][0].lower()
                bold = any(k in fn for k in ("bold", "black", "semibold", "heavy"))
                yield pno, txt, size, bold


_SKIP = re.compile(r"intentionally left blank|^\W*$", re.I)

def looks_heading(txt):
    return (3 <= len(txt) <= 90 and len(txt.split()) <= 12
            and txt[0].isalpha() and txt[:1].isupper()
            and not txt.endswith((".", ",", ";", ":"))
            and not re.search(r"\|\s*\d+\s*$", txt)           # running head + page no.
            and not _SKIP.search(txt))


def cluster(sizes, tol=0.6):
    """Single-linkage cluster of font sizes; returns {size: cluster_center}."""
    uniq = sorted(set(sizes), reverse=True)
    groups, cur = [], []
    for s in uniq:
        if cur and cur[-1] - s <= tol:
            cur.append(s)
        else:
            if cur: groups.append(cur)
            cur = [s]
    if cur: groups.append(cur)
    return {s: round(sum(g) / len(g), 1) for g in groups for s in g}


def detect(pdf, min_gap, min_count=3):
    lines = list(iter_lines(pdf))
    body = Counter(s for _, t, s, _ in lines if len(t) > 45).most_common(1)
    body_size = body[0][0] if body else Counter(s for _, _, s, _ in lines).most_common(1)[0][0]
    raw = [(p, t, s, b) for p, t, s, b in lines
           if looks_heading(t) and (s >= body_size + min_gap or (b and s >= body_size + 0.1))]
    # cluster heading sizes; keep STRUCTURAL tiers (a cluster recurring >= min_count times)
    cmap = cluster([s for _, _, s, _ in raw])
    tier_count = Counter(cmap[s] for _, _, s, _ in raw)
    tiers = sorted([c for c, n in tier_count.items() if n >= min_count], reverse=True)
    level = {c: i + 1 for i, c in enumerate(tiers)}
    heads = [(p, t, s, b, level[cmap[s]]) for p, t, s, b in raw if cmap[s] in level]
    return body_size, heads, tiers


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--min-gap", type=float, default=0.4, help="min size delta over body to count as heading (pt)")
    ap.add_argument("--apply-md", type=Path, help="mark detected headings in the markdown files in this dir")
    ap.add_argument("--base-level", type=int, default=1, help="markdown level for the top heading tier (1=#, 2=##)")
    ap.add_argument("--dry-run", action="store_true", help="preview what --apply-md would mark, without writing")
    args = ap.parse_args()

    try:
        body_size, heads, tiers = detect(str(args.pdf), args.min_gap)
    except ImportError:
        sys.exit("needs pdfminer.six  (pip install pdfminer.six)")
    print(f"body ≈ {body_size}pt · {len(heads)} headings · structural tiers (pt→level): "
          f"{ {t: i+1 for i,t in enumerate(tiers)} }")

    if not args.apply_md:
        for p, t, s, b, lvl in heads:
            print(f"  p{p+1:>3} L{lvl} {s}pt{'*' if b else ' '} {'  '*(lvl-1)}{t}")
        return

    # apply: PER-FILE relative leveling. A file's # title is set by the converter;
    # the heading sizes present in that file are ranked -> ##, ###, … by size desc.
    want = {}                                   # norm(text) -> font size
    for _, t, s, b, lvl in heads:
        want.setdefault(norm(t), s)
    total = 0
    files = sorted(args.apply_md.glob("*.md"))
    for md in files:
        lines = md.read_text(encoding="utf-8").split("\n")
        present = sorted({want[norm(l.strip())] for l in lines
                          if l.strip() and not l.startswith("#") and norm(l.strip()) in want},
                         reverse=True)
        rank = {sz: args.base_level + 1 + i for i, sz in enumerate(present)}  # top present -> ##
        out, n = [], 0
        for ln in lines:
            s = ln.strip()
            if s and not s.startswith("#") and norm(s) in want and want[norm(s)] in rank:
                out.append("#" * min(6, rank[want[norm(s)]]) + " " + s); n += 1
            else:
                out.append(ln)
        if n and not args.dry_run:
            md.write_text("\n".join(out), encoding="utf-8")
        if n:
            print(f"  {md.name}: +{n} headings ({'/'.join('#'*min(6,rank[z]) for z in present)})")
        total += n
    print(f"{'[dry-run] ' if args.dry_run else ''}marked {total} headings across {len(files)} files")


if __name__ == "__main__":
    main()
