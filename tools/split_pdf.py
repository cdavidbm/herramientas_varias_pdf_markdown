#!/usr/bin/env python3
"""
split_pdf.py — Split a PDF into multiple PDFs based on a chapters plan.

Backend: poppler's `pdfseparate` + `pdfunite` (no Python PDF deps required).

Plan format (JSON):
{
  "source": "path/to/book.pdf",          # optional if --pdf is given
  "output_dir": "chapters",              # optional; default: ./chapters
  "sections": [
    {"title": "Introduction",            # required
     "start": 11,                        # required: 1-based PDF page
     "end": 20},                         # required: inclusive 1-based PDF page
    ...
  ]
}

Filenames are auto-generated as:
  NN_slugified-title.pdf    (NN = zero-padded index starting at 00)

Usage:
  python3 split_pdf.py plan.json
  python3 split_pdf.py plan.json --pdf "/path/to/book.pdf" --out chapters/
  python3 split_pdf.py plan.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
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


def split_section(
    source_pdf: Path,
    start: int,
    end: int,
    output_pdf: Path,
) -> None:
    """Extract pages [start..end] (1-based, inclusive) from source_pdf into output_pdf."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pattern = str(tmp_path / "page-%04d.pdf")
        subprocess.run(
            ["pdfseparate", "-f", str(start), "-l", str(end), str(source_pdf), pattern],
            check=True,
        )
        page_files = sorted(tmp_path.glob("page-*.pdf"))
        if not page_files:
            raise RuntimeError(f"pdfseparate produced no pages for {start}..{end}")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["pdfunite", *[str(p) for p in page_files], str(output_pdf)],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path, help="Path to plan JSON file")
    parser.add_argument("--pdf", type=Path, help="Source PDF (overrides plan.source)")
    parser.add_argument("--out", type=Path, help="Output directory (overrides plan.output_dir)")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit")
    args = parser.parse_args()

    require_tool("pdfseparate")
    require_tool("pdfunite")
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

    output_dir = args.out or Path(plan.get("output_dir", "chapters"))
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

    # Validate first
    for i, sec in enumerate(sections):
        for key in ("title", "start", "end"):
            if key not in sec:
                sys.exit(f"error: section #{i} missing '{key}'")
        if not (1 <= sec["start"] <= sec["end"] <= total_pages):
            sys.exit(
                f"error: section '{sec['title']}' has invalid range "
                f"{sec['start']}..{sec['end']} (total pages: {total_pages})"
            )

    # Preview
    width = len(str(len(sections) - 1))
    planned: list[tuple[Path, int, int]] = []
    for i, sec in enumerate(sections):
        name = f"{str(i).zfill(max(2, width))}_{slugify(sec['title'])}.pdf"
        out = output_dir / name
        planned.append((out, sec["start"], sec["end"]))
        print(f"  [{i:02d}] p.{sec['start']:>4}-{sec['end']:<4} -> {name}")

    if args.dry_run:
        return 0

    print()
    for out, start, end in planned:
        print(f"  writing {out.name} ({end - start + 1} pages)...")
        split_section(source, start, end, out)

    print(f"\nDone. {len(planned)} files written to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
