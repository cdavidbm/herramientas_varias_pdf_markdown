#!/usr/bin/env python3
"""
embed_figures_from_captions.py — Añade las FIGURAS (cartas, diagramas) a un libro ya
traducido cuyo markdown conserva las LEYENDAS de figura como texto pero NO las imágenes.

Caso: los tomos ya convertidos/traducidos (p. ej. Natividades Persas) tienen en su markdown
líneas «**Figura N: …**» pero sin la carta. Este script las recorta del PDF fuente (escaneo
OCR-eado con leyendas «Figure N: …») y las incrusta ANTES de su leyenda española, dejando
la leyenda traducida a la vista (mejor que rotular en el idioma origen).

Flujo (todo automático, reanudable):
  1. Lee `MD-DIR/*.md` y localiza las leyendas «Figura N: …» → punto de inserción de cada figura.
  2. En el PDF fuente busca «Figure N» con `pdftotext -layout`; descarta las páginas-ÍNDICE
     (las que listan >3 figuras) y toma la página del CUERPO de cada figura.
  3. Rasteriza esas páginas y pide a agy/Gemini la BBOX del dibujo (sin leyenda), en lotes
     con reintento (agy trunca lotes densos).
  4. Recorta SOLO el dibujo: usa la bbox de agy y RECORTA la leyenda por su posición real
     (`pdftotext -bbox` localiza «Figure N» y se corta justo encima) → `FIGURES-DIR/figNNN.png`.
  5. Inserta `![Figura N](RELPATH/figNNN.png)` antes de la línea «…Figura N: …» en el markdown.

Uso:
  python3 embed_figures_from_captions.py FUENTE.pdf --md-dir es --figures-dir figuras \
      --fig-relpath ../figuras --workdir _work [--parallel 4] [--dpi 300]

Requisitos: agy en PATH (o --agy-bin), poppler (pdftoppm/pdftotext), crop_figure.py en tools/.
"""
from __future__ import annotations

import argparse
import glob
import html
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CAP_RE = re.compile(r'(?m)^\s*\*{0,2}Figura (\d+):?\s*(.*?)\**\s*$')
BBOX_LINE = re.compile(r'\bpg(\d+)[^|]*\|\s*bbox=([0-9.]+(?:,[0-9.]+){3})')

BBOX_PROMPT = (
    "Each image is a scanned book page containing ONE astrological figure/chart/diagram/table "
    "(a circle/wheel, geometric diagram, or boxed table). For EACH file output exactly ONE line:\n"
    "<filename> | bbox=x0,y0,x1,y1\n"
    "where x0,y0,x1,y1 are FRACTIONS 0..1 of the page giving the bounding box of ONLY THE FIGURE "
    "ITSELF (the drawing/chart/table) — do NOT include the 'Figure N: ...' caption line, and do "
    "NOT include body paragraph text. Box tightly around the drawing but never cut any part of it. "
    "Output nothing else."
)


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def parse_captions(md_dir: Path) -> dict[int, tuple[str, str]]:
    caps = {}
    for f in sorted(glob.glob(str(md_dir / "*.md"))):
        for m in CAP_RE.finditer(Path(f).read_text(encoding="utf-8")):
            caps[int(m.group(1))] = (os.path.basename(f), m.group(2).strip())
    return caps


def figure_pages(src: Path) -> dict[int, int]:
    txt = sh(["pdftotext", "-layout", str(src), "-"]).stdout.split("\f")
    occ, dpp = {}, {}
    for pg, body in enumerate(txt, 1):
        nums = set(int(m.group(1)) for m in re.finditer(r"Figure (\d+)", body))
        dpp[pg] = len(nums)
        for n in nums:
            occ.setdefault(n, []).append(pg)
    listpages = {pg for pg, c in dpp.items() if c > 3}          # páginas-índice
    return {n: ([p for p in pgs if p not in listpages] or pgs)[0] for n, pgs in occ.items()}


def render(src: Path, pages: list[int], pdir: Path, dpi: int):
    pdir.mkdir(parents=True, exist_ok=True)
    for p in pages:
        out = pdir / f"pg{p:04d}.png"
        if out.exists():
            continue
        pref = str(pdir / f"_t{p:04d}")
        sh(["pdftoppm", "-r", "150", "-png", "-f", str(p), "-l", str(p), str(src), pref])
        c = sorted(pdir.glob(f"_t{p:04d}*.png"))
        if c:
            c[0].rename(out)


