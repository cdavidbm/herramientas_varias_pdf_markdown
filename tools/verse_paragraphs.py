#!/usr/bin/env python3
"""verse_paragraphs.py — reformatea texto VERSIFICADO a UN PÁRRAFO POR VERSO.

Muchos clásicos (Abū Maʿshar, Valens, Doroteo, Hefestión) numeran sus frases o
«versos». Tras convertir un escaneo, el cuerpo suele quedar como UN párrafo gigante
por capítulo con los números de verso inline (« … condition. 4 And indeed… 5 But…»).
Eso rompe la legibilidad (líneas de decenas de miles de caracteres) y, si además un
título absorbió el cuerpo, hace que TODO renderice como un encabezado en negrita.

Esta herramienta parte cada verso en su propio párrafo con el número en **negrita**.

SEÑAL de verso (fiable en prosa inglesa): un número 1..MAX **solo** (rodeado de
espacios) SEGUIDO de palabra capitalizada / apertura (`A-Z ( [ "`). El filtro de
mayúscula descarta las CANTIDADES (« … 30 signs», «assign 1 to …» → van en
minúscula) y permite el RESET del contador al empezar cada capítulo (2, 3, 4…),
imprescindible cuando algunos encabezados se perdieron en el OCR.

NO toca: encabezados (`#`), tablas (`|`), bloques de código (```), citas (`>`),
definiciones de nota (`[^`) ni líneas que ya empiezan en negrita. Es idempotente:
un `**4**` ya puesto no se vuelve a tocar.

Límite honesto: en textos donde una cantidad va seguida de Mayúscula (un nombre
propio, un inicio de cláusula) puede colar algún falso verso → por eso va en
**DRY-RUN por defecto**: revisa el recuento antes de `--apply`.

Uso:
  python3 verse_paragraphs.py libro/*.md              # dry-run: cuenta versos
  python3 verse_paragraphs.py libro/*.md --apply      # escribe
  python3 verse_paragraphs.py cap.md --max 250 --apply
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

PROTECT = ("#", "|", "```", ">", "[^", "- ", "* ")
NUM = re.compile(r"(\d{1,3})$")


def split_verses(text: str, vmax: int = 199) -> str:
    """Devuelve el texto con cada verso en su propio párrafo (número en negrita)."""
    toks = text.split()
    paras: list[list[str]] = [[]]
    for i, tok in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        m = re.fullmatch(r"\d{1,3}", tok)
        if m and 1 <= int(tok) <= vmax and re.match(r"[A-Z(\[“]", nxt):
            if paras[-1]:                 # abre un párrafo nuevo por verso
                paras.append([])
            paras[-1].append(f"**{int(tok)}**")
        else:
            paras[-1].append(tok)
    return "\n\n".join(" ".join(p) for p in paras if p)


def process(text: str, vmax: int) -> tuple[str, int]:
    """Aplica el split a las líneas de cuerpo; cuenta versos marcados."""
    out, verses = [], 0
    for ln in text.split("\n"):
        s = ln.lstrip()
        if not s or s.startswith(PROTECT) or s.startswith("**"):
            out.append(ln)
            continue
        new = split_verses(ln, vmax)
        verses += new.count("**") // 2
        out.append(new)
    return "\n".join(out), verses


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe los cambios (def: dry-run)")
    ap.add_argument("--max", type=int, default=199, help="número de verso máximo plausible (def 199)")
    args = ap.parse_args()
    total = 0
    for f in args.files:
        txt = f.read_text(encoding="utf-8")
        new, v = process(txt, args.max)
        total += v
        maxln_old = max((len(x) for x in txt.split("\n")), default=0)
        maxln_new = max((len(x) for x in new.split("\n")), default=0)
        if new != txt:
            print(f"{f.name}: {v} versos · línea+larga {maxln_old} → {maxln_new}")
            if args.apply:
                f.write_text(new, encoding="utf-8")
    print(f"\n{'APLICADO' if args.apply else 'DRY-RUN'}: {total} versos en {len(args.files)} archivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
