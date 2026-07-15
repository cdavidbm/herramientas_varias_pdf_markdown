#!/usr/bin/env python3
"""
ocr_incremental.py — Run ocrmypdf over a PDF in page BATCHES, saving each batch to
disk so a long OCR job can survive an interruption (closed laptop, Ctrl-C, crash)
and RESUME instead of starting from zero.

Why: `ocrmypdf` processes the whole document in a temp dir and only writes the
output PDF at the very end. On a 350-page 300-dpi scan that is 20-40 min (or hours
with preprocessing) with nothing usable on disk until the finish line — kill it and
all the work is lost. This wrapper slices the PDF into batches (qpdf), OCRs each
into `parts/part_NNNN.pdf` immediately, prints progress, and on a re-run SKIPS
batches whose part already exists. When all batches are done it merges them into
`<stem>_ocr.pdf`.

Because OCR is page-independent, batch boundaries never split content (unlike
Docling tables/footnotes) — batching here is purely for checkpointing, free of
seam artifacts.

Best models: if `~/.local/share/forja-tessdata` exists (from tools/ocr_setup.sh)
it is used automatically via TESSDATA_PREFIX, so you get tessdata_best without
extra flags. Override with --tessdata or the env var.

Modes (how to treat any existing OCR text layer):
  redo   (default) `--redo-ocr`   : strip existing OCR, re-OCR the images. Best for
                                    fixing a BAD text layer (e.g. Internet Archive)
                                    while keeping the original image untouched.
  force  `--force-ocr`            : rasterize every page and OCR. Use when the page
                                    mixes vector text/images or redo refuses; allows
                                    --deskew/--clean/--rotate (pass via --extra).
  skip   `--skip-text`            : only OCR pages with NO text layer (adds a layer
                                    to image-only scans; leaves born-digital text).

Usage:
  python3 ocr_incremental.py book.pdf                         # -> book_ocr.pdf (redo, eng)
  python3 ocr_incremental.py book.pdf --lang eng --batch 20
  python3 ocr_incremental.py scan.pdf --mode skip --lang spa+lat
  python3 ocr_incremental.py book.pdf                         # re-run = resume
  python3 ocr_incremental.py book.pdf --mode force --extra "--deskew --clean"

Requires: `ocrmypdf`, `qpdf`, `pdfinfo` (poppler) on PATH.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

MODE_FLAG = {"redo": "--redo-ocr", "force": "--force-ocr", "skip": "--skip-text"}


def sh(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def page_count(pdf):
    out = sh(["pdfinfo", str(pdf)]).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise SystemExit("could not read page count (pdfinfo failed)")


def tesseract_batch(pdf, a, b, side, tmp, dpi, lang, env):
    """Render pages a..b with pdftoppm and OCR each directly with tesseract.
    Writes the concatenated text (pages \\f-separated) to `side`. More accurate on
    italics than ocrmypdf's rasterization for some scans."""
    texts = []
    for p in range(a, b + 1):
        stem = tmp / f"pg_{p:04d}"
        r = sh(["pdftoppm", "-f", str(p), "-l", str(p), "-r", str(dpi), "-png",
                str(pdf), str(stem)])
        pngs = sorted(tmp.glob(f"pg_{p:04d}*.png"))
        if r.returncode != 0 or not pngs:
            raise RuntimeError(f"pdftoppm failed on page {p}: {r.stderr}")
        png = pngs[0]
        r = sh(["tesseract", str(png), "stdout", "-l", lang], env=env)
        if r.returncode != 0:
            png.unlink(missing_ok=True)
            raise RuntimeError(f"tesseract failed on page {p}: {r.stderr[-500:]}")
        texts.append(r.stdout)
        png.unlink(missing_ok=True)
    # Escritura ATÓMICA: si el proceso muere a mitad del write, un `side` truncado
    # existiría y el resume (side.exists() and st_size>0) lo daría por bueno,
    # perdiendo páginas. Escribir a .tmp y os.replace (rename atómico) lo evita.
    tmp_side = side.with_name(side.name + ".tmp")
    tmp_side.write_text("\f".join(texts), encoding="utf-8")
    os.replace(tmp_side, side)


