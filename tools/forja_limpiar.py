#!/usr/bin/env python3
"""forja_limpiar.py — PUERTA ÚNICA de post-limpieza de un libro convertido.

El problema que resuelve: la suite tiene ~12 arregladores sueltos y «qué correr, en
qué orden» vivía en la prosa de CLAUDE.md y en la cabeza del agente. Aquí esa RECETA
queda en código: una sola orden limpia un libro entero aplicando, EN ORDEN, las
correcciones deterministas y seguras, y termina con un informe de lo que hay que
mirar a mano.

Generaliza a `limpiar_academico.py` (que solo cubría 3 fixers OUP).

NÚCLEO (siempre, determinista y con guardas — cada fixer es no-op si su patrón no
está, así que componerlos es seguro):
    fix_ocr: ordinals · romans · ligatures · diacritics

OPCIONALES (activa según el libro):
    --verses     un párrafo por verso (texto versificado; verse_paragraphs)
    --notas      reconstruye notas [^N] por archivo (footnotes_rebuild)
    --openings   arregla portadillas/capitulares (clean_openings; OUP)
    --docling    normalización fina de salida Docling (docling_clean)
    --spell      erratas OCR con el libro como corpus (CONSERVADOR; solo informa)

Termina SIEMPRE con el informe de `flag_ocr_artifacts` (qué revisar contra la
imagen), salvo `--no-report`.

Dry-run por defecto; `--apply` escribe. Uso:
    python3 forja_limpiar.py ./markdown                 # informe de qué haría
    python3 forja_limpiar.py ./markdown --apply         # núcleo determinista
    python3 forja_limpiar.py ./markdown --verses --notas --apply
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fix_ocr, verse_paragraphs, footnotes_rebuild, clean_openings, docling_clean  # noqa: E402
import flag_ocr_artifacts  # noqa: E402


def _write(f: Path, new: str, apply: bool):
    if apply:
        f.write_text(new, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="carpeta con los .md (o un .md suelto)")
    ap.add_argument("--apply", action="store_true", help="escribe (def: dry-run)")
    ap.add_argument("--verses", action="store_true", help="un párrafo por verso")
    ap.add_argument("--notas", action="store_true", help="reconstruye notas [^N]")
    ap.add_argument("--openings", action="store_true", help="portadillas/capitulares (OUP)")
    ap.add_argument("--docling", action="store_true", help="normalización fina Docling")
    ap.add_argument("--spell", action="store_true", help="erratas OCR (conservador, solo informa)")
    ap.add_argument("--no-report", action="store_true", help="sin informe final de artefactos")
    a = ap.parse_args()

    if a.folder.is_dir():
        files = sorted(a.folder.glob("*.md"))
    elif a.folder.is_file():
        files = [a.folder]
    else:
        sys.exit(f"error: no existe {a.folder}")
    if not files:
        sys.exit(f"error: no hay .md en {a.folder}")

    counts: dict[str, int] = {}

    def bump(k, n): counts[k] = counts.get(k, 0) + n

    for f in files:
        text = f.read_text(encoding="utf-8")
        # 1) reflow versificado (antes que nada: cambia la estructura de párrafos)
        if a.verses:
            text, n = verse_paragraphs.process(text, 199); bump("versos", n)
        # 2) notas [^N]  (rebuild devuelve (texto, stats))
        if a.notas:
            new, _stats = footnotes_rebuild.rebuild(text)
            if new != text:
                bump("notas", 1); text = new
        # 3) núcleo determinista de OCR (ordinales, romanos, ligaduras, diacríticos)
        for name, fn in fix_ocr.DETERMINISTIC:
            text, n = fn(text); bump(name, n)
        # 4) aperturas OUP / Docling (opcionales)
        if a.openings:
            text, _ = clean_openings.clean(text)
        if a.docling:
            text = docling_clean.fix_space_ligatures(docling_clean.fix_spacing(
                docling_clean.fix_accents(text)))
        _write(f, text, a.apply)

    # spell aparte (usa el corpus completo y solo INFORMA salvo --apply explícito)
    if a.spell:
        print("\n[spell] (conservador — revisa antes de aplicar)")
        fix_ocr._run_spell(files, a.apply, 1)

    verb = "APLICADO" if a.apply else "DRY-RUN (usa --apply)"
    print(f"\n=== {verb} · {len(files)} archivo(s) ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")

    # informe final: qué revisar a mano contra la imagen
    if not a.no_report:
        hits = flag_ocr_artifacts.check(files, {"garbage", "stray", "bracket", "split"})
        print(f"\n[revisar a mano] {len(hits)} artefacto(s) señalado(s) por flag_ocr_artifacts"
              + (" — corre `flag_ocr_artifacts.py` para el detalle." if hits else " ✓"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
