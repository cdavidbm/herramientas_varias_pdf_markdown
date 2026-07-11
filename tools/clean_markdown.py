#!/usr/bin/env python3
"""
clean_markdown.py — Post-process Docling (or similar) Markdown into clean,
study-ready text WITHOUT destroying legitimate repeated content.

What it fixes, in order:
  1. Base64-embedded images  ->  extracted to `imagen-NN.<ext>` files next to the
     output and referenced by relative path (drops huge inline blobs).
  2. Soft hyphens (U+00AD), including "mel<shy> ancholic" -> "melancholic".
  3. Running page-headers that OCR/Docling promoted to `##` headings. A heading
     is treated as page furniture and removed ONLY when it is either
       (a) a *recent* duplicate — the same heading text already appeared as a
           heading within the last --window lines (running headers repeat every
           page; ~10-20 lines apart), or
       (b) sentence-interrupting — the previous non-blank line does not end in
           terminal punctuation AND the next non-blank line starts lowercase
           (a header dropped into the middle of a paragraph across a page break);
           in this case the split sentence is rejoined.
     A heading whose text repeats only far apart (e.g. an Al-Biruni category
     that recurs once per planet) is KEPT — that is real content, not furniture.
     Markers in --keep-markers (default: [COMMENT], [QUOTE, [TEXT], [NATURES)
     are never touched.
  4. Justified-text spacing: runs of 2+ spaces inside prose collapse to one
     (tables, code fences, headings and image lines are left alone).
  5. 3+ blank lines collapse to one blank line.

The original file is left untouched unless --in-place is given; by default the
result goes to <input>.clean.md (or --out).

Usage:
  python3 clean_markdown.py book.md
  python3 clean_markdown.py book.md --in-place
  python3 clean_markdown.py book.md --out clean.md --window 60
  python3 clean_markdown.py book.md --keep-markers "[COMMENT]" "[NOTE]"
"""
from __future__ import annotations

import argparse
import base64
import re
from pathlib import Path

DEFAULT_KEEP = ("[COMMENT]", "[QUOTE", "[END OF QUOTE]", "[TEXT]", "[NATURES")
IMG_RE = re.compile(r"!\[[^\]]*\]\(data:image/(png|jpeg|jpg);base64,([^)]+)\)")
TERMINAL = (".", "!", "?", ":", '"', "”", ")", "-", "—", "")


def extract_images(lines, outdir):
    n = 0

    def repl(m):
        nonlocal n
        n += 1
        ext = "png" if m.group(1) == "png" else "jpg"
        fname = f"imagen-{n:02d}.{ext}"
        (outdir / fname).write_bytes(base64.b64decode(m.group(2)))
        return f"![Imagen {n}]({fname})"

    return [IMG_RE.sub(repl, ln) for ln in lines], n


def is_heading(ln):
    return ln.startswith("## ")


def ends_terminal(s):
    s = s.rstrip()
    return s == "" or s.endswith(TERMINAL)


def clean(text, outdir, window=60, keep_markers=DEFAULT_KEEP):
    # 1) images
    lines = text.split("\n")
    lines, n_img = extract_images(lines, outdir)

    # 2) soft hyphens
    lines = [ln.replace("­ ", "").replace("­", "") for ln in lines]

    def is_marker(h):
        return any(m in h for m in keep_markers)

    # 3) running headers
    body = "\n".join(lines)
    out, recent = [], {}
    n_dropped = n_joined = 0
    i, N = 0, len(lines)
    while i < N:
        ln = lines[i]
        s = ln.strip()
        if is_heading(s) and not is_marker(s):
            seen_at = recent.get(s)
            recent_dup = seen_at is not None and (len(out) - seen_at) <= window
            prev = next((out[k] for k in range(len(out) - 1, -1, -1)
                         if out[k].strip()), "")
            j = i + 1
            while j < N and lines[j].strip() == "":
                j += 1
            nxt = lines[j] if j < N else ""
            interrupts = prev != "" and not ends_terminal(prev) and nxt[:1].islower()
            if recent_dup or interrupts:
                if interrupts:
                    n_joined += 1
                    for k in range(len(out) - 1, -1, -1):
                        if out[k].strip():
                            out[k] = out[k].rstrip() + " " + lines[j].lstrip()
                            break
                    i = j + 1
                    continue
                n_dropped += 1
                i += 1
                while i < N and lines[i].strip() == "":
                    i += 1
                continue
            recent[s] = len(out)
        out.append(ln)
        i += 1

    # 4) collapse justified spacing (skip tables/code/headings/images)
    def collapse(ln):
        s = ln.lstrip()
        if s.startswith(("|", "```", "#", "![", "<!--")):
            return ln
        return re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", ln)

    result = "\n".join(collapse(x) for x in out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result, dict(images=n_img, headers_dropped=n_dropped, sentences_rejoined=n_joined)


def main():
    ap = argparse.ArgumentParser(description="Clean Docling markdown safely.")
    ap.add_argument("input")
    ap.add_argument("--out", help="output path (default <input>.clean.md)")
    ap.add_argument("--in-place", action="store_true", help="overwrite the input")
    ap.add_argument("--window", type=int, default=60,
                    help="lines within which an identical heading is a running header (default 60)")
    ap.add_argument("--keep-markers", nargs="*", default=list(DEFAULT_KEEP),
                    help="heading markers that may legitimately repeat")
    args = ap.parse_args()

    src = Path(args.input)
    outdir = src.parent
    text = src.read_text(encoding="utf-8")
    result, stats = clean(text, outdir, args.window, tuple(args.keep_markers))

    dst = src if args.in_place else Path(args.out) if args.out else src.with_suffix(".clean.md")
    dst.write_text(result, encoding="utf-8")
    print(f"images extracted : {stats['images']}")
    print(f"running headers  : {stats['headers_dropped']} dropped")
    print(f"split sentences  : {stats['sentences_rejoined']} rejoined")
    print(f"written          : {dst}")


if __name__ == "__main__":
    main()
