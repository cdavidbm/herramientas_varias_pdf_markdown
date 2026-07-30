#!/usr/bin/env python3
"""footnotes_redistribute.py — mueve las definiciones `[^N]:` agrupadas al final
de un archivo hasta el final de la SECCIÓN donde está su llamada.

Para qué sirve
--------------
Muchos EPUB (Calibre/Kindle) guardan TODAS las notas en un documento-pool, así
que el conversor las vuelca juntas al final de cada archivo, típicamente bajo un
encabezado «## Notes». Eso se lee bien mientras el archivo es un libro entero,
pero **al trocear por capítulos las definiciones se quedan TODAS en el último
trozo**: los capítulos anteriores conservan sus llamadas `[^N]` sin definición y,
al maquetar, esas notas NO se imprimen (pandoc descarta la llamada huérfana en
silencio). El defecto no lo ve el balance refs↔defs del archivo sin trocear.

Por eso este paso va ANTES de `split_chapters.py`: reparte cada definición al
final de la sección que la invoca, y así el troceo se la lleva con su capítulo.

Reglas
------
* Una definición va a la sección donde aparece su PRIMERA llamada.
* Las definiciones sin llamada NO se borran: se dejan donde estaban (bajo su
  encabezado) y se reportan — perderlas es peor que dejarlas descolocadas.
* El encabezado del bloque de notas se elimina solo si se queda vacío.
* No se renumera nada: las etiquetas originales se conservan (`md_to_pdf`
  renumera al maquetar).
* No toca bloques de código cercados.

Uso
---
    python3 footnotes_redistribute.py libro.md --level 3            # dry-run
    python3 footnotes_redistribute.py libro.md --level 3 --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEF_RE = re.compile(r"^\[\^([^\]]+)\]:")
REF_RE = re.compile(r"\[\^([^\]]+)\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _mask_fences(lines: list[str]) -> list[bool]:
    """Devuelve, por línea, si está dentro de un bloque de código cercado."""
    inside = False
    out: list[bool] = []
    for ln in lines:
        if FENCE_RE.match(ln):
            out.append(True)
            inside = not inside
            continue
        out.append(inside)
    return out


def redistribute(text: str, level: int) -> tuple[str, dict]:
    lines = text.split("\n")
    fenced = _mask_fences(lines)

    # 1. Localizar las definiciones (fuera de código).
    def_idx: dict[str, int] = {}
    def_lines: set[int] = set()
    for i, ln in enumerate(lines):
        if fenced[i]:
            continue
        m = DEF_RE.match(ln)
        if m and m.group(1) not in def_idx:
            def_idx[m.group(1)] = i
            def_lines.add(i)

    stats = {"defs": len(def_idx), "moved": 0, "orphan_defs": [], "unresolved_refs": []}
    if not def_idx:
        return text, stats

    # 2. Trocear el cuerpo en secciones del nivel pedido.
    #    bounds[k] = (inicio, fin_exclusivo) de la sección k; la 0 es el preámbulo.
    starts = [0]
    for i, ln in enumerate(lines):
        if fenced[i] or i in def_lines:
            continue
        m = HEADING_RE.match(ln)
        if m and len(m.group(1)) == level:
            starts.append(i)
    starts = sorted(set(starts))
    bounds = [(s, starts[k + 1] if k + 1 < len(starts) else len(lines))
              for k, s in enumerate(starts)]

    # 3. Sección de la PRIMERA llamada de cada etiqueta.
    target: dict[str, int] = {}
    for k, (s, e) in enumerate(bounds):
        for i in range(s, e):
            if fenced[i] or i in def_lines:
                continue
            for label in REF_RE.findall(lines[i]):
                if label in def_idx and label not in target:
                    target[label] = k

    for label in def_idx:
        if label not in target:
            stats["orphan_defs"].append(label)

    # Llamadas sin definición (solo informativo).
    seen_refs: set[str] = set()
    for i, ln in enumerate(lines):
        if fenced[i] or i in def_lines:
            continue
        seen_refs.update(REF_RE.findall(ln))
    stats["unresolved_refs"] = sorted(seen_refs - set(def_idx))

    # 4. Reconstruir: las definiciones reubicadas salen de su sitio y se
    #    reinyectan al final de su sección (en orden de etiqueta original).
    moved = {lab for lab in def_idx if lab in target}
    stats["moved"] = len(moved)

    per_section: dict[int, list[str]] = {}
    for lab, k in target.items():
        per_section.setdefault(k, []).append(lab)
    for k in per_section:
        per_section[k].sort(key=lambda lab: def_idx[lab])

    # El encabezado que precede al bloque de notas se borra si se queda sin
    # ninguna definición debajo.
    first_def = min(def_idx.values())
    heading_to_drop = None
    if not stats["orphan_defs"]:
        for i in range(first_def - 1, -1, -1):
            if lines[i].strip() == "":
                continue
            if HEADING_RE.match(lines[i]) and not fenced[i]:
                heading_to_drop = i
            break

    out: list[str] = []
    for k, (s, e) in enumerate(bounds):
        body: list[str] = []
        for i in range(s, e):
            if i == heading_to_drop:
                continue
            if i in def_lines:
                lab = DEF_RE.match(lines[i]).group(1)  # type: ignore[union-attr]
                if lab in moved:
                    continue  # se reinyecta en su sección
            body.append(lines[i])
        while body and body[-1].strip() == "":
            body.pop()
        if per_section.get(k):
            if body:
                body.append("")
            body.extend(lines[def_idx[lab]] for lab in per_section[k])
        out.extend(body)
        out.append("")

    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n", stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--level", type=int, default=2,
                    help="nivel de encabezado que delimita la sección (def. 2)")
    ap.add_argument("--apply", action="store_true", help="escribir los cambios")
    args = ap.parse_args()

    rc = 0
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"warning: no existe: {p}", file=sys.stderr)
            rc = 1
            continue
        text = p.read_text(encoding="utf-8")
        new, st = redistribute(text, args.level)
        tag = "" if args.apply else " (dry-run)"
        print(f"{p}: {st['defs']} definiciones, {st['moved']} reubicadas{tag}")
        if st["orphan_defs"]:
            print(f"  ojo: {len(st['orphan_defs'])} definición(es) SIN llamada, "
                  f"se dejan donde estaban: {', '.join(st['orphan_defs'][:10])}"
                  + (" …" if len(st["orphan_defs"]) > 10 else ""))
        if st["unresolved_refs"]:
            print(f"  ojo: {len(st['unresolved_refs'])} llamada(s) sin definición: "
                  f"{', '.join(st['unresolved_refs'][:10])}"
                  + (" …" if len(st["unresolved_refs"]) > 10 else ""))
        if args.apply and new != text:
            p.write_text(new, encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
