#!/usr/bin/env python3
"""
check_translation.py — Chequeos MECÁNICOS de una traducción markdown vs su original.

No juzga la calidad de la traducción (eso lo hace el agente): verifica que la
ESTRUCTURA se preservó. Pensado para la suite La Forja / skill /traducir-md.

Uso:
    python3 check_translation.py original.md traducido.md [--glosario glosario.md]

Sale con código 1 si hay discrepancias estructurales (útil para automatizar).
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

FENCE = re.compile(r'^```')
FOOTNOTE_DEF = re.compile(r'^\[\^([^\]]+)\]:')         # [^N]: definición
FOOTNOTE_REF = re.compile(r'(?<!\])\[\^([^\]]+)\](?!:)')  # [^N] en el cuerpo
HEADING = re.compile(r'^(#{1,6})\s')
LINK = re.compile(r'(?<!\!)\[[^\]]+\]\(([^)]+)\)')
IMAGE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')


def strip_code(lines: list[str]) -> list[str]:
    """Devuelve las líneas fuera de bloques de código cercados."""
    out, in_fence = [], False
    for ln in lines:
        if FENCE.match(ln):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(ln)
    return out


def analyze(path: Path) -> dict:
    raw = path.read_text(encoding='utf-8', errors='replace').splitlines()
    body = strip_code(raw)
    text = "\n".join(body)
    refs = sorted({m for ln in body for m in FOOTNOTE_REF.findall(ln)},
                  key=lambda s: (len(s), s))
    def_set, heading_list = set(), []
    for ln in body:
        if (md := FOOTNOTE_DEF.match(ln)):
            def_set.add(md.group(1))
        if (mh := HEADING.match(ln)):
            heading_list.append(mh.group(1))
    defs = sorted(def_set, key=lambda s: (len(s), s))
    headings = heading_list
    return {
        "fences": sum(1 for ln in raw if FENCE.match(ln)) // 2,
        "footnote_refs": refs,
        "footnote_defs": defs,
        "headings": headings,
        "n_headings": len(headings),
        "links": LINK.findall(text),
        "images": IMAGE.findall(text),
        "numbers": re.findall(r'\d+', text),
        "paras": [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()],
        "words": len(text.split()),
        "last": next((p.strip() for p in reversed(re.split(r'\n\s*\n', text)) if p.strip()), ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original", type=Path)
    ap.add_argument("traducido", type=Path)
    ap.add_argument("--glosario", type=Path, help="glosario.md con tabla | origen | destino |")
    args = ap.parse_args()

    o = analyze(args.original)
    t = analyze(args.traducido)
    problemas: list[str] = []
    avisos: list[str] = []

    print(f"== QA: {args.original.name}  →  {args.traducido.name} ==\n")

    # 1. Notas al pie: paridad de marcadores y definiciones
    print(f"Notas [^N] en cuerpo:   original {len(o['footnote_refs']):>3} | traducido {len(t['footnote_refs']):>3}")
    print(f"Definiciones [^N]::     original {len(o['footnote_defs']):>3} | traducido {len(t['footnote_defs']):>3}")
    if o["footnote_refs"] != t["footnote_refs"]:
        falt = set(o["footnote_refs"]) - set(t["footnote_refs"])
        extra = set(t["footnote_refs"]) - set(o["footnote_refs"])
        if falt:  problemas.append(f"Faltan marcadores de nota en la traducción: {sorted(falt)}")
        if extra: problemas.append(f"Marcadores de nota de más en la traducción: {sorted(extra)}")
    if set(t["footnote_refs"]) != set(t["footnote_defs"]):
        sin_def = set(t["footnote_refs"]) - set(t["footnote_defs"])
        sin_ref = set(t["footnote_defs"]) - set(t["footnote_refs"])
        if sin_def: problemas.append(f"Notas citadas sin definición [^N]: {sorted(sin_def)}")
        if sin_ref: avisos.append(f"Definiciones sin cita en el cuerpo: {sorted(sin_ref)}")

    # 1b. Recuento de palabras: detecta TRUNCAMIENTO (el fallo más traicionero de
    #     traducir capítulos largos con un solo pase: el modelo se corta a mitad).
    ratio = t["words"] / max(1, o["words"])
    print(f"Palabras:               original {o['words']:>5} | traducido {t['words']:>5}  (ratio {ratio:.2f})")
    if ratio < 0.85:
        problemas.append(f"Traducción MUY corta (ratio {ratio:.2f}): probable TRUNCAMIENTO u "
                         f"omisiones. El español suele igualar o superar (~1.0–1.15) al inglés. "
                         f"Última frase del traducido: «{t['last'][:80]}…» — compárala con el final "
                         f"del original.")
    elif ratio > 1.30:
        avisos.append(f"Traducción inusualmente larga (ratio {ratio:.2f}): ¿añadidos o duplicación?")

    # 2. Encabezados: mismo número y misma jerarquía de niveles
    print(f"Encabezados:            original {o['n_headings']:>3} | traducido {t['n_headings']:>3}")
    if o["headings"] != t["headings"]:
        if o["n_headings"] != t["n_headings"]:
            problemas.append(f"Distinto número de encabezados ({o['n_headings']} vs {t['n_headings']}).")
        else:
            problemas.append("Los niveles de encabezado no coinciden en orden (se alteró la jerarquía).")

    # 3. Enlaces e imágenes: las URLs deben conservarse idénticas
    if sorted(o["links"]) != sorted(t["links"]):
        avisos.append(f"Las URLs de enlaces no coinciden (original {len(o['links'])}, traducido {len(t['links'])}).")
    if sorted(o["images"]) != sorted(t["images"]):
        avisos.append(f"Las URLs de imágenes no coinciden (original {len(o['images'])}, traducido {len(t['images'])}).")
    if o["fences"] != t["fences"]:
        avisos.append(f"Distinto número de bloques de código ({o['fences']} vs {t['fences']}).")

    # 4. Texto sin traducir: párrafos idénticos no triviales
    set_o = set(o["paras"])
    identicos = [p for p in t["paras"]
                 if p in set_o and len(p) > 40 and not HEADING.match(p)]
    if identicos:
        avisos.append(f"{len(identicos)} párrafo(s) idénticos al original (¿sin traducir?). "
                      f"Primero: «{identicos[0][:70]}…»")

    # 4b. Números: años, páginas y cifras deben conservarse (multiconjunto)
    from collections import Counter
    co, ct = Counter(o["numbers"]), Counter(t["numbers"])
    perdidos = sorted((co - ct).elements(), key=lambda s: (len(s), s))
    if perdidos:
        avisos.append(f"Números del original ausentes en la traducción "
                      f"(¿cifras/años/páginas omitidos?): {perdidos[:15]}")

    # 5. Glosario: que ningún término ORIGEN quede suelto en la traducción
    if args.glosario and args.glosario.is_file():
        filas = re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|',
                           args.glosario.read_text(encoding='utf-8', errors='replace'),
                           re.MULTILINE)
        t_text = "\n".join(t["paras"]).lower()
        fugas = []
        for origen, destino in filas:
            origen = origen.strip()
            if origen.lower() in ("origen", "source", "término", "termino"):
                continue  # cabecera de la tabla
            if origen and re.search(rf'\b{re.escape(origen.lower())}\b', t_text):
                fugas.append(f"{origen} → {destino.strip()}")
        if fugas:
            avisos.append("Posibles términos del glosario SIN traducir en el texto: "
                          + "; ".join(fugas[:10]))

    # --- Informe ---
    print()
    if problemas:
        print("🔴 PROBLEMAS (estructura rota):")
        for p in problemas: print(f"   - {p}")
    if avisos:
        print("🟡 AVISOS (revisar a mano):")
        for a in avisos: print(f"   - {a}")
    if not problemas and not avisos:
        print("🟢 Sin discrepancias estructurales. (La calidad semántica la juzga el agente.)")

    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
