#!/usr/bin/env python3
"""cose_parrafos.py — une los párrafos que un bisturí PARTIÓ en el salto de página.

`pdf_rich_to_markdown.py` abre párrafo nuevo en cada cambio de página, así que un
párrafo que cruza de página sale roto A MEDIA FRASE:

    …subdividió el abanico de la cábala «aceptable» mucho más sutilmente. En numerosas

    ocasiones Idel ha argumentado, *contra* Scholem, que…

Se lee, pero no es markdown correcto: al maquetar salen dos párrafos con sangría
donde el libro tiene uno, y el corte cae a mitad de oración. Medido en Lehrich: 251.

**La señal es doble y hay que exigir las dos**: el párrafo anterior NO cierra frase
(ni punto, ni interrogación, ni comilla de cierre) y el siguiente ABRE EN MINÚSCULA.
Con una sola de las dos se cosen párrafos legítimos.

**Y nunca se cose alrededor de una CITA EN BLOQUE**: ahí la interrupción es del
original —la frase del autor entra en la cita y sale de ella—, y unirlas destruiría
la cita. Tampoco se tocan encabezados, tablas, imágenes ni definiciones de nota.

Uso:
    python3 cose_parrafos.py ./es/*.md            # dry-run, informa
    python3 cose_parrafos.py ./es/*.md --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Cierre de frase: puntuación final, admitiendo una llamada de nota o comillas detrás.
FIN = re.compile(r'[.!?:;»”\)\]…]\s*(?:\[\^[^\]]+\])?\s*$')
NO_PROSA = ("#", "|", "!", ">", "[^", "---", "*   ", "- ")


def es_prosa(p: str) -> bool:
    s = p.strip()
    return bool(s) and not s.startswith(NO_PROSA)


def cose(md: str) -> tuple[str, int]:
    partes = md.split("\n\n")
    out: list[str] = []
    n = 0
    for p in partes:
        s = p.strip()
        if (out and es_prosa(out[-1]) and es_prosa(s)
                and not FIN.search(out[-1].rstrip())
                and s[:1].islower()):
            # continuación: se une con un espacio, sin tocar nada más
            out[-1] = out[-1].rstrip() + " " + s
            n += 1
            continue
        out.append(p if not s else s)
    return "\n\n".join(x for x in out if x.strip() or True), n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    a = ap.parse_args()
    tot = toc = 0
    for f in a.files:
        if not f.is_file():
            print(f"warning: no existe {f}", file=sys.stderr)
            continue
        orig = f.read_text(encoding="utf-8")
        nuevo, n = cose(orig)
        nuevo = re.sub(r"\n{3,}", "\n\n", nuevo).rstrip() + "\n"
        if n:
            tot += n
            toc += 1
            if a.apply:
                f.write_text(nuevo, encoding="utf-8")
            print(f"  {f.name}: {n} párrafo(s) cosido(s)")
    print(f"\n{'APLICADO' if a.apply else 'DRY-RUN'} — {tot} uniones en {toc} archivo(s)")
    if not a.apply and tot:
        print("Revisa la lista y vuelve a lanzarlo con --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
