#!/usr/bin/env python3
"""
split_pdf_spreads.py — Turn a 2-up scanned PDF (two book pages per physical
page) into a 1-up PDF (one book page per physical page).

Typical case: a book scanned with the book held open, so every physical page
contains left-and-right book pages side by side. Tools like NotebookLM will
OCR such pages as if each line spanned both halves, which ruins reading order.
This script cuts each wide page vertically down the middle into two pages
(left then right), so the output reads like the original book.

Narrow / portrait pages (covers, colophons, single-page inserts) are detected
by aspect ratio and passed through untouched — unless `--split-all` is set.

Backend: `mutool poster` (mupdf-tools) to split, `pdfseparate` / `pdfunite`
(poppler-utils) to slice and re-stitch. No Python PDF library required.

Usage:
  python3 split_pdf_spreads.py input.pdf [output.pdf]
  python3 split_pdf_spreads.py input.pdf out.pdf --threshold 1.1
  python3 split_pdf_spreads.py input.pdf out.pdf --order rl     # right-to-left (manga/arabic)
  python3 split_pdf_spreads.py input.pdf out.pdf --split-all    # force-split every page
  python3 split_pdf_spreads.py input.pdf --dry-run              # report plan, no output
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from forja_common import require_tool





def page_sizes(pdf: Path) -> list[tuple[float, float]]:
    """Return a list of (width, height) in points for every page."""
    out = subprocess.check_output(
        ["pdfinfo", "-f", "1", "-l", "999999", str(pdf)], text=True
    )
    sizes: dict[int, tuple[float, float]] = {}
    for line in out.splitlines():
        # "Page   42 size:  842.4 x 612.96 pts"
        line = line.strip()
        if not line.startswith("Page "):
            continue
        try:
            rest = line.split("Page", 1)[1].strip()
            num_part, size_part = rest.split("size:", 1)
            n = int(num_part.strip())
            w_str, _, h_str = size_part.strip().split()[0:3]
            sizes[n] = (float(w_str), float(h_str))
        except (ValueError, IndexError):
            continue
    if not sizes:
        raise RuntimeError("could not parse any page sizes from pdfinfo")
    return [sizes[i] for i in sorted(sizes)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path, nargs="?")
    ap.add_argument(
        "--threshold",
        type=float,
        default=1.05,
        help="aspect ratio (w/h) at which a page is considered a 2-up spread "
        "and split (default: 1.05). Pages below this pass through.",
    )
    ap.add_argument(
        "--order",
        choices=("lr", "rl"),
        default="lr",
        help="reading order: 'lr' = left half then right (default); "
        "'rl' = right half then left (manga / Arabic / Hebrew).",
    )
    ap.add_argument(
        "--split-all",
        action="store_true",
        help="split every page regardless of aspect ratio.",
    )
    ap.add_argument(
        "--split-none-below",
        type=int,
        default=0,
        help="never split pages with number < N (1-based). Useful when the "
        "first few pages are title/cover spreads you don't want split.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    require_tool("pdfinfo")
    require_tool("pdfseparate")
    require_tool("pdfunite")
    require_tool("mutool")

    if not args.input.is_file():
        sys.exit(f"input PDF not found: {args.input}")

    output = args.output
    if output is None:
        output = args.input.with_name(args.input.stem + "_1up.pdf")

    sizes = page_sizes(args.input)
    total = len(sizes)

    # Decide per-page action
    actions: list[tuple[int, str]] = []  # (page_num, "split" | "keep")
    for i, (w, h) in enumerate(sizes, 1):
        if i < args.split_none_below:
            actions.append((i, "keep"))
            continue
        if args.split_all:
            actions.append((i, "split"))
            continue
        ratio = w / h if h else 1.0
        actions.append((i, "split" if ratio >= args.threshold else "keep"))

    n_split = sum(1 for _, a in actions if a == "split")
    n_keep = total - n_split
    out_pages = n_keep + 2 * n_split

    print(f"Input       : {args.input}")
    print(f"Pages       : {total}  ({n_keep} portrait kept, {n_split} landscape split)")
    print(f"Output      : {output}")
    print(f"Output pages: {out_pages}")
    print(f"Order       : {'left then right' if args.order == 'lr' else 'right then left'}")
    if args.dry_run:
        print("\nFirst 12 planned actions:")
        for i, (n, a) in enumerate(actions[:12]):
            w, h = sizes[n - 1]
            print(f"  p.{n:>4}  {w:>7.1f}x{h:<7.1f}  -> {a}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pieces: list[Path] = []

        for n, action in actions:
            single = tmp_path / f"src-{n:05d}.pdf"
            subprocess.run(
                [
                    "pdfseparate",
                    "-f", str(n), "-l", str(n),
                    str(args.input), str(single),
                ],
                check=True,
            )
            if action == "keep":
                pieces.append(single)
                continue

            split = tmp_path / f"split-{n:05d}.pdf"
            subprocess.run(
                ["mutool", "poster", "-x", "2", "-y", "1", str(single), str(split)],
                check=True,
                stdout=subprocess.DEVNULL,
            )

            if args.order == "lr":
                pieces.append(split)
            else:
                # Right-half-first: extract pages 2, 1 in that order
                left = tmp_path / f"left-{n:05d}.pdf"
                right = tmp_path / f"right-{n:05d}.pdf"
                subprocess.run(
                    ["pdfseparate", "-f", "1", "-l", "1", str(split), str(left)],
                    check=True,
                )
                subprocess.run(
                    ["pdfseparate", "-f", "2", "-l", "2", str(split), str(right)],
                    check=True,
                )
                pieces.append(right)
                pieces.append(left)

            if n % 25 == 0 or n == total:
                print(f"  processed {n}/{total}")

        # Concatenate in chunks to avoid command-line length limits on very long books
        chunk_size = 200
        if len(pieces) <= chunk_size:
            subprocess.run(
                ["pdfunite", *[str(p) for p in pieces], str(output)], check=True
            )
        else:
            merged: list[Path] = []
            for i in range(0, len(pieces), chunk_size):
                batch = pieces[i : i + chunk_size]
                out_batch = tmp_path / f"batch-{i // chunk_size:04d}.pdf"
                subprocess.run(
                    ["pdfunite", *[str(p) for p in batch], str(out_batch)], check=True
                )
                merged.append(out_batch)
            subprocess.run(
                ["pdfunite", *[str(p) for p in merged], str(output)], check=True
            )

    print(f"\nDone. Wrote {output} ({out_pages} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
