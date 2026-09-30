#!/usr/bin/env python3
"""book_invariants.py — compara dos versiones de un texto y avisa si una EDICIÓN DE ESTILO tocó lo intocable.

Cuando varios agentes pulen un libro en paralelo (revisión de conjunto, auditoría fina
párrafo por párrafo), el riesgo no es la prosa: es que, al reescribir, cambien una cita
verificada, un localizador, una remisión, una nota o una marca de evidencia sin darse
cuenta. En *El cielo de los Nombres* esta comparación, hecha tras cada pasada contra la
copia `.orig`, fue lo que permitió aceptar 15 ediciones simultáneas sin releerlas enteras,
y lo que delató los pocos cambios de fondo (comillas quitadas a una paráfrasis, una marca
añadida) para que el coordinador los autorizara uno por uno.

Rasgos que compara (multiconjuntos, no orden):
  - `citas`       texto entre «…» o “…” de ≥ --min-quote caracteres (lo citado de una fuente)
  - `localizadores` paréntesis con año, §, n.º, p./pp., cap., clase o nota
  - `encabezados` líneas `#` completas (números y títulos: otros capítulos remiten a ellos)
  - `notas`       identificadores de definición `[^x]:` (y su integridad llamada↔definición)
  - `remisiones`  «capítulo N, §X», «Excurso, §XIV», «nota N»
  - `filas`       número de filas de tabla (`|…`)
  - `marcas`      marcas de evidencia (regex --marks; por defecto [E]/[D]/[P]/[O]/[X] y C·A·B)

Uso:
    python3 book_invariants.py original.md editado.md
    python3 book_invariants.py carpeta_orig/ carpeta_editada/      # empareja por nombre
    python3 book_invariants.py a.md b.md --json --marks '\\[[EDPOX]\\]'

Sale con código 1 si algún rasgo difiere. El informe lista, por rasgo, lo que DESAPARECE
(−) y lo que APARECE (+): un cambio autorizado se reconoce a simple vista; uno accidental,
también.

Trampa: las comillas METALINGÜÍSTICAS («la palabra «aspectos»») cuentan como cita si
superan --min-quote; súbelo si el texto las usa mucho. Por defecto, 25 caracteres.
"""
from __future__ import annotations
import argparse, collections, json, re, sys
from pathlib import Path

LOC = re.compile(r"\(([^()]*(?:\d{4}|§|n\.º|n\.os|\bpp?\.\s|\bcap\.|\bcaps\.|\bclase\b|\bnota\b)[^()]*)\)")
REMIS = re.compile(r"cap[íi]tulos?\s+\d+(?:,\s*|\s*\()§§?\s*[\d.]+|\b[A-ZÁÉÍÓÚ]\w+,\s*§§?\s*[IVXLC]+\b|\bnotas?\s+\d+\b", re.I)
DEFAULT_MARKS = r"\[[EDPOX]\]|\b[CAB](?:·[CAB])+\b"


def features(text: str, min_quote: int, marks: str) -> dict:
    lines = text.split("\n")
    defs = re.findall(r"^\[\^([^\]]+)\]:", text, re.M)
    calls = set(re.findall(r"\[\^([^\]]+)\](?!:)", text))
    return {
        "citas": collections.Counter(q for q in re.findall(r"«([^»]+)»|“([^”]+)”", text)
                                     for q in [q[0] or q[1]] if len(q) >= min_quote),
        "localizadores": collections.Counter(LOC.findall(text)),
        "encabezados": collections.Counter(l for l in lines if l.startswith("#")),
        "notas": collections.Counter(defs),
        "remisiones": collections.Counter(REMIS.findall(text)),
        "filas": collections.Counter({"filas de tabla": sum(1 for l in lines if l.startswith("|"))}),
        "marcas": collections.Counter(re.findall(marks, text)),
        "_notas_rotas": sorted((set(defs) ^ calls)),
    }


def compare(a: str, b: str, min_quote: int = 25, marks: str = DEFAULT_MARKS) -> dict:
    fa, fb = features(a, min_quote, marks), features(b, min_quote, marks)
    out = {}
    for k in fa:
        if k.startswith("_"):
            continue
        minus, plus = fa[k] - fb[k], fb[k] - fa[k]
        if k == "filas" and fa[k] != fb[k]:
            out[k] = {"-": [f"{fa[k]['filas de tabla']} → {fb[k]['filas de tabla']}"], "+": []}
        elif minus or plus:
            out[k] = {"-": sorted(minus.elements()), "+": sorted(plus.elements())}
    if fb["_notas_rotas"]:
        out["notas_rotas"] = {"-": [], "+": fb["_notas_rotas"]}
    return out


def pairs(a: Path, b: Path):
    if a.is_dir() and b.is_dir():
        for fa in sorted(a.glob("*.md")):
            fb = b / fa.name
            if fb.exists():
                yield fa.name, fa, fb
            else:
                yield fa.name, fa, None
    else:
        yield b.name, a, b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("original", type=Path)
    ap.add_argument("editado", type=Path)
    ap.add_argument("--min-quote", type=int, default=25)
    ap.add_argument("--marks", default=DEFAULT_MARKS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    report, bad = {}, False
    for name, fa, fb in pairs(a.original, a.editado):
        if fb is None:
            report[name] = {"archivo": {"-": ["falta en la versión editada"], "+": []}}
            bad = True; continue
        d = compare(fa.read_text(encoding="utf-8"), fb.read_text(encoding="utf-8"),
                    a.min_quote, a.marks)
        if d:
            report[name] = d; bad = True
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if not report:
            print("OK: citas, localizadores, encabezados, notas, remisiones, filas y marcas idénticos.")
        for name, d in report.items():
            print(f"== {name}")
            for k, v in d.items():
                for x in v["-"]:
                    print(f"  {k:14} − {x[:110]}")
                for x in v["+"]:
                    print(f"  {k:14} + {x[:110]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
