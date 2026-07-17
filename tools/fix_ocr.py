#!/usr/bin/env python3
"""fix_ocr.py — puerta ÚNICA a las correcciones de texto OCR de La Forja.

Reúne bajo un solo comando los cinco arregladores que antes eran scripts sueltos.
La LÓGICA de cada uno sigue viviendo (y testeándose) en su módulo; esto es la
FACHADA que da una interfaz coherente y un orden de aplicación seguro, para que no
haya que recordar cinco comandos con cinco convenciones distintas.

  fix_ocr.py ordinals   FILE...   4 lh→4th, ll'h→11th, I1'→1st (escaneos)
  fix_ocr.py romans     FILE...   Volume IT→II, Ch. IIL→III, «I»-pronombre
  fix_ocr.py ligatures  FILE...   conWrmation→confirmation (OUP, guarda de dicc.)
  fix_ocr.py diacritics FILE...   Martı´n→Martín, Wolfenb€uttel→Wolfenbüttel, +NFC
  fix_ocr.py spell      FILE...   erratas OCR con el libro como modelo (CONSERVADOR)
  fix_ocr.py all        FILE...   los 4 deterministas (NO spell: pide revisión ojo)

Dry-run por defecto; `--apply` escribe. Cada subcomando conserva las MISMAS guardas
de seguridad que su módulo (protege nombres propios, transliteraciones, latín,
griego, árabe…). Para el flujo completo de post-limpieza usa `forja_limpiar.py`.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fix_ordinals, fix_roman_numerals, fix_ligatures, fix_diacritics, ocr_spellfix  # noqa: E402
from forja_common import load_dict  # noqa: E402

_LIG_FIXER = None


def _ordinals(text: str) -> tuple[str, int]:
    return fix_ordinals.fix(text)


def _romans(text: str) -> tuple[str, int]:
    new, changes = fix_roman_numerals.process(text)
    return new, len(changes)


def _diacritics(text: str) -> tuple[str, int]:
    return fix_diacritics.fix(text)


def _ligatures(text: str) -> tuple[str, int]:
    global _LIG_FIXER
    if _LIG_FIXER is None:
        words = load_dict()
        if not words:
            sys.exit("error: no hay diccionario (apt install wbritish wamerican); "
                     "sin él, ligatures no corrige nada por seguridad.")
        _LIG_FIXER = fix_ligatures.make_fixer(words)
    new, n, _ = fix_ligatures.process(text, _LIG_FIXER)
    return new, n


# subcomandos deterministas y seguros, en orden de aplicación recomendado
DETERMINISTIC = [("ordinals", _ordinals), ("romans", _romans),
                 ("ligatures", _ligatures), ("diacritics", _diacritics)]
FIXERS = dict(DETERMINISTIC)


def _apply_fixer(fn, files, apply):
    total = 0
    for f in files:
        old = f.read_text(encoding="utf-8")
        new, n = fn(old)
        total += n
        if n:
            print(f"  {f.name}: {n} cambio(s)")
            if apply:
                f.write_text(new, encoding="utf-8")
    return total


def _run_spell(files, apply, max_edits):
    corpus = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
    fx = ocr_spellfix.Fixer(corpus, min_freq=3, max_edits=max_edits)
    total = 0
    for f in files:
        changes: list = []
        new = fx.fix_text(f.read_text(encoding="utf-8"), changes)
        total += len(changes)
        if changes:
            print(f"  {f.name}: {len(changes)} corrección(es)")
            for a, b in changes[:20]:
                print(f"     «{a}» → «{b}»")
            if apply:
                f.write_text(new, encoding="utf-8")
    return total


def collect(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(p.glob("*.md"))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"error: no existe {p}")
    if not files:
        sys.exit("error: no hay archivos .md")
    return files


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=[k for k, _ in DETERMINISTIC] + ["spell", "all"],
                    help="qué corregir")
    ap.add_argument("files", nargs="+", type=Path, help=".md o carpeta(s)")
    ap.add_argument("--apply", action="store_true", help="escribe (def: dry-run)")
    ap.add_argument("--max-edits", type=int, default=1, help="spell: distancia máx (def 1)")
    a = ap.parse_args()
    files = collect(a.files)

    if a.cmd == "spell":
        total = _run_spell(files, a.apply, a.max_edits)
    elif a.cmd == "all":
        total = 0
        for name, fn in DETERMINISTIC:
            print(f"[{name}]")
            total += _apply_fixer(fn, files, a.apply)
    else:
        total = _apply_fixer(FIXERS[a.cmd], files, a.apply)

    verb = "aplicados" if a.apply else "en dry-run (usa --apply)"
    print(f"\nTOTAL {a.cmd}: {total} cambio(s) {verb} · {len(files)} archivo(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
