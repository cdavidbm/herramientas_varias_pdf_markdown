#!/usr/bin/env python3
"""
pdf_blocks.py — Recover BLOCK QUOTES from a DIGITAL pdf by font size + indentation.

Extended quotations (and verse, epigraphs) are set off in the original by a SMALLER
font and/or a deeper left indent — a signal text extraction throws away, so the
bisturí emits them as ordinary body paragraphs, often fragmented by spurious blank
lines. This reads per-line font size AND left position (x0) with pdfminer, finds the
body's size/margin, groups the indented/smaller lines into quote BLOCKS, and (in
apply mode) marks the matching markdown as a `>` blockquote — joining the fragments
into one readable quote.

Companion of pdf_headings.py (headings by size); same philosophy:

SUPERVISED, not blind. `--dry-run` first, read the detected blocks (are these really
quotes? any body caught?), THEN `--apply-md`, then re-read a chapter. It proposes;
you decide. Digital pdfs only — image/OCR scans have no size/indent signal, use an
agent pass there.

Two modes:
  (default)      print the detected quote blocks (page · first words)
  --apply-md DIR wrap the matching paragraphs in DIR's markdown as a `>` blockquote

Usage:
  python3 pdf_blocks.py book.pdf                          # list detected quotes
  python3 pdf_blocks.py book.pdf --indent 16 --size-drop 0.3
  python3 pdf_blocks.py book.pdf --apply-md ./markdown --dry-run
"""
from __future__ import annotations
import argparse, re, sys, unicodedata
from collections import Counter
from pathlib import Path


def norm(s):
    # letters only: drops spaces, punctuation AND digits so scattered footnote numbers
    # / dates don't break the alignment between the PDF quote and the markdown paragraphs.
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.lower())


def iter_lines(pdf):
    """Yield (page, text, size, x0) for every text line, spaces rebuilt from x-gaps."""
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
                for c in chs:
                    if prev is not None and c.x0 - prev > c.size * 0.25:
                        out.append(" ")
                    out.append(c.get_text()); prev = c.x1
                txt = re.sub(r"\s+", " ", "".join(out)).strip()
                if txt:
                    yield (pno, txt, round(sum(c.size for c in chs) / len(chs), 1),
                           round(min(c.x0 for c in chs)))


def dehyph(a, b):
    return a[:-1] + b if re.search(r"[A-Za-zÀ-ÿ]-$", a) else a + " " + b


