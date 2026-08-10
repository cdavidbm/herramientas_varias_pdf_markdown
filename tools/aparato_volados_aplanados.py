#!/usr/bin/env python3
"""aparato_volados_aplanados.py — enlaza un aparato cuyos VOLADOS están APLANADOS.

CLI sobre `forja.aparato`. La lógica y sus guardas viven en el módulo, con su
test en `tests/test_aparato.py`; aquí solo está el trato con la línea de órdenes
y con los archivos.

Cuándo se usa
-------------
Algunos PDF digitales pasan por un reprocesador (Nitro Pro, ciertos
«optimizadores») que **aplana los superíndices**: el dígito de la llamada queda
con la MISMA línea base y casi el mismo cuerpo que el texto que lo rodea. Se cae
la detección por geometría y es fácil concluir que el aparato no se puede
enlazar con ese PDF. Casi siempre se puede: el dígito sigue en el texto, pegado
sin espacio al carácter anterior.

Medido en al-Tilimsānī, *The Divine Names* (LAL/NYU, trad. Casewit): un primer
intento ancló 13 de 544 y dio el caso por imposible; con las guardas del módulo
salen **590 de 591** en el cuerpo y **42 de 43** en la introducción, con el
cuerpo conservando exactamente las mismas 90.454 palabras.

AUDITA ANTES DE ENLAZAR (`--auditar`)
-------------------------------------
El mismo libro traía el aparato TRUNCADO y parecía íntegro: 1..544 seguidas y
sin huecos, mientras el PDF llegaba a la 591 —las 47 restantes glutinadas dentro
de la «entrada 544», de 375 palabras frente a una mediana de 5—. No lo ve el
rango, ni el balance, ni el recuento de palabras.

Uso
---
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md --auditar
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md --cuerpo 07-49
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md --cuerpo 07-49 \\
        --apply --imprime-sin-anclar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forja.aparato import (  # noqa: E402
    SERIE_PARRAFO, Aparato, anclar, auditar, candidatos_pegados,
)


def rango(spec: str) -> tuple[int, int]:
    a, _, b = spec.partition("-")
    return int(a), int(b or a)


def main() -> int:
    ap_ = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("md_dir", type=Path)
    ap_.add_argument("--notas", required=True, help="archivo del aparato, dentro de md_dir")
    ap_.add_argument("--cuerpo", default="", help="rango de prefijos, p. ej. 07-49")
    ap_.add_argument("--enmascarar", action="append", default=[SERIE_PARRAFO],
                     help="regex de OTRAS series de números (repetible). Por defecto, la "
                          "numeración de párrafo al margen estilo LAL.")
    ap_.add_argument("--etiqueta", default="", help="prefijo de etiqueta, p. ej. «i» → [^i7]")
    ap_.add_argument("--salto", type=int, default=6, help="hueco máximo tolerado en la cadena")
    ap_.add_argument("--auditar", action="store_true", help="solo comprobar el aparato y salir")
    ap_.add_argument("--imprime-sin-anclar", action="store_true",
                     help="las notas cuyo volado no esté en el texto se imprimen como texto")
    ap_.add_argument("--apply", action="store_true")
    a = ap_.parse_args()

    aparato = Aparato.de_entradas((a.md_dir / a.notas).read_text(encoding="utf-8"))
    if not aparato.notas:
        print(f"error: no se reconocen entradas «**N.**» en {a.notas}")
        return 2

    fich = sorted(p for p in a.md_dir.glob("*.md") if p.name != a.notas)
    if a.cuerpo:
        lo, hi = rango(a.cuerpo)
        fich = [p for p in fich if p.name[:2].isdigit() and lo <= int(p.name[:2]) <= hi]

    tope_cuerpo = 0
    for p in fich:
        vals = [v for _a, _b, v in candidatos_pegados(p.read_text(encoding="utf-8"),
                                                      a.enmascarar)]
        tope_cuerpo = max([tope_cuerpo] + [v for v in vals if v <= aparato.tope * 3])

    print(f"aparato: {len(aparato.notas)} entradas, 1..{aparato.tope} | "
          f"huecos: {aparato.huecos() or 'ninguno'}")
    for aviso in aparato.sospecha_truncamiento(tope_cuerpo):
        print(f"  ⚠ {aviso}")
        print("    NO enlaces hasta arreglarlo: las notas que falten se perderían calladas.")
    if a.auditar:
        return 1 if aparato.sospecha_truncamiento(tope_cuerpo) else 0

    # La cadena es del LIBRO, no de cada archivo: se arrastra de uno a otro.
    ult, plan = 0, {}
    for p in fich:
        texto, puestas = anclar(p.read_text(encoding="utf-8"), aparato.tope,
                                etiqueta=a.etiqueta, salto=a.salto, desde=ult + 1,
                                patrones=a.enmascarar)
        if puestas:
            ult = max(puestas)
            plan[p] = (texto, puestas)

    total = sorted(v for _t, vs in plan.values() for v in vs)
    sin = [n for n in sorted(aparato.notas) if n not in set(total)]
    print(f"\nancladas {len(total)} de {len(aparato.notas)} "
          f"({100 * len(total) / len(aparato.notas):.1f}%)")
    print(f"sin anclar (el volado no está en el texto): {sin or 'ninguna'}")
    for p, (_t, vs) in plan.items():
        print(f"  {p.name[:52]:<52} {len(vs):4d}")

    if not a.apply:
        print("\n(ensayo: nada escrito. Añade --apply)")
        return 0

    E = a.etiqueta
    for p, (texto, vs) in plan.items():
        texto = texto.rstrip() + "\n\n## Notes\n\n" + "\n\n".join(
            f"[^{E}{v}]: {aparato.notas[v]}" for v in vs) + "\n"
        p.write_text(texto, encoding="utf-8")

    if sin and a.imprime_sin_anclar:
        # Cada una va con SUS VECINAS de numeración, no todas al final del libro:
        # una nota del §131 impresa tras el colofón no se encuentra nunca.
        destino: dict[Path, list[int]] = {}
        for n in sin:
            vecina = min(plan, key=lambda q: min(abs(v - n) for v in plan[q][1]))
            destino.setdefault(vecina, []).append(n)
        for p, nums in destino.items():
            s = p.read_text(encoding="utf-8").rstrip() + "\n\n## Nota sin llamada\n\n"
            for n in nums:
                s += (f"> **{n}.** {aparato.notas[n]}\n>\n> *(El volado de esta nota no "
                      f"aparece en el texto. Se imprime aquí, en su lugar de la secuencia, "
                      f"en vez de anclarla a ojo: pandoc descarta en silencio la definición "
                      f"sin llamada.)*\n\n")
            p.write_text(s, encoding="utf-8")
            print(f"\nnota(s) sin llamada {nums} impresas en {p.name}")

    mal = 0
    for p in plan:
        for problema in auditar(p.read_text(encoding="utf-8")):
            print(f"  ⚠ {p.name}: {problema}")
            mal += 1
    print(f"\nauditoría: {'todo cuadra' if not mal else f'{mal} problema(s)'}")
    print(f"El aparato central ({a.notas}) queda REDUNDANTE: sácalo de la carpeta o se "
          f"imprimirá dos veces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
