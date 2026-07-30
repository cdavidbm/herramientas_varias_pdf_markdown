#!/usr/bin/env python3
"""
quita_titulillos_fundidos.py — borra los titulillos de página que el OCR PEGÓ al cuerpo.

El bisturí quita el titulillo por GEOMETRÍA, pero en las páginas donde el OCR lo fundió
con la primera línea del texto ya no hay geometría que valga: sobrevive impreso a media
página, en versales y cortando la frase. En el markdown pasa desapercibido.

Aquí el titulillo tiene una forma constante y muy reconocible:

    *§§7.1-36:* MARRIAGE *¢” RELATIONSHIPS* 229 of the seventh [would do so]…
    └──────────── prefijo: § + TÍTULO EN VERSALES + Nº DE PÁGINA ────────────┘└ cuerpo

El ancla NO es el título (el OCR lo escribe distinto cada vez: `¢”`, `¢»`, `€”` por «&»;
`S§7.`, `$9§7.`, `§.§70.` por «§§7.»). Las constantes son tres, y se exigen las TRES:

  1. el prefijo contiene una racha de 4+ VERSALES seguidas;
  2. termina en un NÚMERO DE PÁGINA de 2-3 cifras seguido del cuerpo en minúscula;
  3. el prefijo NO contiene ninguna palabra en minúscula de 3+ letras.

La (3) es la guarda que impide comerse prosa real: muchos libros llevan versales legítimas
dentro del cuerpo (rótulos, portadillas), pero no van seguidas de un número de página con
la frase reanudándose en minúscula.

Y `--encabezados` borra los titulillos que el conversor llegó a PROMOVER a encabezado
(«# §A: INTRODUCTORY MATTERS 57»): se reconocen porque terminan en un número de página
suelto. Solo se borran si el archivo tiene OTRO encabezado con el mismo texto sin el
número — es decir, si son un duplicado y no se pierde ninguna sección.

Dry-run por defecto. Sirve igual para `en/` y `es/`.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# prefijo = arranque + … + VERSALES + … + nº de página, y luego el cuerpo en minúscula
FUNDIDO = re.compile(
    r"^(?P<pre>[^a-z\n]{0,90}?[A-Z]{4,}[^a-z\n]{0,60}?\s(?P<pag>\d{2,3})\s+)(?=[a-z\[(])")
MINUSCULA = re.compile(r"[a-záéíóúñ]{3,}")
ENC_PAG = re.compile(r"^(#{1,6}\s+)(?P<txt>.*?)\s+(?P<pag>\d{2,3})\s*$")


def llano(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def quita_cuerpo(txt: str) -> tuple[str, list[str]]:
    fuera, lineas = [], txt.split("\n")
    for i, l in enumerate(lineas):
        if l.startswith("#"):
            continue
        m = FUNDIDO.match(l)
        if not m:
            continue
        pre = m.group("pre")
        if MINUSCULA.search(pre):       # guarda: el prefijo no puede llevar prosa
            continue
        lineas[i] = l[m.end():]
        fuera.append(pre.strip()[:66])
    return "\n".join(lineas), fuera


def quita_encabezados(txt: str) -> tuple[str, list[str]]:
    lineas = txt.split("\n")
    titulos = {llano(ENC_PAG.match(l).group("txt")) if ENC_PAG.match(l) else llano(l[2:])
               for l in lineas if l.startswith("#")}
    fuera, salida = [], []
    for l in lineas:
        m = ENC_PAG.match(l)
        # se borra solo si el MISMO título existe ya sin el número: es un duplicado
        if m and llano(m.group("txt")) in titulos and any(
                o.startswith("#") and llano(o[2:]) == llano(m.group("txt")) for o in lineas):
            fuera.append(l[:66])
            continue
        salida.append(l)
    return "\n".join(salida), fuera


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", type=Path, nargs="+")
    ap.add_argument("--encabezados", action="store_true",
                    help="borra además los titulillos PROMOVIDOS a encabezado")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    tc = te = 0
    for d in a.dirs:
        for f in sorted(d.glob("*.md")):
            txt = f.read_text(encoding="utf-8")
            txt, cuerpo = quita_cuerpo(txt)
            enc: list[str] = []
            if a.encabezados:
                txt, enc = quita_encabezados(txt)
            if not (cuerpo or enc):
                continue
            print(f"\n── {d}/{f.name}")
            for x in cuerpo:
                print(f"     cuerpo:     «{x}»")
            for x in enc:
                print(f"     ENCABEZADO: «{x}»")
            tc += len(cuerpo)
            te += len(enc)
            if a.apply:
                f.write_text(txt, encoding="utf-8")
    print(f"\n{'='*70}\ntitulillos en cuerpo {tc} · encabezados falsos {te}"
          f"{'' if a.apply else '   (dry-run: usa --apply)'}")


if __name__ == "__main__":
    main()
