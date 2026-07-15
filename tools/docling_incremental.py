#!/usr/bin/env python3
"""
docling_incremental.py — Run Docling over a PDF in page BATCHES, saving progress
after every batch so a long scan can survive an interruption (closed laptop,
Ctrl-C, crash) and RESUME instead of starting over.

Why: `docling convert` processes the whole document in memory and only writes the
Markdown at the very end. On a 230-page scanned book that is hours of OCR with
nothing on disk until the finish line. This wrapper slices the PDF into batches
(qpdf), runs `docling convert` on each, writes `parts/part_NNNN.md` immediately,
prints progress, and on a re-run SKIPS batches whose part file already exists.
When all batches are done it concatenates them into `<stem>.md`.

Trade-offs (honest):
  * Docling reloads its models once per batch (a few seconds each). Use a larger
    --batch to amortise this; the point here is safety/visibility, not raw speed.
    For PDFs that already carry a text layer (e.g. ABBYY OCR), add --no-ocr for a
    big speed-up — the text layer is used and per-image OCR is skipped.
  * A table or footnote that straddles a batch boundary may split; keep batches
    generous (default 15) and glue at the seams if needed.

Requires: `docling`, `qpdf`, `pdfinfo` (poppler) on PATH — all in setup.sh.

Usage:
  python3 docling_incremental.py book.pdf --out ./markdown
  python3 docling_incremental.py book.pdf --out ./markdown --batch 20 --no-ocr
  python3 docling_incremental.py book.pdf --out ./markdown   # re-run = resume
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def page_count(pdf):
    out = sh(["pdfinfo", str(pdf)]).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise SystemExit("could not read page count (pdfinfo failed)")


def main():
    ap = argparse.ArgumentParser(description="Docling with per-batch checkpointing + resume.")
    ap.add_argument("pdf")
    ap.add_argument("--out", default="markdown", help="output directory (default ./markdown)")
    ap.add_argument("--batch", type=int, default=15, help="pages per batch (default 15)")
    ap.add_argument("--image-export-mode", default="placeholder",
                    choices=["placeholder", "embedded", "referenced"])
    ap.add_argument("--no-ocr", action="store_true",
                    help="skip OCR and use the PDF text layer (fast; for ABBYY/born-digital PDFs)")
    ap.add_argument("--num-threads", type=int, default=4)
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    outdir = Path(args.out)
    parts = outdir / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    tmp = parts / "_tmp"
    tmp.mkdir(exist_ok=True)

    total = page_count(pdf)
    batches = [(a, min(a + args.batch - 1, total)) for a in range(1, total + 1, args.batch)]
    print(f"{pdf.name}: {total} pages -> {len(batches)} batch(es) of {args.batch}")

    for k, (a, b) in enumerate(batches, 1):
        part = parts / f"part_{k:04d}.md"
        if part.exists() and part.stat().st_size > 0:
            print(f"  [{k}/{len(batches)}] pages {a}-{b}  ✓ resume (already done)")
            continue
        t0 = time.time()
        batch_pdf = tmp / f"batch_{k:04d}.pdf"
        r = sh(["qpdf", "--empty", "--pages", str(pdf), f"{a}-{b}", "--", str(batch_pdf)])
        if r.returncode != 0 or not batch_pdf.exists():
            sys.exit(f"qpdf failed on pages {a}-{b}:\n{r.stderr}")
        cmd = ["docling", "convert", str(batch_pdf), "--to", "md",
               "--image-export-mode", args.image_export_mode,
               "--device", "cpu", "--num-threads", str(args.num_threads),
               "--output", str(tmp)]
        cmd += ["--no-ocr"] if args.no_ocr else []
        r = sh(cmd)
        produced = tmp / f"{batch_pdf.stem}.md"
        if r.returncode != 0 or not produced.exists():
            sys.exit(f"docling failed on pages {a}-{b}:\n{r.stderr[-2000:]}")
        # Escritura ATÓMICA: si el proceso muere a mitad del write, un `part`
        # truncado existiría y el resume (part.exists() and st_size>0) lo daría por
        # bueno, perdiendo páginas. Escribir a .tmp y os.replace (rename atómico).
        part_tmp = part.with_name(part.name + ".tmp")
        part_tmp.write_text(produced.read_text(encoding="utf-8"), encoding="utf-8")
        os.replace(part_tmp, part)
        produced.unlink(missing_ok=True)
        batch_pdf.unlink(missing_ok=True)
        print(f"  [{k}/{len(batches)}] pages {a}-{b}  ✓ {time.time()-t0:.0f}s "
              f"({part.stat().st_size//1024} KB)", flush=True)

    # concatenate
    final = outdir / f"{pdf.stem}.md"
    with final.open("w", encoding="utf-8") as fh:
        for k in range(1, len(batches) + 1):
            fh.write((parts / f"part_{k:04d}.md").read_text(encoding="utf-8").rstrip("\n") + "\n\n")
    print(f"\nDONE -> {final}  ({final.stat().st_size//1024} KB)")
    print(f"(per-batch parts kept in {parts}/ for resume; delete when satisfied)")


if __name__ == "__main__":
    main()
