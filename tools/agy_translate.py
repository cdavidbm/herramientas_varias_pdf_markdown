#!/usr/bin/env python3
"""
agy_translate.py — Traduce un markdown de capítulo/Book a otro idioma con agy/Gemini,
troceando para no truncar, y con QA estructural contra el original.

Contraparte de `agy_transcribe.py` para la fase de traducción-como-QA. El markdown de
origen (p.ej. inglés de alta fidelidad) se trocea por párrafos, cada trozo lo traduce
agy/Gemini leyendo el `glosario.md` (terminología fijada), y se reensambla. Las notas
`[^N]` conservan su numeración (única por archivo), así que la reconstrucción es
concatenación directa. QA: mismo conjunto de refs/defs de nota, mismos encabezados y
figuras, sin inglés residual evidente, ratio de palabras ES/EN sensato.

NO sustituye la verificación humana/del director: es el ANDAMIAJE que produce el
borrador fiel y barato (cuota Gemini) que luego se revisa. La imagen del PDF sigue
siendo la autoridad ante cualquier duda de cifra/transliteración.

Uso:
  python3 agy_translate.py en/04_Book_IV.md --out es/04_Book_IV.md \
      --glosario glosario.md --prompt _work/TRANSLATE_PROMPT.txt --workdir _work \
      [--chunk-words 1800] [--parallel 3] [--model "Gemini 3.1 Pro (High)"]
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

FNDEF = re.compile(r"^\[\^(\d+)\]:", re.M)
REF = re.compile(r"\[\^(\d+)\](?!:)")
HEAD = re.compile(r"^#{1,6}\s", re.M)
IMG = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def split_body_defs(md: str) -> tuple[str, str]:
    """Separa el cuerpo del bloque FINAL contiguo de definiciones de nota `[^N]:`.

    Recorre desde el final saltando líneas en blanco; mientras encuentre defs las incluye
    en el bloque; se detiene en la primera línea de cuerpo (no-def, no-blanca).
    """
    lines = md.split("\n")
    split = len(lines)
    for k in range(len(lines) - 1, -1, -1):
        s = lines[k].strip()
        if s == "":
            continue
        if FNDEF.match(lines[k]):
            split = k
            continue
        break
    body = "\n".join(lines[:split]).rstrip()
    defs = "\n".join(lines[split:]).strip()
    return body, defs


def chunk_paragraphs(text: str, max_words: int) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    chunks, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > max_words:
            chunks.append("\n\n".join(cur)); cur, n = [], 0
        cur.append(p); n += w
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


DEFLINE = re.compile(r"^\[\^\d+\]:")


def chunk_defs(text: str, max_words: int) -> list[str]:
    """Trocea el bloque FINAL de definiciones de nota agrupando definiciones ENTERAS.

    Las defs `[^N]:` van una por línea SIN línea en blanco entre sí, así que
    `chunk_paragraphs` las vería como un único párrafo gigante y agy/Gemini trunca su
    salida (medido: ~190 de 304 defs en Brennan cap. 4). Aquí cada definición empieza en
    `[^N]:` y sigue hasta la próxima (soporta defs de varias líneas); se agrupan en trozos
    de <= max_words conservando el formato una-por-línea.
    """
    lines = text.split("\n")
    defs, cur = [], []
    for ln in lines:
        if DEFLINE.match(ln) and cur:
            defs.append("\n".join(cur)); cur = [ln]
        else:
            cur.append(ln)
    if cur:
        defs.append("\n".join(cur))
    chunks, buf, n = [], [], 0
    for d in defs:
        w = len(d.split())
        if buf and n + w > max_words:
            chunks.append("\n".join(buf)); buf, n = [], 0
        buf.append(d); n += w
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def translate_chunk(text: str, prompt: str, glos_name: str, workdir: Path, model: str, agy_bin: str, idx: int) -> str:
    src = workdir / f"_tr_src_{idx:03d}.md"
    src.write_text(text, encoding="utf-8")
    full = (f"{prompt}\nLee {glos_name} (terminología obligatoria) y traduce al español el "
            f"siguiente markdown. Devuelve SOLO el markdown traducido, sin comentarios ni preámbulo, "
            f"conservando [^N], encabezados (# Book N → # Libro N), referencias [*Abbr.* …]/[al-Qabīsī …] "
            f"verbatim, figuras ![..](..) y transliteraciones en cursiva:\n\n{text}")
    r = sh([agy_bin, "-p", full, "--model", model, "--add-dir", str(workdir), "--dangerously-skip-permissions"])
    src.unlink(missing_ok=True)
    return r.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Traduce un markdown con agy/Gemini, troceando, con QA.")
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glosario", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, default=Path("_work"))
    ap.add_argument("--chunk-words", type=int, default=1800)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--model", default="Gemini 3.1 Pro (High)")
    ap.add_argument("--agy-bin", default="/home/chris/.local/bin/agy")
    args = ap.parse_args()

    md = args.src.read_text(encoding="utf-8")
    args.workdir.mkdir(parents=True, exist_ok=True)
    # el glosario debe estar accesible bajo workdir
    glos_local = args.workdir / args.glosario.name
    if not glos_local.exists() or glos_local.resolve() != args.glosario.resolve():
        glos_local.write_text(args.glosario.read_text(encoding="utf-8"), encoding="utf-8")
    prompt = args.prompt.read_text(encoding="utf-8")

    body, defs = split_body_defs(md)
    chunks = chunk_paragraphs(body, args.chunk_words)
    if defs:
        chunks_defs = chunk_defs(defs, args.chunk_words)
    else:
        chunks_defs = []
    print(f"[traducción] {args.src.name}: {len(chunks)} trozos de cuerpo + {len(chunks_defs)} de notas")

    all_chunks = chunks + chunks_defs
    results = [None] * len(all_chunks)
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {ex.submit(translate_chunk, c, prompt, args.glosario.name, args.workdir,
                          args.model, args.agy_bin, i): i for i, c in enumerate(all_chunks)}
        for fu in futs:
            i = futs[fu]
            results[i] = fu.result()

    body_es = "\n\n".join(results[:len(chunks)]).strip()
    defs_es = "\n".join(results[len(chunks):]).strip()
    out = body_es + ("\n\n" + defs_es if defs_es else "") + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")

    # QA estructural EN vs ES
    def refset(t): return set(REF.findall(t))
    def defset(t): return set(FNDEF.findall(t))
    en_refs, es_refs = refset(md), refset(out)
    en_defs, es_defs = defset(md), defset(out)
    en_h, es_h = len(HEAD.findall(md)), len(HEAD.findall(out))
    en_img, es_img = len(IMG.findall(md)), len(IMG.findall(out))
    ratio = len(out.split()) / max(1, len(md.split()))
    resid = len(re.findall(r"\b(the|and|of|with|which|would|planet|degree)\b", body_es))
    print(f"OK  {args.out}")
    print(f"    notas EN refs/defs={len(en_refs)}/{len(en_defs)}  ES refs/defs={len(es_refs)}/{len(es_defs)}"
          f"  {'✓' if es_refs==en_refs and es_defs==en_defs else '⚠ DESAJUSTE'}")
    print(f"    encabezados EN/ES={en_h}/{es_h}  figuras EN/ES={en_img}/{es_img}  ratio ES/EN={ratio:.2f}")
    if resid > 3:
        print(f"    ⚠ posibles restos en inglés en el cuerpo (~{resid} palabras función) → revisar")
    if es_refs != en_refs or es_defs != en_defs or en_h != es_h or en_img != es_img:
        print("    → ACCIÓN: revisar desajustes estructurales.")


if __name__ == "__main__":
    main()