def detect(pdf, indent, size_drop, min_chars):
    lines = list(iter_lines(pdf))
    body_size = Counter(s for _, t, s, _ in lines if len(t) > 45).most_common(1)[0][0]
    body_x0 = Counter(x for _, t, s, x in lines if len(t) > 45).most_common(1)[0][0]

    FURNITURE = re.compile(r"\|\s*\d+\s*$|^\s*\d+\s*\||^\d{1,4}$")   # running head / page no.

    def is_quote(t, s, x):
        # indented well past the paragraph first-line indent, and not set LARGER than
        # body (that would be a heading, not a quote). A smaller font strengthens it.
        return x >= body_x0 + indent and s <= body_size + 0.1 and not FURNITURE.search(t)

    blocks, cur, start = [], [], None
    def flush():
        if cur:
            txt = ""
            for ln in cur:
                txt = ln if not txt else dehyph(txt, ln)
            if len(txt) >= min_chars:
                blocks.append((start, txt))
    for p, t, s, x in lines:
        if is_quote(t, s, x):
            if not cur:
                start = p
            cur.append(t)
        elif cur and FURNITURE.search(t):
            continue                         # page break inside a quote: skip, keep it open
        else:
            flush(); cur = []
    flush()
    return body_size, body_x0, blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--indent", type=float, default=16, help="left-indent (pt) past body margin to count as quote")
    ap.add_argument("--size-drop", type=float, default=0.3, help="how much smaller than body the quote font is (pt)")
    ap.add_argument("--min-chars", type=int, default=60, help="ignore indented runs shorter than this")
    ap.add_argument("--apply-md", type=Path, help="wrap matching paragraphs in this markdown dir as `>` blockquotes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        body_size, body_x0, blocks = detect(str(args.pdf), args.indent, args.size_drop, args.min_chars)
    except ImportError:
        sys.exit("needs pdfminer.six  (pip install pdfminer.six)")
    print(f"body ≈ {body_size}pt @ x0={body_x0} · {len(blocks)} quote block(s)")

    if not args.apply_md:
        for p, t in blocks:
            print(f"  p{p+1:>3} «{t[:70]}…»" if len(t) > 70 else f"  p{p+1:>3} «{t}»")
        return

    # apply: find each block as a run of consecutive markdown paragraphs, replace with `>`.
    # skip back-matter (index/notes/…): it is indented too, but those are not quotes.
    BACKMATTER = re.compile(r"index|notes|bibliograph|contents|illustrations|plates|glossary", re.I)
    bnorm = [(norm(t), t) for _, t in blocks if norm(t)]
    allfiles = sorted(args.apply_md.glob("*.md"))
    files = [f for f in allfiles if not BACKMATTER.search(f.name)]
    total = 0
    for md in files:
        raw = md.read_text(encoding="utf-8")
        paras = re.split(r"\n\s*\n", raw)
        used = [False] * len(paras)
        n = 0
        for bn, btext in bnorm:
            for i in range(len(paras)):
                if paras[i] is None or used[i] or paras[i].lstrip().startswith(("#", ">")):
                    continue
                if not bn.startswith(norm(paras[i])[:24]):   # quick reject
                    continue
                acc = ""
                for j in range(i, min(i + 25, len(paras))):
                    if paras[j] is None or paras[j].lstrip().startswith(("#", ">")):
                        break
                    before = acc
                    acc = before + norm(paras[j])
                    clean = acc == bn or (acc.startswith(bn) and len(acc) - len(bn) <= 8)
                    if clean:                        # block ends at paragraph j's boundary
                        quote = re.sub(r"\s+", " ", " ".join(p.strip() for p in paras[i:j + 1])).strip()
                        if len(quote) < 20:
                            break
                        paras[i] = "> " + quote
                        for k in range(i + 1, j + 1):
                            paras[k] = None; used[k] = True
                        used[i] = True; n += 1
                        break
                    if acc.startswith(bn):           # block ends INSIDE paragraph j -> split it
                        remaining = len(bn) - len(before)
                        cnt, si = 0, len(paras[j])
                        for idx, ch in enumerate(paras[j]):
                            if ch.isalpha():
                                cnt += 1
                            if cnt == remaining:
                                si = idx + 1; break
                        while si < len(paras[j]) and paras[j][si] not in " \t":   # keep footnote no./punct
                            si += 1
                        tail, rest = paras[j][:si].strip(), paras[j][si:].strip()
                        quote = re.sub(r"\s+", " ", " ".join(p.strip() for p in paras[i:j]) + " " + tail).strip()
                        if len(quote) < 20:
                            break
                        paras[i] = "> " + quote
                        for k in range(i + 1, j):
                            paras[k] = None; used[k] = True
                        paras[j] = rest or None
                        used[i] = True
                        if paras[j] is None:
                            used[j] = True
                        n += 1
                        break
                    if not bn.startswith(acc):       # diverged -> no match from i
                        break
                if used[i]:
                    break
        if n:
            newraw = "\n\n".join(p for p in paras if p is not None)
            if not args.dry_run:
                md.write_text(newraw, encoding="utf-8")
            print(f"  {md.name}: {n} blockquote(s)")
        total += n
    print(f"{'[dry-run] ' if args.dry_run else ''}wrapped {total} blockquotes across {len(files)} files")


if __name__ == "__main__":
    main()
