#!/usr/bin/env python3
"""
imprime_sin_anclar.py — evita que el PDF se coma las notas que no tienen llamada.

EL DEFECTO, medido: `md_to_pdf` (vía pandoc) solo imprime una nota si existe la LLAMADA
`[^etiqueta]` en el cuerpo. Una definición huérfana de llamada se descarta EN SILENCIO.
En este libro el aparato se reconstruyó contando marcadores en un escaneo, y solo se ancló
donde coincidían dos señales independientes: 502 notas ancladas frente a 1.493 sin anclar.
Resultado: el PDF salió sin 1.463 notas. Ni el log de lualatex ni el balance refs↔defs lo
delatan —el markdown está completo, es la maquetación la que las tira—.

LA SOLUCIÓN: las definiciones sin llamada se convierten en TEXTO CORRIENTE al final de su
archivo, bajo un epígrafe propio, conservando su número. Así se imprimen todas y el lector
las tiene a mano, sin fingir un anclaje que no está verificado —que es lo que el usuario
pidió: anclar solo donde la imagen muestre el volado—.

Las notas SÍ ancladas se dejan intactas como `[^etiqueta]`, para que sigan saliendo al pie
de su página.

Dry-run por defecto.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

DEF = re.compile(r"^\[\^([\d-]+)\]: (.*)$", re.M)
EPIGRAFE = "## Notas del aparato sin llamada localizada"


def procesa(txt: str) -> tuple[str, int, int]:
    refs = set(re.findall(r"\[\^([\d-]+)\](?!:)", txt))
    defs = DEF.findall(txt)
    if not defs:
        return txt, 0, 0
    ancladas = [(l, c) for l, c in defs if l in refs]
    sueltas = [(l, c) for l, c in defs if l not in refs]
    if not sueltas:
        return txt, len(ancladas), 0

    # quitar del texto TODAS las definiciones y volver a poner solo las ancladas
    cuerpo = DEF.sub("", txt).rstrip()
    partes = [cuerpo]
    if ancladas:
        partes.append("\n\n" + "\n\n".join(f"[^{l}]: {c}" for l, c in ancladas))
    partes.append("\n\n" + EPIGRAFE + "\n\n" +
                  "\n\n".join(f"**{l.split('-')[-1]}.** {c}" for l, c in sueltas))
    return "".join(partes).rstrip() + "\n", len(ancladas), len(sueltas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ta = ts = 0
    for f in sorted(a.dir.glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        if EPIGRAFE in txt:
            print(f"  {f.name[:44]:<44} ya procesado")
            continue
        nuevo, ancl, suelt = procesa(txt)
        if not suelt:
            continue
        print(f"  {f.name[:44]:<44} ancladas {ancl:>4} · a imprimir aparte {suelt:>4}")
        ta += ancl
        ts += suelt
        if a.apply:
            f.write_text(nuevo, encoding="utf-8")
    print(f"\nancladas (siguen al pie) {ta} · rescatadas para que se impriman {ts}"
          f"{'' if a.apply else '   (dry-run: usa --apply)'}")


if __name__ == "__main__":
    main()
