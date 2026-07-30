#!/usr/bin/env python3
"""
limpia_dudas.py — resuelve las marcas `[?: …]` que el traductor dejó como deuda declarada.

El prompt le prohíbe inventar: ante un resto de OCR ilegible debe marcarlo en vez de
rellenarlo. Eso es lo correcto, pero deja 236 marcas que NO pueden ir al PDF. No todas
son iguales, y tratarlas igual sería el error:

  [RUIDO]  La marca es la COLA de una llamada de nota que el escaneo se comió
           («dignidad, [?: 7*]», «oposición [?: opposition®]»). No aporta nada: el
           aparato de notas va aparte y la puntuación real ya está fuera del corchete.
           → se borra.

  [REF]    La marca es una REFERENCIA CRUZADA a *ITA* y es lo ÚNICO que hay
           («Véase `[?: VIL6.]`»). Borrarla dejaría un «Véase» huérfano: hay que
           REPARARLA. El destrozo es la confusión clásica del OCR entre `I` y
           `J [ L T H U 1`, así que se normaliza por regla y se VERIFICA que el
           resultado sea un numeral romano válido de *ITA* (Libros I-VIII).
           Contrastado contra la imagen impresa en III.14, II.9-10 y IV.3.

  [MIRAR]  Todo lo demás. NO se toca: se lista para revisarlo a mano contra la imagen.
           Es preferible una marca fea a un borrado que se lleve contenido real.

Dry-run por defecto.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARCA = re.compile(r"\s*`?\[\?:\s*([^\]]*)\]`?")
VEASE = re.compile(r"(?:V|v)éase\s*`?$")
# un «núcleo» alfabético de 3+ letras significa que la marca dice algo, no es solo ruido
NUCLEO = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}")
# Una marca es PORTANTE (falta contenido de verdad) si lo que va DELANTE queda abierto:
# una palabra función o un delimitador sin cerrar. «Hermann de Carintia asoció a [?: …]»
# perdió «Trismegisto»; «*Recti* [?: Reefi]» no perdió nada, la lectura buena ya está.
FUNCION = re.compile(
    r"(?:^|[\s(\[«\"])(?:de|del|la|el|los|las|lo|un|una|unos|unas|a|al|y|e|o|u|con|"
    r"por|para|en|que|como|sobre|ni|sin|desde|entre|según|hasta)\s*$", re.I)
ABIERTO = re.compile(r"[(\[«\"“,;:]\s*$")
# referencia cruzada a *ITA* aunque no vaya tras «Véase» (listas: «Véase I.3, I.4, VII4»)
PINTA_REF = re.compile(r"^[IVXJLTHU\[\]|1]{1,4}\.?[\d.\-–f]*\.?$")
ROMANOS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII"}
# el OCR lee estos caracteres donde el impreso pone una «I»
COMO_I = str.maketrans({c: "I" for c in "J[]|1lLTHU"})


def repara_ref(bruto: str) -> str | None:
    """«VIL6.» → «VII.6». Devuelve None si no se reconstruye con certeza."""
    s = bruto.strip().rstrip(".,;")
    m = re.match(r"^([A-Za-z\[\]|]+)\.?(.*)$", s)
    if not m:                                   # empieza por cifra: «111.14», «11.6»
        m = re.match(r"^([\d]+)\.(.*)$", s)
        if not m:
            return None
    cabeza, resto = m.group(1), m.group(2)
    romano = cabeza.translate(COMO_I).upper()
    # «VUI»→«VIII»: la U es una I mal leída, pero translate ya lo hizo; validamos
    if romano not in ROMANOS:
        return None
    resto = resto.strip().rstrip(".")
    if not resto:
        return None                             # «See II» a secas: ambiguo, no lo invento
    if not re.fullmatch(r"[\d.\-–]+", resto):
        return None
    return f"{romano}.{resto}"


def procesa(txt: str) -> tuple[str, list[str], list[str], list[str]]:
    borradas, reparadas, mirar = [], [], []
    out, pos = [], 0
    for m in MARCA.finditer(txt):
        out.append(txt[pos:m.start()])
        pos = m.end()
        contenido = m.group(1).strip()
        antes = txt[max(0, m.start() - 40):m.start()].rstrip()
        # 1. referencia cruzada a *ITA* (tras «Véase» o dentro de una lista de refs)
        if VEASE.search(antes) or PINTA_REF.match(contenido):
            ref = repara_ref(contenido)
            if ref:
                out.append(f" {ref}" if VEASE.search(antes) else f" {ref}")
                reparadas.append(f"{contenido!r} → {ref}")
            else:
                out.append(m.group(0))
                mirar.append(f"REF sin resolver: …{antes[-34:]!r} → {contenido!r}")
            continue
        # 2. ruido puro: la cola de una llamada de nota que el escaneo se comió
        if not NUCLEO.search(contenido):
            borradas.append(contenido)
            continue
        # 3. ¿queda abierto lo de delante? entonces la marca ES el contenido que falta
        if FUNCION.search(antes) or ABIERTO.search(antes):
            out.append(m.group(0))
            mirar.append(f"FALTA CONTENIDO: …{antes[-34:]!r} → {contenido!r}")
            continue
        # 4. la lectura buena ya está delante: la marca solo repite el original corrupto
        borradas.append(contenido)
    out.append(txt[pos:])
    return "".join(out), borradas, reparadas, mirar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path, nargs="?", default=Path("es"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    tb = tr = 0
    pendientes: list[tuple[str, str]] = []
    for f in sorted(a.dir.glob("*.md")):
        nuevo, borradas, reparadas, mirar = procesa(f.read_text(encoding="utf-8"))
        if not (borradas or reparadas or mirar):
            continue
        print(f"\n── {f.name}: {len(borradas)} ruido · {len(reparadas)} refs · {len(mirar)} a mirar")
        for r in reparadas:
            print(f"     ✎ {r}")
        tb += len(borradas)
        tr += len(reparadas)
        pendientes += [(f.name, x) for x in mirar]
        if a.apply:
            f.write_text(nuevo, encoding="utf-8")
    print(f"\n{'='*70}\nruido borrado {tb} · referencias reparadas {tr} · "
          f"PENDIENTES DE MIRAR {len(pendientes)}")
    for nom, x in pendientes:
        print(f"   {nom[:24]:<24} {x}")
    if not a.apply:
        print("\n(dry-run: usa --apply)")


if __name__ == "__main__":
    main()