def agy_bboxes(pages: list[int], pdir: Path, model: str, agy_bin: str, parallel: int) -> dict[int, str]:
    files = [f"pg{p:04d}.png" for p in pages]
    batches = [files[i:i + 4] for i in range(0, len(files), 4)]
    result: dict[int, str] = {}

    def run(bat):
        prompt = f"{BBOX_PROMPT}\nFiles (in ./): {', '.join(bat)}"
        out = sh([agy_bin, "-p", prompt, "--model", model, "--add-dir", str(pdir),
                  "--dangerously-skip-permissions"]).stdout
        return out

    for _ in range(3):                                          # reintenta lotes incompletos
        pending = [b for b in batches if not all(int(re.search(r"pg(\d+)", f).group(1)) in result for f in b)]
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            for out in ex.map(run, pending):
                for m in BBOX_LINE.finditer(out):
                    result[int(m.group(1))] = m.group(2)
    return result


def caption_top(src: Path, page: int, n: int) -> float | None:
    xml = sh(["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(src), "-"]).stdout
    ph = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', xml)
    if not ph:
        return None
    H = float(ph.group(2))
    words = re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">([^<]*)</word>', xml)
    for i, (x0, y0, w) in enumerate(words):
        if html.unescape(w).strip() == "Figure" and i + 1 < len(words):
            if html.unescape(words[i + 1][2]).strip().rstrip(":") == str(n):
                return float(y0) / H
    return None


def embed(md_dir: Path, mdfile: str, n: int, relpath: str, name: str) -> bool:
    p = md_dir / mdfile
    t = p.read_text(encoding="utf-8")
    pat = re.compile(rf'(?m)^(\s*\*{{0,2}}Figura {n}:[^\n]*)$')
    t2, k = pat.subn(f"![Figura {n}]({relpath}/{name})\n\n" + r"\1", t, count=1)
    if k:
        p.write_text(t2, encoding="utf-8")
    return bool(k)


def main():
    ap = argparse.ArgumentParser(description="Incrusta figuras recortadas del PDF fuente junto a sus leyendas.")
    ap.add_argument("src", type=Path)
    ap.add_argument("--md-dir", type=Path, required=True)
    ap.add_argument("--figures-dir", type=Path, required=True)
    ap.add_argument("--fig-relpath", default="../figuras")
    ap.add_argument("--workdir", type=Path, default=Path("_work"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--model", default="Gemini 3.1 Pro (High)")
    ap.add_argument("--agy-bin", default=os.path.expanduser("~/.local/bin/agy"))
    args = ap.parse_args()

    caps = parse_captions(args.md_dir)
    pages_of = figure_pages(args.src)
    figs = {n: (pages_of[n], caps[n]) for n in sorted(caps) if n in pages_of}
    missing_pg = [n for n in caps if n not in pages_of]
    print(f"[1/4] leyendas={len(caps)}  localizadas en fuente={len(figs)}"
          + (f"  ⚠ sin página: {missing_pg}" if missing_pg else ""))

    pdir = args.workdir / "pages"
    upages = sorted(set(p for p, _ in figs.values()))
    print(f"[2/4] render {len(upages)} páginas @150dpi …")
    render(args.src, upages, pdir, 150)

    print(f"[3/4] agy bboxes ({args.parallel} en paralelo) …")
    bboxes = agy_bboxes(upages, pdir, args.model, args.agy_bin, args.parallel)
    nob = [p for p in upages if p not in bboxes]
    if nob:
        print(f"    ⚠ sin bbox tras reintentos: páginas {nob}")

    print(f"[4/4] recorte (leyenda recortada por OCR) + embebido …")
    args.figures_dir.mkdir(parents=True, exist_ok=True)
    done, prob = 0, []
    for n in sorted(figs):
        page, (mdfile, _cap) = figs[n]
        if page not in bboxes:
            prob.append(f"{n}:nobbox"); continue
        x0, y0, x1, y1 = (float(v) for v in bboxes[page].split(","))
        ct = caption_top(args.src, page, n)
        if ct and ct - 0.008 > y0:
            y1 = min(y1, ct - 0.008)
        name = f"fig{n:03d}.png"
        r = sh(["python3", str(TOOLS / "crop_figure.py"), str(args.src), "--page", str(page),
                "--bbox", f"{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}", "--pad", "0.008",
                "--dpi", str(args.dpi), "--out", str(args.figures_dir / name)])
        if r.returncode != 0:
            prob.append(f"{n}:crop"); continue
        if embed(args.md_dir, mdfile, n, args.fig_relpath, name):
            done += 1
        else:
            prob.append(f"{n}:noembed")
    print(f"\n== figuras incrustadas: {done}/{len(caps)} ==" + (f"  problemas: {prob}" if prob else ""))


if __name__ == "__main__":
    main()
