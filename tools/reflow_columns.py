#!/usr/bin/env python3
"""
reflow_columns.py — Recompone la prosa que un bisturí partió al mal-leer una maqueta
a DOS COLUMNAS paralelas (original|traducción, o texto|variante), dejando el cuerpo
cortado en fragmentos de una línea sembrados de comentarios `<!-- col N pág M -->`.

El problema
-----------
Muchas ediciones académicas ponen pasajes en una columna estrecha (una variante de
manuscrito, el original enfrentado a la traducción). Un extractor que no separa bien
las columnas toma cada LÍNEA FÍSICA de la columna estrecha como un PÁRRAFO y marca los
saltos con `<!-- col N pág M -->`. Resultado: «ejemplo: como si el / Ascendente fuera /
Virgo, / y la pregunta / …» — una palabra o dos por renglón, ilegible.

La idea clave
-------------
El texto principal (párrafos largos) SÍ cierra frase con punto, así que hace de
BARRERA natural; solo los fragmentos cortados quedan «abiertos». Se recose:
  1. Se borran los comentarios `<!-- col … -->`.
  2. Se fusiona cada párrafo que NO cierra frase (`. : ! ? …`) con el siguiente; y
     también si el siguiente ARRANCA en minúscula (continuación evidente, incluso tras
     una coma inicial: «…ejemplo:» → «, como si…»).

Es determinista y de bajo riesgo: preserva el texto (verificado token a token en
Sahl & Māshā'allāh, donde recompuso las variantes de la ed. de 1493 y la lista de
términos de la Introducción, ambas a 2 columnas). NO separa dos columnas de CONTENIDO
distinto entremezcladas a nivel de línea (eso pide leer la fuente y reconstruir a mano);
sí arregla el caso —el más común— en que una columna estrecha se cortó en renglones.

Guardas (para no fundir lo que no toca)
---------------------------------------
No fusiona encabezados `#`, figuras `![`, definiciones de nota `[^N]:`, tablas `|`,
citas `>`, bloques de código, ni las LÍNEAS-ETIQUETA totalmente en negrita (leyendas
«**Figura N: …**», rótulos): esas cierran o abren bloque y hacen de barrera. Al coser
se normalizan los artefactos que deja la unión (« ,» → «,», «: ,» → «:», espacios
dobles). Idempotente. Simulacro por defecto.

Uso
---
    python3 reflow_columns.py cap.md              # simulacro
    python3 reflow_columns.py es/*.md --apply
"""
import argparse
import re
from pathlib import Path

# comentario de columna del extractor: «<!-- col 1 pág 107 -->», «<!-- col 2 page 5 -->»…
COL = re.compile(r"^\s*<!--\s*col\b[^>]*-->\s*$", re.I)
# no fundir: encabezados, figuras, definiciones de nota, tablas, citas, código, y las
# líneas-etiqueta enteras en negrita (leyendas/rótulos, que abren o cierran bloque)
NOFUNDIR = re.compile(r"^\s*(#|!\[|\[\^\d+\]:|>|\||```|\*\*[^\n]+\*\*\s*$)")
# nota/comilla/cierre que puede colgar tras la puntuación final
COLA = re.compile(r'(\[\^\d+\]|["”»)\]]|\*+)+$')
TERMINAL = tuple(".:!?…")


def termina_frase(par: str) -> bool:
    """¿El párrafo cierra una frase? (ignora notas/comillas/cierres colgantes al final)."""
    s = par.rstrip()
    prev = None
    while s and s != prev:
        prev = s
        s = COLA.sub("", s).rstrip()
    return bool(s) and s[-1] in TERMINAL


def reflow(txt: str) -> tuple[str, int]:
    """Devuelve (texto recompuesto, nº de fragmentos recosidos)."""
    lineas = [l for l in txt.split("\n") if not COL.match(l)]     # quitar comentarios col
    parras = re.split(r"\n[ \t]*\n", "\n".join(lineas))
    out, fusiones, i = [], 0, 0
    while i < len(parras):
        cur = parras[i].strip("\n")
        if not cur.strip():
            i += 1
            continue
        while i + 1 < len(parras) and cur.strip() and not NOFUNDIR.match(cur):
            sig = parras[i + 1].strip("\n")
            if not sig.strip() or NOFUNDIR.match(sig):
                break
            # fundir si el actual no cierra frase, o si el siguiente arranca en minúscula
            # (continuación evidente); el texto principal empieza en mayúscula → barrera.
            continua = re.sub(r"^[\s,;:.]+", "", sig)[:1].islower()
            if termina_frase(cur) and not continua:
                break
            cur = cur.rstrip() + " " + sig.lstrip()
            fusiones += 1
            i += 1
        out.append(cur)
        i += 1
    limpio = []
    for p in out:                                # limpiar los artefactos de la costura
        p = re.sub(r" +([,;.])", r"\1", p)       # « ,» → «,»
        p = re.sub(r":\s*,", ":", p)             # «: ,» → «:»
        p = re.sub(r"[ \t]{2,}", " ", p)
        limpio.append(p)
    return "\n\n".join(limpio) + "\n", fusiones


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="markdown a recomponer")
    ap.add_argument("--apply", action="store_true", help="escribir (por defecto: simulacro)")
    a = ap.parse_args()
    tot = 0
    for f in a.files:
        txt = f.read_text(encoding="utf-8")
        nuevo, n = reflow(txt)
        if nuevo == txt:
            continue
        tot += n
        print(f"{f.name:48s} fragmentos recosidos={n:4d}  "
              f"comentarios col quitados={txt.count('<!-- col')}")
        if a.apply:
            f.write_text(nuevo, encoding="utf-8")
    print(f"\n{'APLICADO' if a.apply else 'SIMULACRO'}: {tot} fragmentos recosidos")


if __name__ == "__main__":
    main()
