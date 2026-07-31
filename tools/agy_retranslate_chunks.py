#!/usr/bin/env python3
"""agy_retranslate_chunks.py — retraduce un markdown VERIFICANDO CADA TROZO.

Por qué existe
--------------
`agy_translate.py` verifica el archivo ENTERO al final: si agy se saltó prosa en
un trozo, lo único que se ve es un ratio bajo, y la única reparación posible es
relanzar el archivo completo — que vuelve a fallar, porque el trozo grande sigue
siendo grande. Medido en el Picatrix (cap. 3.11, 8.407 palabras): dos intentos de
`agy_translate` dejaron el ratio en 0.68 y 0.86, con ~1.200 palabras perdidas en
DOS tramos concretos, mientras el aparato de notas cuadraba 21/21 — así que ni el
balance de notas ni los encabezados lo delataban.

Aquí cada trozo se verifica NADA MÁS traducirlo (ratio + sus `[^N]`) y, si no
cuadra, se reintenta ese trozo solo; si vuelve a fallar, se PARTE EN DOS y cada
mitad va por separado. El fallo se ataja donde ocurre y no contamina el resto.

Las definiciones `[^N]:` se traducen aparte, una a una, porque son la parte que
más barato es verificar (deben salir todas, con su número intacto).

Uso
---
    python3 agy_retranslate_chunks.py en/cap.md --out es/cap.md \\
        --glosario glosario.md --prompt PROMPT.txt --workdir _work
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REF = re.compile(r"\[\^(\d+)\](?!:)")
DEFLINE = re.compile(r"^\[\^(\d+)\]:", re.M)


def agy(prompt: str, workdir: Path, model: str, binpath: str) -> str:
    r = subprocess.run([binpath, "-p", prompt, "--model", model,
                        "--add-dir", str(workdir), "--dangerously-skip-permissions"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def split_body_defs(md: str) -> tuple[str, list[str]]:
    lines = md.split("\n")
    body, defs = [], []
    for ln in lines:
        (defs if DEFLINE.match(ln) else body).append(ln)
    return "\n".join(body).strip(), [d for d in defs if d.strip()]


def chunk(paras: list[str], max_words: int) -> list[list[str]]:
    out, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > max_words:
            out.append(cur); cur, n = [], 0
        cur.append(p); n += w
    if cur:
        out.append(cur)
    return out


def translate_verified(text: str, base_prompt: str, glos: str, workdir: Path,
                       model: str, binpath: str, depth: int = 0) -> str:
    """Traduce un trozo y NO lo da por bueno hasta que cuadre."""
    want_refs = set(REF.findall(text))
    n_en = len(text.split())
    prompt = (f"{base_prompt}\nLee {glos} (terminología obligatoria) y traduce al español el "
              f"markdown siguiente. Devuelve SOLO el markdown traducido, ÍNTEGRO —sin omitir ni "
              f"resumir NINGÚN párrafo—, conservando [^N], encabezados, cifras y cursivas:\n\n{text}")
    best = ""
    for _ in range(3):
        es = agy(prompt, workdir, model, binpath)
        if not es:
            continue
        ratio = len(es.split()) / max(1, n_en)
        if set(REF.findall(es)) >= want_refs and 0.85 <= ratio <= 1.45:
            return es
        if len(es.split()) > len(best.split()):
            best = es
    # Sigue sin cuadrar: partir en dos y traducir cada mitad por su cuenta.
    paras = [p for p in text.split("\n\n") if p.strip()]
    if depth < 3 and len(paras) > 1:
        mid = len(paras) // 2
        a = translate_verified("\n\n".join(paras[:mid]), base_prompt, glos, workdir,
                               model, binpath, depth + 1)
        b = translate_verified("\n\n".join(paras[mid:]), base_prompt, glos, workdir,
                               model, binpath, depth + 1)
        return a + "\n\n" + b
    print(f"  aviso: trozo sin cuadrar tras reintentos ({n_en} palabras)", file=sys.stderr)
    return best or text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glosario", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, default=Path("_work"))
    ap.add_argument("--chunk-words", type=int, default=700)
    ap.add_argument("--model", default="Gemini 3.1 Pro (High)")
    ap.add_argument("--agy-bin", default="/home/chris/.local/bin/agy")
    args = ap.parse_args()

    md = args.src.read_text(encoding="utf-8")
    args.workdir.mkdir(parents=True, exist_ok=True)
    glos_local = args.workdir / args.glosario.name
    if not glos_local.exists() or glos_local.resolve() != args.glosario.resolve():
        glos_local.write_text(args.glosario.read_text(encoding="utf-8"), encoding="utf-8")
    base_prompt = args.prompt.read_text(encoding="utf-8")

    body, defs = split_body_defs(md)
    paras = [p for p in body.split("\n\n") if p.strip()]
    groups = chunk(paras, args.chunk_words)
    print(f"[retraducción] {args.src.name}: {len(groups)} trozos de cuerpo + "
          f"{len(defs)} definiciones", file=sys.stderr)

    out_parts = []
    for i, g in enumerate(groups, 1):
        es = translate_verified("\n\n".join(g), base_prompt, args.glosario.name,
                                args.workdir, args.model, args.agy_bin)
        out_parts.append(es)
        print(f"  trozo {i}/{len(groups)} ok", file=sys.stderr)

    defs_es = []
    for grp in chunk(defs, 400):
        es = translate_verified("\n".join(grp), base_prompt, args.glosario.name,
                                args.workdir, args.model, args.agy_bin)
        defs_es.append(es)

    out = "\n\n".join(out_parts).strip() + "\n\n" + "\n".join(defs_es).strip() + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")

    r_en, r_es = set(REF.findall(md)), set(REF.findall(out))
    d_en, d_es = set(DEFLINE.findall(md)), set(DEFLINE.findall(out))
    ratio = len(out.split()) / max(1, len(md.split()))
    print(f"-> {args.out}\n   llamadas {len(r_es)}/{len(r_en)} (faltan {sorted(r_en - r_es)})"
          f"\n   definiciones {len(d_es)}/{len(d_en)} (faltan {sorted(d_en - d_es)})"
          f"\n   ratio {ratio:.3f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
