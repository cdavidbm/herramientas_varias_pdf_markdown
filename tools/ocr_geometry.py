#!/usr/bin/env python3
"""ocr_geometry.py — separa CUERPO / NOTAS AL PIE / running-head y reconstruye
PÁRRAFOS usando la GEOMETRÍA de la TSV de tesseract (posición + tamaño de fuente).

EL PROBLEMA que resuelve
------------------------
El texto plano del OCR PIERDE la geometría de la página. En un escaneo con notas a
pie, tesseract entonces **intercala las notas con el cuerpo** (la nota cae a media
frase) y **pierde los párrafos** de la prosa. Comparar texto contra texto no lo
arregla: la información está en DÓNDE y de QUÉ TAMAÑO está cada palabra.

La TSV de tesseract (`--psm 6 -c tessedit_create_tsv=1`) da la caja de cada palabra
(left, top, width, height). Con eso se recupera, por página:

  · running-head : la 1ª línea de arriba con patrón «nº TÍTULO» / «TÍTULO nº».
  · NOTAS al pie : el bloque final tras el mayor HUECO vertical del 40% inferior.
                   Es la señal ROBUSTA — siempre hay un espacio (+ filete) entre el
                   cuerpo y las notas, aunque su fuente NO sea claramente menor
                   (medido en Theophilus: en varias páginas la nota era ~0.9×cuerpo
                   y el umbral de tamaño solo, la dejaba escapar al cuerpo). Fallback
                   si no hay hueco claro: fuente < 0.82×la del cuerpo.
  · PÁRRAFOS     : una línea cuyo margen izquierdo va claramente a la derecha de la
                   MEDIANA de los márgenes = sangría de primera línea = párrafo
                   nuevo. La MEDIANA (no el mínimo) es clave: los marcadores de nota
                   volados «§ ¥ *» cuelgan a la izquierda y, con `min`, hacían que
                   TODAS las líneas parecieran sangradas.

Cómo obtener la TSV:
    ocr_incremental.py libro.pdf --engine tesseract --tsv-out libro.tsv --psm 6
(una TSV por página, separadas por form-feed `\f`, igual que `--sidecar-out`).

Uso como LIBRERÍA (para el converter específico de un libro):
    from ocr_geometry import split_page   # -> (running_head|None, body_lines, notes)
    #   body_lines = [(es_sangria: bool, texto)]   notes = [texto]
Uso como CLI (vuelca el cuerpo reflotado + `## Notes` de un tramo de páginas):
    python3 ocr_geometry.py libro.tsv --pages 24-71            # prosa (párrafos)
    python3 ocr_geometry.py libro.tsv --pages 72-145 --join    # verso (un bloque)

Límite honesto: separa LAYOUT, no arregla el reconocimiento de caracteres. Una
página con OCR malo en el borde sigue saliendo con garble; el PDF buscable manda.
Los títulos de capítulo y la estructura (prosa vs verso) los pone el converter del
libro; esta herramienta da el cuerpo limpio y las notas aparte.
"""
from __future__ import annotations
import argparse, re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forja_common import load_dict  # noqa: E402

RH_TOP = re.compile(r"^\s*(\d{1,3}\s+[A-Z]|[A-Z][A-Z ]{6,}.*\d{1,3}\s*$|[ivxlIVXL]{1,5}\s*$)")
LEAD_MARK = re.compile(r"^\s*[|§¥®°†‡◊]+\s*")            # filete/marcador volado al inicio
NOTE_MARK = re.compile(r"^\s*(['\"*®°◊†‡~]|\d{1,3}[ .)])")


def parse_lines(tsv_text: str):
    """[(y, altura_mediana, left, texto_ordenado_x)] por línea, de arriba a abajo."""
    lines: dict = {}
    for ln in tsv_text.split("\n"):
        f = ln.split("\t")
        if len(f) < 12 or f[0] != "5" or f[11].strip() == "":
            continue
        try:
            left, top, h = int(f[6]), int(f[7]), int(f[9])
        except ValueError:
            continue
        lines.setdefault((f[2], f[3], f[4]), []).append((left, top, h, f[11]))
    out = []
    for ws in lines.values():
        ws.sort()
        out.append((min(w[1] for w in ws), statistics.median(w[2] for w in ws),
                    ws[0][0], " ".join(w[3] for w in ws)))
    out.sort()
    return out


