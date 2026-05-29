#!/usr/bin/env python3
"""
detect_chapters.py — Scan a PDF for candidate chapter start pages.

This is a helper that prints the 1-based PDF page numbers where lines matching
common chapter/section markers appear. Use its output to hand-craft a plan.json
for split_pdf.py.

It detects lines such as:
  INTRODUCTION
  CHAPTER ONE / CHAPTER 1
  PART I
  CONCLUSION / EPILOGUE / PREFACE / FOREWORD
  BIBLIOGRAPHY / INDEX / APPENDIX

Usage:
  python3 detect_chapters.py path/to/book.pdf
  python3 detect_chapters.py path/to/book.pdf --pattern "^SECTION\\s"
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PATTERN = (
    r"^\s*("
    r"INTRODUCTION|CONCLUSION|EPILOGUE|PREFACE|FOREWORD|ACKNOWLEDGEMENTS?|"
    r"BIBLIOGRAPHY|INDEX|APPENDIX(?:\s+[A-Z0-9]+)?|"
    r"CHAPTER\s+[A-Z0-9]+|"
    r"PART\s+[IVXLCDM0-9]+|"
    r"BOOK\s+[IVXLCDM0-9]+"
    r")\s*$"
)


def page_count(pdf: Path) -> int:
    out = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("page count not found")


def page_text(pdf: Path, n: int) -> str:
    return subprocess.check_output(
        ["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(pdf), "-"],
        text=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN,
                    help="Regex applied per-line (default matches common chapter markers)")
    ap.add_argument("--context", type=int, default=1,
                    help="Lines of context to display with each hit (default 1)")
    args = ap.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"not a file: {args.pdf}")

    rx = re.compile(args.pattern, re.IGNORECASE | re.MULTILINE)
    total = page_count(args.pdf)
    print(f"scanning {total} pages of {args.pdf.name}\n")

    hits: list[tuple[int, str]] = []
    for n in range(1, total + 1):
        text = page_text(args.pdf, n)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if rx.match(line):
                ctx_start = max(0, i - 0)
                ctx_end = min(len(lines), i + 1 + args.context)
                snippet = "\n    ".join(l for l in lines[ctx_start:ctx_end] if l.strip())
                hits.append((n, snippet))
                break

    if not hits:
        print("no candidate chapter markers found; try a custom --pattern")
        return 1

    print(f"{len(hits)} candidate(s):\n")
    for n, snippet in hits:
        print(f"  p.{n:>4}: {snippet}")
    print()
    print("next step: craft a plan.json with these pages, then run split_pdf.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