def main():
    ap = argparse.ArgumentParser(description="ocrmypdf with per-batch checkpointing + resume.")
    ap.add_argument("pdf")
    ap.add_argument("--out", help="output PDF path (default <stem>_ocr.pdf next to input)")
    ap.add_argument("--lang", default="eng", help="tesseract language(s), e.g. eng / spa+lat+grc (default eng)")
    ap.add_argument("--batch", type=int, default=20, help="pages per batch (default 20)")
    ap.add_argument("--mode", choices=list(MODE_FLAG), default="redo",
                    help="how to treat existing OCR (default redo); see module docstring")
    ap.add_argument("--jobs", type=int, default=0, help="ocrmypdf --jobs within a batch (0=ocrmypdf default)")
    ap.add_argument("--optimize", type=int, default=0, help="ocrmypdf --optimize level 0-3 (default 0)")
    ap.add_argument("--tessdata", default=str(Path.home() / ".local/share/forja-tessdata"),
                    help="TESSDATA_PREFIX to use if it exists (default forja-tessdata / best models)")
    ap.add_argument("--extra", default="", help="extra args passed verbatim to ocrmypdf (quote them)")
    ap.add_argument("--sidecar-out", help="also write the plain OCR TEXT (all pages, form-feed separated) "
                    "to this path — resumable per batch. Use this when the searchable-PDF text layer is not "
                    "extractable by pdftotext (some recoded/LuraDocument scans embed OCR text without ToUnicode).")
    ap.add_argument("--engine", choices=["ocrmypdf", "tesseract"], default="ocrmypdf",
                    help="OCR engine. 'ocrmypdf' (default) builds a searchable PDF. 'tesseract' renders each "
                    "page with pdftoppm and runs tesseract DIRECTLY — noticeably more accurate on some scans "
                    "(ocrmypdf's own rasterization can misread italics, e.g. oikos→otkos), outputs TEXT only "
                    "(requires --sidecar-out), no PDF.")
    ap.add_argument("--dpi", type=int, default=300, help="render DPI for --engine tesseract (default 300)")
    args = ap.parse_args()
    if args.engine == "tesseract" and not args.sidecar_out:
        sys.exit("--engine tesseract outputs text only; pass --sidecar-out PATH")

    pdf = Path(args.pdf).resolve()
    if not pdf.is_file():
        sys.exit(f"no such PDF: {pdf}")
    out = Path(args.out).resolve() if args.out else pdf.with_name(pdf.stem + "_ocr.pdf")
    work = pdf.with_name(pdf.stem + "_ocrwork")
    parts = work / "parts"
    tmp = work / "_tmp"
    parts.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(exist_ok=True)

    # Use best models if available (ocrmypdf reads TESSDATA_PREFIX from env).
    env = dict(os.environ)
    td = Path(args.tessdata)
    if td.is_dir():
        env["TESSDATA_PREFIX"] = str(td)
        td_note = f"best models: {td}"
    else:
        td_note = "system tessdata (forja-tessdata not found; run tools/ocr_setup.sh for best models)"

    total = page_count(pdf)
    batches = [(a, min(a + args.batch - 1, total)) for a in range(1, total + 1, args.batch)]
    print(f"{pdf.name}: {total} pages -> {len(batches)} batch(es) of {args.batch} | "
          f"mode={args.mode} lang={args.lang}\n{td_note}")

    extra = shlex.split(args.extra)
    want_text = bool(args.sidecar_out)
    tess = args.engine == "tesseract"
    done = 0
    for k, (a, b) in enumerate(batches, 1):
        part = parts / f"part_{k:04d}.pdf"
        side = parts / f"part_{k:04d}.txt"
        # checkpoint: tesseract engine keys on the TEXT part; ocrmypdf on the PDF part
        if tess:
            resumed = side.exists() and side.stat().st_size > 0
        else:
            resumed = part.exists() and part.stat().st_size > 0 and (not want_text or side.exists())
        if resumed:
            print(f"  [{k}/{len(batches)}] pages {a}-{b}  ✓ resume (already done)")
            done += 1
            continue
        t0 = time.time()
        if tess:
            try:
                tesseract_batch(pdf, a, b, side, tmp, args.dpi, args.lang, env)
            except RuntimeError as e:
                side.unlink(missing_ok=True)
                sys.exit(f"tesseract engine failed on pages {a}-{b}:\n{e}")
        else:
            batch_pdf = tmp / f"batch_{k:04d}.pdf"
            r = sh(["qpdf", "--empty", "--pages", str(pdf), f"{a}-{b}", "--", str(batch_pdf)])
            if r.returncode != 0 or not batch_pdf.exists():
                sys.exit(f"qpdf failed on pages {a}-{b}:\n{r.stderr}")
            # Escritura ATÓMICA: ocrmypdf escribe directamente sobre el destino; si
            # muere a mitad, un `part`/`side` truncado existiría y el resume lo daría
            # por bueno (páginas perdidas). Escribir a .tmp y os.replace al terminar.
            part_tmp = part.with_name(part.name + ".tmp")
            side_tmp = side.with_name(side.name + ".tmp")
            cmd = ["ocrmypdf", MODE_FLAG[args.mode], "-l", args.lang]
            if args.jobs:
                cmd += ["--jobs", str(args.jobs)]
            if args.optimize:
                cmd += ["--optimize", str(args.optimize)]
            if want_text:
                cmd += ["--sidecar", str(side_tmp)]
            cmd += extra + [str(batch_pdf), str(part_tmp)]
            r = sh(cmd, env=env)
            # ocrmypdf exit 6 = "some pages already had text and were skipped" (skip mode) — not fatal.
            if r.returncode not in (0, 6) or not part_tmp.exists() or (want_text and not side_tmp.exists()):
                part_tmp.unlink(missing_ok=True)
                side_tmp.unlink(missing_ok=True)
                sys.exit(f"ocrmypdf failed on pages {a}-{b} (exit {r.returncode}):\n{r.stderr[-2000:]}")
            os.replace(part_tmp, part)
            if want_text:
                os.replace(side_tmp, side)
            batch_pdf.unlink(missing_ok=True)
        done += 1
        eta = (time.time() - t0) * (len(batches) - done)
        print(f"  [{k}/{len(batches)}] pages {a}-{b}  ✓ {time.time()-t0:.0f}s "
              f"(~{eta/60:.0f} min left)", flush=True)

    # merge all part PDFs (ocrmypdf engine only)
    if not tess:
        part_files = [str(parts / f"part_{k:04d}.pdf") for k in range(1, len(batches) + 1)]
        merge = ["qpdf", "--empty", "--pages"] + part_files + ["--", str(out)]
        r = sh(merge)
        if r.returncode != 0 or not out.exists():
            sys.exit(f"qpdf merge failed:\n{r.stderr}")
        print(f"\nDONE -> {out}  ({out.stat().st_size//1024} KB, {total} pages)")
    else:
        print(f"\nDONE (tesseract engine, text only, {total} pages)")

    # concatenate per-batch sidecar text (form-feed separated) when requested
    if want_text:
        side_out = Path(args.sidecar_out).resolve()
        with side_out.open("w", encoding="utf-8") as fh:
            for k in range(1, len(batches) + 1):
                t = (parts / f"part_{k:04d}.txt").read_text(encoding="utf-8", errors="replace")
                fh.write(t if t.endswith("\f") else t + "\f")
        print(f"TEXT -> {side_out}  ({side_out.stat().st_size//1024} KB, all pages, \\f-separated)")
    print(f"(batch parts kept in {parts}/ for resume; delete {work}/ when satisfied)")


if __name__ == "__main__":
    main()