def split_page(tsv_text: str):
    """Devuelve (running_head|None, [(es_sangria, texto)], [texto_nota])."""
    lines = parse_lines(tsv_text)
    if not lines:
        return None, [], []
    body_h = statistics.median(h for _, h, _, _ in lines)
    rh = None
    if RH_TOP.match(lines[0][3]) and lines[0][0] < lines[-1][0] * 0.12:
        rh = lines[0][3]; lines = lines[1:]
    if len(lines) < 3:
        return rh, [(False, l[3]) for l in lines], []
    ytop, ybot = lines[0][0], lines[-1][0]
    span = max(ybot - ytop, 1)
    ys = [l[0] for l in lines]
    gaps = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    med_gap = gaps[len(gaps) // 2] if gaps else 60
    start = None; best = 0
    for i in range(len(lines) - 1):
        if lines[i][0] > ytop + span * 0.40:
            g = ys[i + 1] - ys[i]
            if g > best:
                best = g; cand = i + 1
    if best > med_gap * 1.7:
        start = cand
    else:
        for i, (y, h, lft, t) in enumerate(lines):
            if y > ytop + span * 0.5 and h < body_h * 0.82:
                start = i; break
    body_lines = lines[:start] if start is not None else lines
    note_lines = lines[start:] if start is not None else []
    lefts = sorted(l[2] for l in body_lines)
    base = lefts[len(lefts) // 2] if lefts else 0
    body = [((l[2] - base) > 25, l[3]) for l in body_lines]
    notes = [l[3] for l in note_lines]
    return rh, body, notes


def _dehyph(a: str, b: str, D: set) -> str:
    b = b.lstrip()
    if a.endswith("-"):
        stem = a[:-1]
        w1 = re.search(r"([A-Za-z]+)$", stem); w2 = re.match(r"([A-Za-z]+)", b)
        if w1 and w2:
            j = (w1.group(1) + w2.group(1)).lower()
            if j in D and not (w1.group(1).lower() in D and w2.group(1).lower() in D):
                return stem + b
        return stem + b
    return a + " " + b if a else b


def reflow(body_lines, D=None, join=False):
    """Une las líneas de cuerpo. `join=True` → un solo bloque (para texto en verso,
    que se parte luego con verse_paragraphs). `join=False` (prosa) → un párrafo por
    sangría. De-guiona los cortes de línea usando el diccionario."""
    D = load_dict() if D is None else D
    paras, buf = [], ""
    for indent, line in body_lines:
        s = LEAD_MARK.sub("", line).strip()
        if not s:
            continue
        if not join and indent and buf:
            paras.append(buf); buf = s
        else:
            buf = _dehyph(buf, s, D)
    if buf:
        paras.append(buf)
    return paras


def join_notes(note_lines, D=None):
    """Une notas envueltas: una nota abre con marcador; las de continuación se pegan.
    Descarta filetes/basura corta."""
    D = load_dict() if D is None else D
    out = []
    for l in note_lines:
        s = l.strip()
        if len(s) <= 4 or not re.search(r"[a-z]{3,}", s):
            continue
        if NOTE_MARK.match(s) or not out:
            out.append(s)
        else:
            out[-1] = _dehyph(out[-1], s, D)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv", type=Path, help="TSV por página (\\f-separada) de ocr_incremental --tsv-out")
    ap.add_argument("--pages", help="rango 1-based inclusive, p. ej. 24-71 (def: todo)")
    ap.add_argument("--join", action="store_true", help="cuerpo como UN bloque (texto en verso)")
    ap.add_argument("--no-notes", action="store_true", help="no emitir la sección ## Notes")
    a = ap.parse_args()
    pages = a.tsv.read_text(encoding="utf-8").split("\f")
    lo, hi = (1, len(pages))
    if a.pages:
        lo, hi = (int(x) for x in a.pages.split("-"))
    D = load_dict()
    body_all, notes_all = [], []
    for i in range(lo - 1, min(hi, len(pages))):
        _, body, notes = split_page(pages[i])
        body_all += body
        notes_all += notes
    for para in reflow(body_all, D, join=a.join):
        print(para); print()
    if notes_all and not a.no_notes:
        print("## Notes\n")
        for k, n in enumerate(join_notes(notes_all, D), 1):
            print(f"{k}. {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
