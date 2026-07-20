#!/usr/bin/env python3
"""
crop_figure.py — Recorta una FIGURA (carta astral, diagrama, rueda zodiacal…)
de una página de PDF y la guarda como PNG para embeberla en el markdown.

Pensado para libros donde ciertas figuras NO se pueden reproducir fielmente como
texto/tabla (glifos ♄♃ en una rueda, diagramas geométricos) y hay que conservarlas
como imagen dentro del corpus markdown, la traducción y el PDF final. El flujo
típico: durante el reconocimiento visual, un agente (agy/Gemini o Claude) devuelve
la caja de la figura en coordenadas FRACCIONARIAS 0..1 de la página
(`bbox=x0,y0,x1,y1`, esquina sup-izq → inf-der); este script rasteriza esa página
a alta resolución y recorta esa caja.

Coordenadas fraccionarias (no píxeles) para que sean robustas al dpi de render:
el agente ve la página a un tamaño y el recorte se hace a otro mayor sin recalcular.

Backend: `pdftoppm` (poppler) para rasterizar + PIL para recortar. Sin libs PDF.

Uso:
  python3 crop_figure.py libro.pdf --page 79 --bbox 0.15,0.28,0.85,0.70 --out figuras/fig26.png
  python3 crop_figure.py libro.pdf --page 79 --bbox 0.15,0.28,0.85,0.70 --dpi 300 --pad 0.01
  # --page es 1-based sobre el PDF. --dpi por defecto 300. --pad añade margen (fracción).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Falta Pillow. Instala con: pip install Pillow  (o usa el venv forja-ocr).")


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in s.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox debe ser x0,y0,x1,y1 (4 fracciones)")
    try:
        x0, y0, x1, y1 = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("bbox: valores no numéricos")
    if not all(0.0 <= v <= 1.0 for v in (x0, y0, x1, y1)):
        raise argparse.ArgumentTypeError("bbox: las fracciones deben ir en 0..1")
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError("bbox: x1>x0 y y1>y0 requeridos")
    return x0, y0, x1, y1


def render_page(pdf: Path, page: int, dpi: int, tmpdir: str) -> Path:
    """Rasteriza UNA página del PDF (1-based) a PNG con pdftoppm."""
    prefix = str(Path(tmpdir) / "pg")
    cmd = ["pdftoppm", "-r", str(dpi), "-png", "-f", str(page), "-l", str(page), str(pdf), prefix]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"pdftoppm falló: {res.stderr.strip()}")
    pngs = sorted(Path(tmpdir).glob("pg*.png"))
    if not pngs:
        sys.exit("pdftoppm no produjo PNG (¿número de página fuera de rango?)")
    return pngs[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Recorta una figura de una página de PDF a PNG.")
    ap.add_argument("pdf", type=Path, help="PDF fuente")
    ap.add_argument("--page", type=int, required=True, help="página 1-based del PDF")
    ap.add_argument("--bbox", type=parse_bbox, required=True,
                    help="x0,y0,x1,y1 en fracciones 0..1 (sup-izq → inf-der)")
    ap.add_argument("--out", type=Path, required=True, help="PNG de salida")
    ap.add_argument("--dpi", type=int, default=300, help="resolución de render (def. 300)")
    ap.add_argument("--pad", type=float, default=0.0,
                    help="margen extra alrededor de la caja, en fracción de página (def. 0)")
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"No existe el PDF: {args.pdf}")

    x0, y0, x1, y1 = args.bbox
    if args.pad:
        x0 = max(0.0, x0 - args.pad); y0 = max(0.0, y0 - args.pad)
        x1 = min(1.0, x1 + args.pad); y1 = min(1.0, y1 + args.pad)

    with tempfile.TemporaryDirectory() as td:
        png = render_page(args.pdf, args.page, args.dpi, td)
        with Image.open(png) as im:
            W, H = im.size
            box = (round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H))
            crop = im.crop(box)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            crop.save(args.out)
    cw, ch = args.out.stat().st_size, None
    with Image.open(args.out) as im:
        ch = im.size
    print(f"OK  {args.out}  ({ch[0]}x{ch[1]} px, {cw} bytes)  desde pág {args.page} @ {args.dpi}dpi "
          f"bbox=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f})")


if __name__ == "__main__":
    main()
