#!/usr/bin/env python3
"""detecta_defectos.py — busca los defectos que NINGÚN control obvio ve.

CLI sobre `forja.aparato` y `forja.estructura`. La lógica y sus guardas viven en
los módulos, con sus tests en `tests/`.

Qué busca, y por qué hace falta una herramienta aparte
-------------------------------------------------------
Todos los defectos de aquí comparten una firma incómoda: **el balance de notas
cuadra, el ratio de palabras sonríe y el markdown se lee sin sobresaltos.** Son
justamente los que sobreviven a la auditoría, a la traducción y al PDF.

* **Llamadas en hueco numérico** — un `[^N]` plantado donde iba una cifra, porque
  el margen recortado se llevó el volado real y el colocador ancló sobre el
  primer número que encontró. Medido en *The Search of the Heart*: 50 casos.
* **Definiciones truncadas** — una nota que acaba en «…p.»: el partidor cortó en
  una referencia de página, y ese mismo fallo se llevó las siguientes. Medido en
  Ficino: 53 notas donde el impreso lleva 90.
* **Títulos en minúscula y huérfanos bajo un encabezado** — las dos mitades de un
  título centrado en dos renglones. La versión cara de este defecto deja el
  encabezado mil palabras más abajo y el tramo intermedio sin traducir.
* **Subtítulos fundidos al párrafo** — apartados marcados con cursiva que el
  bisturí no vio. Medido en Lehrich: 86 por idioma; el libro queda sin estructura
  interna y el índice solo lista capítulos.
* **Ratio POR CAPÍTULO** (con `--es`) — porque el global esconde la laguna: en
  Ficino era 0,98 con un capítulo al 0,62.

No corrige nada. Un anclaje o un encabezado puestos a ciegas es como se pierde
texto; esto señala dónde mirar.

Uso
---
    python3 detecta_defectos.py ./markdown
    python3 detecta_defectos.py ./en --es ./es        # además, ratio por capítulo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forja.aparato import definiciones_truncadas, llamadas_en_hueco_numerico  # noqa: E402
from forja.estructura import (  # noqa: E402
    capitulos_con_deficit, encabezados_partidos, notas_duplicadas_en_cuerpo,
    subtitulos_fundidos, titulos_en_minuscula,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md_dir", type=Path, help="carpeta de markdown (el original)")
    ap.add_argument("--es", type=Path, help="carpeta traducida, para el ratio por capítulo")
    ap.add_argument("--max", type=int, default=8, help="cuántos casos mostrar por tipo")
    a = ap.parse_args()

    ficheros = sorted(a.md_dir.glob("*.md"))
    if not ficheros:
        print(f"error: no hay .md en {a.md_dir}")
        return 2

    total = 0
    for etiqueta, fn, formato in [
        ("LLAMADAS EN HUECO NUMÉRICO (el balance cuadra igual)",
         llamadas_en_hueco_numerico, lambda x: f"[^{x[0]}] {x[1]}\n        …{x[2]}…"),
        ("DEFINICIONES TRUNCADAS (el partidor cortó en una referencia)",
         definiciones_truncadas, lambda x: f"[^{x}]"),
        ("TÍTULOS EN MINÚSCULA (mitad de un título partido)",
         titulos_en_minuscula, lambda x: x),
        ("HUÉRFANOS BAJO UN ENCABEZADO (la otra mitad)",
         encabezados_partidos, lambda x: f"{x[0]}  ⟵  «{x[1]}»"),
        ("SUBTÍTULOS FUNDIDOS AL PÁRRAFO (el libro pierde su estructura)",
         subtitulos_fundidos, lambda x: f"*{x[0]}*  ⟵  «{x[1]}…»"),
    ]:
        hallazgos = []
        for f in ficheros:
            for h in fn(f.read_text(encoding="utf-8")):
                hallazgos.append((f.name, h))
        if not hallazgos:
            continue
        total += len(hallazgos)
        print(f"\n── {etiqueta}: {len(hallazgos)}")
        for nombre, h in hallazgos[:a.max]:
            print(f"   {nombre[:34]:<34} {formato(h)}")
        if len(hallazgos) > a.max:
            print(f"   … y {len(hallazgos) - a.max} más")

    dup = []
    for f in ficheros:
        t = f.read_text(encoding="utf-8")
        cuerpo, _, aparato = t.partition("\n## Notas\n")
        if not aparato:
            cuerpo, _, aparato = t.partition("\n## Notes\n")
        if aparato:
            n = notas_duplicadas_en_cuerpo(cuerpo, aparato)
            if n > 2:
                dup.append((f.name, n))
    if dup:
        total += len(dup)
        print("\n── NOTAS DUPLICADAS EN EL CUERPO (el balance cuadra igual): "
              f"{len(dup)} archivo(s)")
        for nombre, n in dup[:a.max]:
            print(f"   {nombre[:40]:<40} {n} definición(es) también en la prosa")

    if a.es:
        pares = []
        for f in ficheros:
            g = a.es / f.name
            if g.is_file():
                pares.append((f.name, f.read_text(encoding="utf-8"),
                              g.read_text(encoding="utf-8")))
        flojos = capitulos_con_deficit(pares)
        if pares:
            glob = sum(len(c.split()) for _, _, c in pares) / \
                max(1, sum(len(o.split()) for _, o, _ in pares))
            print(f"\n── RATIO POR CAPÍTULO  (global {glob:.3f}, que es el que engaña)")
            for nombre, r in flojos:
                print(f"   {nombre[:34]:<34} {r}")
            if not flojos:
                print("   ningún capítulo por debajo del umbral")
            total += len(flojos)

    print(f"\n{total} señal(es). No se ha modificado nada: son sitios donde MIRAR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
