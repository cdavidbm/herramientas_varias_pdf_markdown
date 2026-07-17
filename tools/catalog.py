#!/usr/bin/env python3
"""catalog.py — genera el CATÁLOGO ÚNICO de todas las tools de La Forja.

El problema que resuelve: con ~46 scripts, «reconocer todo lo disponible» dependía
de la prosa (larga y cambiante) de CLAUDE.md + memoria. Un libro difícil podía
toparse con una tool que existe pero que el agente no recuerda (medido: book_index,
book_map eran invisibles en CLAUDE.md). Aquí, en cambio, el índice se DERIVA de los
docstrings, así que enumera SIEMPRE las 46 y no puede desincronizarse.

Lee la 1ª línea útil del docstring de cada `tools/*.py`, las agrupa por función y
emite `tools/CATALOG.md`. Marca además las que NO se mencionan en CLAUDE.md (drift).

    python3 catalog.py            # imprime el catálogo
    python3 catalog.py --write    # escribe tools/CATALOG.md
    python3 catalog.py --check    # exit≠0 si alguna tool no está en CATALOG (para CI)
"""
from __future__ import annotations
import argparse, ast, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# (etiqueta de grupo, predicado sobre el nombre de archivo) — orden = orden del índice
GROUPS = [
    ("Puertas / orquestadores", lambda n: n in {
        "forja_limpiar.py", "fix_ocr.py", "limpiar_academico.py"}),
    ("Conversores (bisturíes)", lambda n: n.endswith("to_markdown.py")),
    ("Sondas / diagnóstico", lambda n: n in {
        "pdf_headings.py", "pdf_blocks.py", "detect_chapters.py", "book_map.py",
        "book_index.py", "ocr_corruption.py"}),
    ("Split / manipulación PDF", lambda n: n.startswith("split_") or n in {
        "ocr_incremental.py", "docling_incremental.py"}),
    ("Limpieza post-conversión", lambda n: n.startswith(("clean_", "fix_", "docling_"))
        or n in {"verse_paragraphs.py", "footnotes_rebuild.py", "astro_glyphs.py",
                 "flag_ocr_artifacts.py", "ocr_spellfix.py", "ocr_preprocess.py"}),
    ("Verificación / auditoría", lambda n: n in {
        "check_completeness.py", "audit_conversion.py", "chapter_bounds.py",
        "index_rebuild.py"}),
    ("Salida / build", lambda n: n in {"md_to_pdf.py", "build_plan.py",
        "latex_to_markdown.py"}),
    ("YouTube", lambda n: n.startswith("yt_") or n == "asr_setup.sh"),
    ("Librería compartida", lambda n: n in {"forja_common.py", "catalog.py"}),
]


def one_liner(path: Path) -> str:
    """1ª línea útil del docstring, sin el prefijo `nombre.py —`."""
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    except SyntaxError:
        doc = ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[\w.]+\.py\s*[—-]\s*", "", s)   # quita «name.py — »
        return s.rstrip()
    return "(sin docstring)"


def classify(names: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {g: [] for g, _ in GROUPS}
    seen = set()
    for n in names:
        for g, pred in GROUPS:
            if pred(n):
                out[g].append(n); seen.add(n); break
    otros = [n for n in names if n not in seen]
    if otros:
        out["Otros"] = otros
    return out


def build() -> tuple[str, list[str]]:
    py = sorted(p.name for p in HERE.glob("*.py"))
    grouped = classify(py)
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8") if (ROOT / "CLAUDE.md").is_file() else ""
    lines = ["# Catálogo de La Forja — todas las tools de un vistazo", "",
             "> Autogenerado por `catalog.py` desde los docstrings. **No editar a mano**;"
             " corre `python3 tools/catalog.py --write`. `⚠` = no mencionada en CLAUDE.md.", ""]
    invisibles = []
    for g, _ in GROUPS + [("Otros", None)]:
        items = grouped.get(g)
        if not items:
            continue
        lines.append(f"## {g}")
        for n in items:
            mark = "" if n[:-3] in claude or n in claude else " ⚠"
            if mark:
                invisibles.append(n)
            lines.append(f"- `{n}`{mark} — {one_liner(HERE / n)}")
        lines.append("")
    return "\n".join(lines), invisibles


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="escribe tools/CATALOG.md")
    ap.add_argument("--check", action="store_true", help="exit≠0 si el catálogo está desactualizado")
    a = ap.parse_args()
    text, invisibles = build()
    dst = HERE / "CATALOG.md"
    if a.check:
        current = dst.read_text(encoding="utf-8") if dst.is_file() else ""
        if current.strip() != text.strip():
            print("CATALOG.md desactualizado: corre `python3 tools/catalog.py --write`")
            return 1
        print("CATALOG.md al día ✓")
        return 0
    if a.write:
        dst.write_text(text + "\n", encoding="utf-8")
        print(f"escrito {dst.relative_to(ROOT)} ({text.count(chr(10))+1} líneas)")
    else:
        print(text)
    if invisibles:
        print(f"\n⚠ {len(invisibles)} tool(s) no mencionadas en CLAUDE.md: {', '.join(invisibles)}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
