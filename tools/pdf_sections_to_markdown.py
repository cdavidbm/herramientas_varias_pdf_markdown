#!/usr/bin/env python3
"""
pdf_sections_to_markdown.py — Split a PDF into one markdown file per logical
section (title), using a pre-computed page-range plan.

Best suited to Calibre-produced PDFs (from EPUB) or any PDF with a clean text
layer and a detailed outline down to sub-title granularity.

Plan format (JSON) — same shape as split_pdf.py:
{
  "source": "path/to/book.pdf",          # optional if --pdf is given
  "output_dir": "markdown",              # optional; default: ./markdown
  "sections": [
    {"title": "Chapter 1 - ...",         # required
     "start": 24,                        # required: 1-based PDF page
     "end": 33},                         # required: inclusive 1-based PDF page
    ...
  ]
}

Output filenames: NNN_slugified-title.md (NNN = zero-padded sequence).

The body text is post-processed:
  * pdftotext default flow (paragraph-aware wrapping, no `-layout`)
  * soft hyphenation at line wrap is undone ("reali-\nty" -> "reality")
  * within-paragraph newlines become spaces
  * blank lines become paragraph breaks
  * the section's own title line, if echoed at the top of the page, is stripped
    (we re-emit it as `# Title`)

Usage:
  python3 pdf_sections_to_markdown.py plan.json
  python3 pdf_sections_to_markdown.py plan.json --pdf "/path/to/book.pdf" --out markdown/
  python3 pdf_sections_to_markdown.py plan.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text[:80] or "section"


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"error: required tool '{name}' is not installed (apt: poppler-utils)")


def pdf_page_count(pdf_path: Path) -> int:
    out = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("Could not determine page count")


def extract_text(pdf: Path, start: int, end: int) -> str:
    """Run pdftotext default flow for the page range and return raw text."""
    result = subprocess.run(
        ["pdftotext", "-f", str(start), "-l", str(end), str(pdf), "-"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


_TITLE_STRIP_CHARS = " \t\r\n.:;,'\"“”‘’()[]-—–"


def _normalize_for_match(s: str) -> str:
    return s.strip(_TITLE_STRIP_CHARS).lower()


def clean_section(raw: str, title: str) -> str:
    """Convert pdftotext output into a clean markdown body.

    Steps:
      1. Normalize whitespace and page form-feeds.
      2. Drop the echoed section title if it is among the first few lines.
      3. Undo soft hyphenation at line breaks within paragraphs.
      4. Collapse intra-paragraph newlines to spaces; keep blank-line breaks.
    """
    # Remove form-feed page separators pdftotext inserts between pages.
    text = raw.replace("\f", "\n\n")

    # Split into paragraphs on blank lines (1+ blank line).
    paragraphs = re.split(r"\n\s*\n", text)

    # Try to drop a title echo from the first 1-2 paragraphs.
    norm_title = _normalize_for_match(title)
    # The PDF outline sometimes uses "Chapter N: Foo" in the outline but only
    # "Foo" in the body (or vice versa). Try both forms.
    title_body_only = re.sub(r"^(chapter|appendix)\s+[\w]+\s*[:\-–—]\s*", "",
                             norm_title, flags=re.IGNORECASE)
    targets = {norm_title, title_body_only}
    targets = {t for t in targets if t}

    trimmed: list[str] = []
    dropped_title = False
    for idx, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue
        if not dropped_title and idx < 3:
            norm = _normalize_for_match(stripped.splitlines()[0])
            if norm in targets or (norm and any(norm.startswith(t) for t in targets)):
                # Drop this leading heading-only paragraph.
                dropped_title = True
                # If the paragraph had more than just the heading line, keep the rest.
                rest = stripped.split("\n", 1)
                if len(rest) == 2 and rest[1].strip():
                    trimmed.append(rest[1])
                continue
        trimmed.append(stripped)

    # Rejoin wrapped lines inside each paragraph.
    cleaned_paragraphs = []
    for para in trimmed:
        # Undo soft hyphenation: "word-\nnext" -> "wordnext" when letters surround it.
        p = re.sub(r"(\w)-\n(\w)", r"\1\2", para)
        # Any remaining single newlines become spaces.
        p = re.sub(r"\s*\n\s*", " ", p)
        # Collapse runs of spaces.
        p = re.sub(r"[ \t]{2,}", " ", p).strip()
        if p:
            cleaned_paragraphs.append(p)

    return "\n\n".join(cleaned_paragraphs)


def write_markdown(out_path: Path, title: str, body: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    out_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("plan", type=Path, help="Path to plan JSON file")
    parser.add_argument("--pdf", type=Path, help="Source PDF (overrides plan.source)")
    parser.add_argument("--out", type=Path, help="Output directory (overrides plan.output_dir)")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit")
    args = parser.parse_args()

    require_tool("pdftotext")
    require_tool("pdfinfo")

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    plan_dir = args.plan.parent.resolve()

    source = args.pdf or Path(plan.get("source", ""))
    if not source:
        sys.exit("error: no source PDF given (use --pdf or set 'source' in plan)")
    if not source.is_absolute():
        source = (plan_dir / source).resolve()
    if not source.is_file():
        sys.exit(f"error: source PDF not found: {source}")

    output_dir = args.out or Path(plan.get("output_dir", "markdown"))
    if not output_dir.is_absolute():
        output_dir = (plan_dir / output_dir).resolve()

    sections = plan.get("sections", [])
    if not sections:
        sys.exit("error: plan has no 'sections'")

    total_pages = pdf_page_count(source)

    print(f"Source  : {source}")
    print(f"Pages   : {total_pages}")
    print(f"Output  : {output_dir}")
    print(f"Sections: {len(sections)}")
    print()

    # Acepta las DOS formas de plan.json de La Forja: la escalar (start/end) y la
    # de lista `pages: [ini, fin]` (fin=null → hasta el final), que es la que
    # documenta CLAUDE.md y usan los demás conversores. Se normaliza a start/end.
    for i, sec in enumerate(sections):
        if "pages" in sec and "start" not in sec:
            pg = sec["pages"]
            if not isinstance(pg, (list, tuple)) or not pg:
                sys.exit(f"error: section #{i} 'pages' debe ser [ini, fin]")
            sec["start"] = pg[0]
            sec["end"] = (pg[1] if len(pg) > 1 and pg[1] is not None else total_pages)

    for i, sec in enumerate(sections):
        for key in ("title", "start", "end"):
            if key not in sec:
                sys.exit(f"error: section #{i} missing '{key}'")
        if not (1 <= sec["start"] <= sec["end"] <= total_pages):
            sys.exit(
                f"error: section '{sec['title']}' has invalid range "
                f"{sec['start']}..{sec['end']} (total pages: {total_pages})"
            )

    width = max(3, len(str(len(sections) - 1)))
    planned: list[tuple[Path, str, int, int]] = []
    for i, sec in enumerate(sections):
        name = f"{str(i).zfill(width)}_{slugify(sec['title'])}.md"
        out = output_dir / name
        planned.append((out, sec["title"], sec["start"], sec["end"]))
        print(f"  [{i:03d}] p.{sec['start']:>4}-{sec['end']:<4} -> {name}")

    if args.dry_run:
        return 0

    print()
    for out, title, start, end in planned:
        raw = extract_text(source, start, end)
        body = clean_section(raw, title)
        write_markdown(out, title, body)
        size = len(body)
        print(f"  wrote {out.name} ({end - start + 1} pp, {size} chars)")

    print(f"\nDone. {len(planned)} files written to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
