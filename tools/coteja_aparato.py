#!/usr/bin/env python3
"""
coteja_aparato.py — contrasta el aparato de notas de un .md contra el PIE IMPRESO del PDF.

El aparato de este libro se reconstruyó CONTANDO marcadores (los volados son diminutos y
tesseract no los lee), y esa cadena puede DESFASARSE sin que nada lo delate: el balance
refs↔defs cuadra igual, el ratio no se entera y el markdown se lee perfectamente. Medido
en la Introducción del traductor: la nota que el impreso numera 18 estaba como [^19], y
dos notas se habían fundido en una perdiendo texto por el camino.

La única fuente que zanja esto es la IMAGEN. Aquí se OCR-ea el PIE de cada página (la
franja inferior, donde vive el aparato), se leen los números REALES —que en el pie sí van
en cuerpo normal y se reconocen bien, al contrario que los volados— y se compara cada
definición con la del markdown por el ARRANQUE DEL TEXTO, no por el número.

Así el desfase se ve como un patrón: si la def. N del markdown coincide con la N-1 del
impreso durante un tramo, ahí está el corrimiento.

Salida: informe. NO modifica nada — corregir un aparato a ciegas es cómo se pierde texto.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import tempfile
from pathlib import Path

DEF_MD = re.compile(r"^\[\^([\d-]+)\]:\s*(.*)$", re.M)
# en el pie impreso la nota abre con su número en cuerpo normal a principio de renglón
DEF_PIE = re.compile(r"^\s*(\d{1,3})\s+([A-Z(\[*«\"'].{12,})$")


def ocr_pie(pdf: Path, pagina: int, franja: float) -> list[str]:
    """OCR de la franja INFERIOR de la página (donde está el aparato)."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdfimages", "-png", "-f", str(pagina), "-l", str(pagina),
                        str(pdf), f"{d}/p"], check=True, capture_output=True)
        img = next(iter(sorted(Path(d).glob("p*.png"))), None)
        if img is None:
            return []
        from PIL import Image
        im = Image.open(img)
        w, h = im.size
        im.crop((0, int(h * (1 - franja)), w, h)).save(f"{d}/pie.png")
        r = subprocess.run(["tesseract", f"{d}/pie.png", "-", "--psm", "6"],
                           capture_output=True, text=True,
                           env={"OMP_THREAD_LIMIT": "1", "PATH": "/usr/bin:/bin"})
    return r.stdout.split("\n")


def norma(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())[:26]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("md", type=Path)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--paginas", required=True, help="rango PDF, p.ej. 28-67")
    ap.add_argument("--franja", type=float, default=0.30,
                    help="fracción inferior de la página que se OCR-ea (def. 0.30)")
    a = ap.parse_args()
    ini, fin = (int(x) for x in a.paginas.split("-"))

    impreso: list[tuple[int, str, int]] = []          # (nº impreso, texto, página)
    for p in range(ini, fin + 1):
        for l in ocr_pie(a.pdf, p, a.franja):
            if m := DEF_PIE.match(l):
                impreso.append((int(m.group(1)), m.group(2).strip(), p))
    md = [(n, t) for n, t in DEF_MD.findall(a.md.read_text(encoding="utf-8"))]

    print(f"pie impreso: {len(impreso)} definiciones · markdown: {len(md)}\n")
    print(f"{'impreso':>8} {'markdown':>9}  {'pág':>4}  arranque del texto")
    print("-" * 78)
    desfases: dict[int, int] = {}
    for n_imp, texto, pag in impreso:
        clave = norma(texto)
        cand = [(i, mn) for i, (mn, mt) in enumerate(md)
                if difflib.SequenceMatcher(None, clave, norma(mt)).ratio() > 0.72]
        if not cand:
            print(f"{n_imp:>8} {'—':>9}  {pag:>4}  ¿FALTA? «{texto[:44]}»")
            continue
        mn = cand[0][1]
        try:
            d = int(mn) - n_imp
        except ValueError:
            d = 0
        desfases[d] = desfases.get(d, 0) + 1
        marca = "" if d == 0 else f"   ← desfase {d:+d}"
        print(f"{n_imp:>8} {mn:>9}  {pag:>4}  «{texto[:40]}»{marca}")
    print("\nresumen de desfases:", ", ".join(f"{k:+d}: {v}" for k, v in sorted(desfases.items())))


if __name__ == "__main__":
    main()
