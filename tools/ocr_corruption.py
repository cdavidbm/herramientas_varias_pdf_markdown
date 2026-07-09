#!/usr/bin/env python3
"""
ocr_corruption.py — Detecta texto OCR probablemente CORRUPTO (sin diccionario).

Marca líneas sospechosas de mala digitalización para que el agente las corrija
CON CRITERIO. No corrige nada (autocorregir textos académicos/multilingües
dañaría términos arcaicos o extranjeros válidos). Solo señala DÓNDE mirar.

Heurísticas seguras y agnósticas de idioma (no usan diccionario):
  - densidad de basura: muchos símbolos/dígitos mezclados con letras
  - "palabras" latinas sin ninguna vocal y largas (ruido típico de OCR)
  - texto espaciado carácter-a-carácter (l e t r a s   s u e l t a s)
  - runs de no-letras (|||, ~=_^) y caracteres de confusión repetidos
Griego/árabe/otros scripts: solo se evalúa densidad de símbolos, no vocales.

Uso:
    python3 ocr_corruption.py archivo.md [archivo2 ...] [--umbral 0.35] [--mostrar 40]
"""
from __future__ import annotations
import argparse
import re
import sys
import unicodedata
from pathlib import Path

VOWELS = set("aeiouáéíóúàèìòùäëïöüâêîôûyAEIOU")
WORD = re.compile(r"\S+")
NONLETTER_RUN = re.compile(r"[^\w\s]{3,}")
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def is_latin(tok: str) -> bool:
    for ch in tok:
        if ch.isalpha():
            try:
                return "LATIN" in unicodedata.name(ch)
            except ValueError:
                return False
    return False


def line_score(line: str) -> tuple[float, list[str]]:
    """Devuelve (score 0-1, razones). Mayor = más sospechoso."""
    s = line.strip()
    if len(s) < 4:
        return 0.0, []
    reasons: list[str] = []
    score = 0.0

    non_space = [c for c in s if not c.isspace()]
    letters = sum(1 for c in non_space if c.isalpha())
    alpha_ratio = letters / max(1, len(non_space))
    if alpha_ratio < 0.55 and len(non_space) > 8:
        score += 0.4; reasons.append(f"pocas letras ({alpha_ratio:.0%})")

    if NONLETTER_RUN.search(s):
        score += 0.25; reasons.append("run de símbolos (|||, ~=_)")

    toks = WORD.findall(s)
    if toks:
        singles = sum(1 for t in toks if len(t) == 1 and t.isalpha())
        if singles / len(toks) > 0.5 and len(toks) > 6:
            score += 0.4; reasons.append("texto espaciado letra-a-letra")

        # palabras latinas largas sin vocales = ruido
        novowel = 0
        for t in toks:
            core = re.sub(r"[^\w]", "", t)
            if len(core) >= 4 and is_latin(core) and not (set(core) & VOWELS):
                novowel += 1
        if novowel >= 2 or (toks and novowel / len(toks) > 0.25):
            score += 0.3; reasons.append(f"{novowel} 'palabra(s)' sin vocales")

        # tokens que mezclan letra+dígito (l0 vs lo, rn vs m…)
        mixed = sum(1 for t in toks if re.search(r"[A-Za-z]\d|\d[A-Za-z]", t))
        if mixed >= 2:
            score += 0.2; reasons.append(f"{mixed} letra+dígito mezclados")

    return min(score, 1.0), reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivos", nargs="+", type=Path)
    ap.add_argument("--umbral", type=float, default=0.35, help="score mínimo para marcar")
    ap.add_argument("--mostrar", type=int, default=40, help="máx. líneas a listar")
    args = ap.parse_args()

    shown = flagged = total = 0
    for path in args.archivos:
        if not path.is_file():
            print(f"(omito {path}: no existe)"); continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total += len(lines)
        hits = []
        for i, ln in enumerate(lines, 1):
            sc, why = line_score(ln)
            if sc >= args.umbral:
                hits.append((i, sc, why, ln.strip()))
        flagged += len(hits)
        if hits:
            print(f"\n== {path.name}: {len(hits)} línea(s) sospechosa(s) de {len(lines)} ==")
            for i, sc, why, txt in hits:
                if shown < args.mostrar:
                    print(f"  L{i} [{sc:.2f}] {', '.join(why)}")
                    print(f"      «{txt[:90]}»")
                    shown += 1

    pct = 100 * flagged / max(1, total)
    print(f"\n── {flagged} línea(s) marcada(s) de {total} ({pct:.1f}%). "
          f"Corrige con criterio SOLO estas; no toques el resto. ──")
    if pct > 25:
        print("   Corrupción alta: si conservas el escaneo original, RE-OCR con "
              "ocr_setup + preprocesado suele superar cualquier arreglo del texto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
