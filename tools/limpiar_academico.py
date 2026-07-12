#!/usr/bin/env python3
"""
limpiar_academico.py — Orquestador de POST-LIMPIEZA para markdown de libros
académicos/escaneos (OUP y similares). Aplica en orden, sobre todos los `.md` de
una carpeta, las correcciones deterministas de La Forja:

    1. fix_ligatures.py   — fi/ff/fl→W/V/X… (con guarda de diccionario)
    2. fix_diacritics.py  — ı/€/acentos desplazados + NFC
    3. clean_openings.py  — portadillas y capitulares partidas (se autosalta si no aplica)

NO hace la verificación de completitud (eso es check_completeness.py, que necesita
el PDF fuente): córrela aparte, ANTES de traducir. Uso:

    python3 limpiar_academico.py ./markdown
    python3 limpiar_academico.py ./markdown --no-openings   # p. ej. back-matter
    python3 limpiar_academico.py ./markdown --report        # muestra, no escribe
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fix_ligatures            # noqa: E402
import fix_diacritics           # noqa: E402
import clean_openings           # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="carpeta con los .md")
    ap.add_argument("--no-openings", action="store_true",
                    help="no tocar aperturas de capítulo (para back-matter/notas/índice)")
    ap.add_argument("--report", action="store_true", help="muestra qué haría, no escribe")
    args = ap.parse_args()

    mds = sorted(p for p in args.folder.glob("*.md") if p.name.lower() != "glosario.md")
    if not mds:
        sys.exit(f"no hay .md en {args.folder}")

    words = fix_ligatures.load_words()
    if not words:
        sys.exit("error: falta diccionario (apt install wbritish wamerican).")
    fixer = fix_ligatures.make_fixer(words)

    tot_lig = 0
    for p in mds:
        text = p.read_text(encoding="utf-8")
        text, n_lig, _ = fix_ligatures.process(text, fixer); tot_lig += n_lig
        text, _ = fix_diacritics.fix(text)
        msg = "(sin apertura)"
        if not args.no_openings:
            text, msg = clean_openings.clean(text)
        if not args.report:
            p.write_text(text, encoding="utf-8")
        print(f"  {p.name}: {n_lig} ligaduras · diacríticos · {msg}")
    print(f"— ligaduras totales: {tot_lig} · {len(mds)} archivo(s) —")
    print("Recuerda: verifica completitud con check_completeness.py ANTES de traducir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
