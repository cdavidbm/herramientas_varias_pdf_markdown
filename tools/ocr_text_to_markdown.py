#!/usr/bin/env python3
"""
ocr_text_to_markdown.py — Slice a plain OCR TEXT dump into per-chapter markdown.

The text-input sibling of pdf_sections_to_markdown.py. Use it when the scan's
searchable-PDF text layer is NOT extractable by pdftotext (some recoded /
LuraDocument scans embed OCR text without ToUnicode), so you OCR'd to a plain
sidecar instead — e.g. `ocr_incremental.py book.pdf --engine tesseract
--sidecar-out book_ocr.txt`, which writes all pages form-feed (\\f) separated.

Given a page-range plan (same schema as pdf_sections_to_markdown / split_pdf) it,
per section:
  - drops the page running-head (first line matching plan `running_heads`) and
    lone page-number / roman-numeral lines,
  - de-hyphenates line-break hyphens and reflows OCR hard-wrapped lines into
    real paragraphs (blank line = paragraph break),
  - marks ALL-CAPS short lines as `##` section headings (skips `:`-bearing rows
    so verse/translation tables don't become headings) and uses the plan title
    as the `#` H1 (dropping the duplicated printed title block),
  - splits an end-of-chapter `NOTES` section into `[^N]:` definitions.

It does NOT fix book-specific OCR corruption (garbled Greek transliterations,
etc.) or link body note markers — do that as a separate cleaning pass, or let a
context-aware translation step normalise it.

Usage:
  python3 ocr_text_to_markdown.py plan.json --text book_ocr.txt
  python3 ocr_text_to_markdown.py plan.json --text book_ocr.txt --out markdown/
  python3 ocr_text_to_markdown.py plan.json --text book_ocr.txt --only Chapter1
"""
from __future__ import annotations
import argparse, json, re, sys, unicodedata
from pathlib import Path


def fold(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--text", type=Path, required=True, help="OCR sidecar text, pages \\f-separated")
    ap.add_argument("--out", type=Path, help="output dir (default plan output_dir or ./markdown)")
    ap.add_argument("--only", help="process only sections whose slug contains this substring")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    pages = args.text.read_text(encoding="utf-8", errors="replace").split("\f")
    outdir = args.out or Path(plan.get("output_dir", "markdown"))
    run_heads = [fold(h) for h in plan.get("running_heads", [])]

    def is_runhead(line):
        f = fold(line)
        return bool(f) and any(f == h or (len(f) > 8 and (f in h or h in f)) for h in run_heads)

    def is_pagenum(line):
        s = line.strip()
        return bool(re.fullmatch(r"[ivxlcIVXLC]{1,7}", s)) or bool(re.fullmatch(r"\d{1,4}", s))

    def is_heading(p):
        letters = [c for c in p if c.isalpha()]
        if len(letters) < 3 or ":" in p:
            return False
        up = sum(1 for c in letters if c.isupper()) / len(letters)
        return up >= 0.85 and len(p) <= 90 and not p.endswith(".") and len(p.split()) <= 14

    def clean_pages(a, b):
        out = []
        for pi in range(a, b + 1):
            lines = pages[pi - 1].split("\n")
            i = 0
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            if i < len(lines) and (is_runhead(lines[i]) or is_pagenum(lines[i])):
                i += 1
                if i < len(lines) and lines[i].strip() == "":
                    i += 1
            for ln in lines[i:]:
                if is_pagenum(ln) and ln.strip():
                    continue
                out.append(ln)
        return out

    def reflow(lines):
        paras, cur = [], []
        def flush():
            if cur:
                paras.append(" ".join(cur).strip()); cur.clear()
        for ln in lines:
            s = ln.rstrip()
            if s.strip() == "":
                flush(); continue
            if cur and re.search(r"[A-Za-z]-$", cur[-1]):
                cur[-1] = cur[-1][:-1] + s.lstrip()
            elif cur:
                cur[-1] = cur[-1] + " " + s.strip()
            else:
                cur.append(s.strip())
        flush()
        return [p for p in paras if p]

    def parse_notes(note_lines):
        entries, num, buf = [], None, []
        def flush():
            if num is not None:
                entries.append((num, " ".join(reflow(buf)).strip()))
        for ln in note_lines:
            m = re.match(r"^(\d{1,3})\.\s+(.*)", ln)
            if m:
                flush(); num = int(m.group(1)); buf = [m.group(2)]
            else:
                buf.append(ln)
        flush()
        return entries

    def build(section):
        a, b = section["pages"]
        b = b if b else len(pages)
        lines = clean_pages(a, b)
        ni = next((i for i, l in enumerate(lines) if l.strip() in ("NOTES", "Notes")), None)
        body_lines = lines[:ni] if ni is not None else lines
        note_lines = lines[ni + 1:] if ni is not None else []
        md = [f"# {section['title']}", ""]
        started = False
        for p in reflow(body_lines):
            if not started:
                if is_heading(p):
                    md += [f"## {p}", ""]; started = True; continue
                if len(p.split()) < 15:
                    continue
                started = True
            md += ([f"## {p}"] if is_heading(p) else [p]) + [""]
        notes = parse_notes(note_lines)
        if notes:
            md += ["## Notes", ""] + [f"[^{n}]: {t}" for n, t in notes]
        return "\n".join(md).rstrip() + "\n", len(reflow(body_lines)), len(notes)

    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
    for s in plan["sections"]:
        if args.only and args.only not in s["slug"]:
            continue
        text, nparas, nnotes = build(s)
        dest = outdir / f"{s['slug']}.md"
        print(f"  {s['slug']:42} paras={nparas:>3} notes={nnotes:>3} -> {dest.name}"
              + (" (dry-run)" if args.dry_run else ""))
        if not args.dry_run:
            dest.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
