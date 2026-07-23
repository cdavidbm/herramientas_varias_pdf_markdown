#!/usr/bin/env python3
"""
fix_markup.py — Repara artefactos de MARKUP que deja la extracción de un PDF maquetado:
negrita/cursiva partida por el salto de línea, ordinales con asteriscos espurios, y
encabezados de sección que quedaron como NEGRITA en vez de encabezado real.

Cuatro defectos deterministas, todos frecuentes en libros compuestos con InDesign/
QuarkXPress (el énfasis abarca un salto de línea y el extractor lo parte):

  A) Negrita partida:  `**…** **…**`  →  `**… …**`
     (repetible: algunas líneas encadenan 3+ tramos; también colapsa `****` espurios,
     el cierre+apertura de negrita pegados que dejan visibles los asteriscos).

  B) Cursiva partida en SUBTÍTULOS:  `*Sobre el 2º* *domicilio*`  →  `*Sobre el 2º domicilio*`
     Restringida a líneas-subtítulo (empiezan por `*`, cortas, sin prosa previa) para
     no fundir dos términos en cursiva de un párrafo normal.

  C) Ordinal roto:  `2**º` / `7****º`  →  `2º` / `7º`
     (el volado del ordinal quedó con `**` espurios entre el número y su sufijo).

  D) Encabezado de sección § dejado en NEGRITA/cursiva en vez de `##`/`###`. Cuando el
     libro marca secciones con `§` (convención de las ediciones de Dykes) y unas salieron
     `## §N` pero otras quedaron `**§N: …**`, se homogeneiza por el NÚMERO:
        `**§N: …**` → `## §N: …`   ·   `**§N.M: …**` → `### §N.M: …`
     (capítulo a nivel 2, subsección a nivel 3). Cubre también `§N: **…**`, `§N: …` y
     `*§N*: *…*`. Si el libro no usa `§`, esta regla simplemente no dispara.

Guardas
-------
El encabezado § exige DOS PUNTOS y que la línea EMPIECE por `§N:` → nunca captura una
referencia «véase §5.6» de mitad de frase. La cursiva partida solo actúa en subtítulos.
Todo es idempotente. Simulacro por defecto.

Uso
---
    python3 fix_markup.py cap.md               # simulacro
    python3 fix_markup.py es/*.md en/*.md --apply

Medido en «Works of Sahl & Māshā'allāh» (Dykes): 184 encabizados § promovidos, 132
negritas y 76 cursivas unidas, 28 ordinales, 13 `****` — idénticos en en/ y esp/.
"""
import argparse
import re
from pathlib import Path

# Encabezado § en sus formas rotas: `**§N: …**`, `§N: **…**`, `§N: …`, `*§N*: *…*`.
SEC = re.compile(r"^\*{0,3}§(\d+(?:\.\d+)?)\*{0,3}\s*:\s*(.+?)\s*$")
ORD = re.compile(r"(\d)\*+(º|ª|er|nd|rd|st|th)\b")                # ordinal con `**` espurio
SPLIT = re.compile(r"\*\*([^*\n]+?)\*\* \*\*([^*\n]+?)\*\*")      # negrita partida
ISPLIT = re.compile(r"\*([^*\n]+?)\* \*([^*\n]+?)\*")            # cursiva partida
CUATRO = re.compile(r"\*{4,}")                                    # `****` espurio


def limpia_titulo(s: str) -> str:
    """Quita los `*` de énfasis y colapsa espacios: texto de encabezado limpio."""
    return re.sub(r"\s+", " ", s.replace("*", "")).strip().rstrip("*").strip()


def arregla_texto(txt: str) -> tuple[str, dict]:
    cuenta = {"sec2": 0, "sec3": 0, "split": 0, "isplit": 0, "ord": 0}
    salida = []
    for linea in txt.split("\n"):
        m = SEC.match(linea)
        if m:                                                    # D) encabezado §
            num, resto = m.group(1), m.group(2)
            titulo = limpia_titulo(f"§{num}: {resto}" if resto.strip() else f"§{num}")
            salida.append(f"{'###' if '.' in num else '##'} {titulo}")
            cuenta["sec3" if "." in num else "sec2"] += 1
            continue
        linea, n = ORD.subn(r"\1\2", linea)                      # C) ordinal roto
        cuenta["ord"] += n
        linea = CUATRO.sub("", linea)
        while True:                                              # A) negrita partida
            linea, n = SPLIT.subn(r"**\1 \2**", linea)
            if not n:
                break
            cuenta["split"] += n
        # B) cursiva partida SOLO en líneas-subtítulo (empiezan por `*`, cortas, sin prosa)
        if linea.lstrip().startswith("*") and len(linea) < 120 and " " not in linea.split("*")[0]:
            while True:
                linea, n = ISPLIT.subn(r"*\1 \2*", linea)
                if not n:
                    break
                cuenta["isplit"] += n
        salida.append(linea)
    return "\n".join(salida), cuenta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="markdown a reparar")
    ap.add_argument("--apply", action="store_true", help="escribir (por defecto: simulacro)")
    a = ap.parse_args()
    tot = dict.fromkeys(("sec2", "sec3", "split", "isplit", "ord"), 0)
    for f in a.files:
        txt = f.read_text(encoding="utf-8")
        nuevo, c = arregla_texto(txt)
        if nuevo == txt:
            continue
        for k in tot:
            tot[k] += c[k]
        print(f"{f.name:46s} §→##={c['sec2']:3d} §→###={c['sec3']:3d} "
              f"negrita={c['split']:3d} cursiva={c['isplit']:3d} ordinal={c['ord']:2d}")
        if a.apply:
            f.write_text(nuevo, encoding="utf-8")
    print(f"\n{'APLICADO' if a.apply else 'SIMULACRO'}: {tot['sec2']} §→##, "
          f"{tot['sec3']} §→###, {tot['split']} negritas, {tot['isplit']} cursivas, "
          f"{tot['ord']} ordinales")


if __name__ == "__main__":
    main()
