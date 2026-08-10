#!/usr/bin/env python3
"""aparato_volados_aplanados.py — enlaza un aparato cuyos VOLADOS están APLANADOS.

Por qué existe
--------------
Algunos PDF digitales pasan por un reprocesador (Nitro Pro, ciertos «optimizadores»)
que **aplana los superíndices**: el dígito de la llamada queda con la MISMA línea
base y prácticamente el mismo cuerpo que el texto que lo rodea. Con eso se cae la
técnica habitual —detectar el volado por su geometría— y es fácil concluir que el
aparato no se puede enlazar con ese PDF.

Casi siempre se puede, porque **el dígito sigue estando en el texto**, pegado sin
espacio al carácter anterior. Lo que hace falta es separarlo de las OTRAS cifras del
documento, y ahí es donde fallan los intentos ingenuos.

Medido en al-Tilimsānī, *The Divine Names* (LAL/NYU Press, trad. Casewit): un primer
intento ancló 13 de 544 y dio el caso por imposible; con las guardas de abajo salen
**590 de 591** en el cuerpo y **42 de 43** en la introducción.

Las cuatro guardas, todas medidas
---------------------------------
1. **Enmascarar las OTRAS series de números antes de nada.** Este libro numera los
   párrafos al margen (`**131.3**`, convención de la Library of Arabic Literature) y
   esa segunda serie se entrelaza con la de las notas. Era la causa REAL de que la
   cadena se rompiera pronto, no «las muchas cifras de la prosa». Se enmascara con
   relleno de la MISMA longitud, para que los offsets sigan valiendo sobre el texto
   real y se pueda sustituir sin recalcular nada.
2. **La cadena tiene que poder SALTAR huecos.** Exigir que avance de uno en uno la
   rompe en el primer número ausente y tira en cascada todo lo que viene detrás
   (medido aquí y, antes, en Lehrich: en ambos se partía justo tras la nota 25).
   Nunca retrocede, eso sí: un número que va hacia atrás es una cifra del cuerpo.
3. **El regex NO puede ser ASCII.** En un libro de transliteración árabe la llamada
   va pegada a `ī`, `ā`, `ḥ`… y `[a-zA-Z]` la deja fuera (`al-Baghawī26`). Se exige
   «pegado a cualquier carácter que no sea espacio ni dígito».
4. **El asterisco cuenta como carácter anterior.** Excluirlo para no chocar con las
   negritas se lleva por delante las llamadas tras un cierre de cursiva (`.”*397`).
   Como la guarda 1 ya enmascaró los marcadores, se puede admitir sin riesgo.

Y dos cosas que NO hace, a propósito
------------------------------------
- **No inventa el anclaje que falta.** Si el volado no está en la página, la nota se
  reporta y se deja sin anclar: un anclaje falso mueve la nota a otra frase y **al
  leer no se nota**. Úsese `--imprime-sin-anclar` para que al menos se imprima
  (recuérdese que **pandoc descarta en silencio la definición sin llamada**).
- **No reparte a ciegas.** Las definiciones van al archivo donde vive SU llamada,
  que es lo que pandoc exige, y se comprueba el balance archivo a archivo.

Antes de usarlo: comprueba que el aparato esté COMPLETO
-------------------------------------------------------
El mismo libro traía el bloque de notas truncado sin que nada lo delatara: 1..544
seguidas y sin huecos, mientras el PDF llegaba a la 591 — las 47 restantes estaban
glutinadas dentro de la «entrada 544», que tenía 375 palabras frente a una mediana
de 5. `--auditar` avisa de eso: compara el número más alto del aparato con el más
alto que aparece en el cuerpo, y señala las entradas anormalmente largas.

Uso
---
    # 1) auditar antes de tocar nada
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md --auditar

    # 2) ensayo y aplicación
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md \\
        --cuerpo 07-49 --enmascarar '\\*\\*\\d+\\.\\d+\\*\\*'
    python3 aparato_volados_aplanados.py ./markdown --notas 50_Notes.md \\
        --cuerpo 07-49 --apply --imprime-sin-anclar
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEF = re.compile(r"^\*\*(\d+)\.\*\*\s*(.+)$", re.M)
# pegado a cualquier carácter que no sea espacio ni dígito (guardas 3 y 4),
# y que no forme parte de una cifra mayor ni de una referencia «17:110» / «1–3»
LLAMADA = re.compile(r"(?<=[^\s\d])(\d{1,3})(?![\d.:–-])")


def leer_aparato(p: Path) -> dict[int, str]:
    return {int(m.group(1)): m.group(2).strip() for m in DEF.finditer(p.read_text(encoding="utf-8"))}


def enmascarar(s: str, patrones: list[str]) -> str:
    """Sustituye por relleno de IGUAL longitud: los offsets siguen valiendo."""
    for pat in patrones:
        s = re.sub(pat, lambda m: "§" * len(m.group(0)), s)
    return s


def cadena(ficheros: list[Path], patrones: list[str], tope: int, salto: int):
    """Cadena ascendente global que puede saltar huecos pero nunca retrocede."""
    ult, out = 0, []
    for p in ficheros:
        mask = enmascarar(p.read_text(encoding="utf-8"), patrones)
        for m in LLAMADA.finditer(mask):
            v = int(m.group(1))
            if v > tope:
                continue
            if v > ult and v - ult <= salto:
                out.append((p, m.start(), m.end(), v))
                ult = v
    return out


def rango(spec: str):
    a, _, b = spec.partition("-")
    return int(a), int(b or a)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md_dir", type=Path)
    ap.add_argument("--notas", required=True, help="archivo del aparato, dentro de md_dir")
    ap.add_argument("--cuerpo", default="", help="rango de prefijos numéricos, p. ej. 07-49")
    ap.add_argument("--enmascarar", action="append", default=[r"\*\*\d+\.\d+\*\*"],
                    help="regex de OTRAS series de números (repetible). Por defecto, la "
                         "numeración de párrafo al margen estilo LAL.")
    ap.add_argument("--etiqueta", default="", help="prefijo de etiqueta, p. ej. «i» → [^i7]")
    ap.add_argument("--salto", type=int, default=6, help="hueco máximo tolerado en la cadena")
    ap.add_argument("--auditar", action="store_true", help="solo comprobar el aparato y salir")
    ap.add_argument("--imprime-sin-anclar", action="store_true",
                    help="las notas cuyo volado no esté en el texto se imprimen como texto")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    notas = leer_aparato(a.md_dir / a.notas)
    if not notas:
        print(f"error: no se reconocen entradas «**N.**» en {a.notas}")
        return 2
    tope = max(notas)

    fich = sorted(p for p in a.md_dir.glob("*.md") if p.name != a.notas)
    if a.cuerpo:
        lo, hi = rango(a.cuerpo)
        fich = [p for p in fich if p.name[:2].isdigit() and lo <= int(p.name[:2]) <= hi]

    # ---- auditoría del aparato (hazla SIEMPRE antes de enlazar) ----
    largos = sorted(((len(t.split()), n) for n, t in notas.items()), reverse=True)[:3]
    med = sorted(len(t.split()) for t in notas.values())[len(notas) // 2]
    crudo = "\n".join(enmascarar(p.read_text(encoding="utf-8"), a.enmascarar) for p in fich)
    tope_cuerpo = max((int(m.group(1)) for m in LLAMADA.finditer(crudo)
                       if int(m.group(1)) < tope * 3), default=0)
    print(f"aparato: {len(notas)} entradas, 1..{tope} | mediana {med} palabras")
    print(f"  las 3 más largas: {[(n, w) for w, n in largos]}")
    huecos = [n for n in range(1, tope + 1) if n not in notas]
    print(f"  huecos: {huecos or 'ninguno'}")
    if tope_cuerpo > tope:
        print(f"  ⚠ EL CUERPO LLEGA A {tope_cuerpo} Y EL APARATO A {tope}: faltan "
              f"{tope_cuerpo - tope} notas. Mira si la última entrada se tragó el resto "
              f"(su longitud frente a la mediana). NO enlaces hasta arreglarlo.")
    if a.auditar:
        return 1 if tope_cuerpo > tope else 0

    hits = cadena(fich, a.enmascarar, tope, a.salto)
    puestas = {v for *_, v in hits}
    sin = [n for n in sorted(notas) if n not in puestas]
    print(f"\nancladas {len(hits)} de {len(notas)}  ({100*len(hits)/len(notas):.1f}%)")
    print(f"sin anclar (el volado no está en el texto): {sin or 'ninguna'}")

    porfich: dict[Path, list] = {}
    for p, ini, fin, v in hits:
        porfich.setdefault(p, []).append((ini, fin, v))
    for p in fich:
        if p in porfich:
            print(f"  {p.name[:52]:<52} {len(porfich[p]):4d}")

    if not a.apply:
        print("\n(ensayo: nada escrito. Añade --apply)")
        return 0

    E = a.etiqueta
    for p in fich:
        hs = porfich.get(p)
        if not hs:
            continue
        s = p.read_text(encoding="utf-8")
        for ini, fin, v in reversed(hs):           # de atrás adelante: offsets válidos
            assert s[ini:fin] == str(v), f"{p.name}: descuadre en la nota {v}"
            s = s[:ini] + f"[^{E}{v}]" + s[fin:]
        s = s.rstrip() + "\n\n## Notes\n\n" + "\n\n".join(
            f"[^{E}{v}]: {notas[v]}" for _, _, v in hs) + "\n"
        p.write_text(s, encoding="utf-8")

    if sin and a.imprime_sin_anclar:
        ultimo = max(porfich, key=lambda q: fich.index(q))
        s = ultimo.read_text(encoding="utf-8").rstrip() + "\n\n## Nota sin llamada\n\n"
        for n in sin:
            s += (f"> **{n}.** {notas[n]}\n>\n> *(El volado de esta nota no aparece en el "
                  f"texto. Se imprime aquí, en su lugar de la secuencia, en vez de anclarla "
                  f"a ojo: pandoc descarta en silencio la definición sin llamada.)*\n\n")
        ultimo.write_text(s, encoding="utf-8")
        print(f"\n{len(sin)} nota(s) sin llamada impresas en {ultimo.name}")

    mal = 0
    for p in fich:
        s = p.read_text(encoding="utf-8")
        d = set(re.findall(r"^\[\^([^\]]+)\]:", s, re.M))
        r = set(re.findall(r"\[\^([^\]]+)\]", re.sub(r"^\[\^[^\]]+\]:.*$", "", s, flags=re.M)))
        if r != d:
            print(f"  ⚠ {p.name}: refs {len(r)} defs {len(d)} → {sorted(r ^ d)}")
            mal += 1
    print(f"\nbalance por archivo: {'todo cuadra' if not mal else f'{mal} con desbalance'}")
    print(f"El aparato central ({a.notas}) queda REDUNDANTE: sácalo de la carpeta o se "
          f"imprimirá dos veces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
