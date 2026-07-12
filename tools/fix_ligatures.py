#!/usr/bin/env python3
"""
fix_ligatures.py — Repara la corrupción de LIGADURAS típica de PDF de editoriales
académicas (OUP/Distiller y similares), donde fi/ff/fl/ffi/ffl se extrajeron como
las MAYÚSCULAS W/V/X/Y/Z.

    conWrmation → confirmation      inXuence → influence      oYce → office
    aVair       → affair            Xour     → flour

El problema es venenoso porque el resultado es ASCII válido: "conWrmation" parece
una errata, no una palabra rota, y un corrector ortográfico normal no lo detecta.

GUARDA DE DICCIONARIO + PROTECCIÓN DE NOMBRES PROPIOS
-----------------------------------------------------
Solo expande cuando la expansión es una palabra REAL del diccionario, para no
tocar palabras legítimas con esas mayúsculas (While, Zoroaster, York, Yahweh) ni
—crucial— NOMBRES PROPIOS en CamelCase con W/V/X/Y/Z interna (LaVey, RavenWolf,
McVey, DeWitt): expandirlos daría "Laffey", "Ravenfiolf"… La regla: un token
CAPITALIZADO cuya expansión NO está en el diccionario se deja intacto.

Diccionarios: /usr/share/dict/british-english y american-english (apt: wamerican
wbritish). Sin diccionario, el script avisa y no toca nada (fail-safe).

Uso:
    python3 fix_ligatures.py cap.md [cap2.md ...]        # in situ
    python3 fix_ligatures.py cap.md --report             # solo reporta, no escribe
    python3 fix_ligatures.py cap.md --out cap.fixed.md   # a otro archivo
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

LIG = {"W": "fi", "V": "ff", "X": "fl", "Y": "ffi", "Z": "ffl"}
DICT_PATHS = ["/usr/share/dict/british-english", "/usr/share/dict/american-english"]
TOKEN = re.compile(r"[A-Za-z][A-Za-z'’]*")


def load_words() -> set[str]:
    words: set[str] = set()
    for p in DICT_PATHS:
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                words |= {w.strip().lower() for w in fh}
        except FileNotFoundError:
            pass
    return words


def _expand(tok: str) -> str:
    return "".join(LIG.get(c, c) for c in tok)


def make_fixer(words: set[str]):
    def in_dict(w: str) -> bool:
        return w.lower().strip("'’") in words

    def fix_token(tok: str) -> tuple[str, bool]:
        if not any(c in LIG for c in tok):
            return tok, False
        if tok.isupper() and len(tok) > 1:            # ACRÓNIMO/versalita: dejar
            return tok, False
        cand = _expand(tok)
        if cand == tok:
            return tok, False
        # 1) mayúscula-ligadura a MITAD de palabra (precedida de minúscula): señal
        #    inequívoca; expande si la expansión es palabra real (also oVer→offer).
        if re.search(r"[a-z][WVXYZ]", tok) and in_dict(cand):
            return cand, True
        # 2) mayúscula-ligadura inicial de palabra: expande solo si el original NO
        #    es palabra y la expansión SÍ (protege While, Zoroaster, Yet, York…).
        if in_dict(cand) and not in_dict(tok):
            return cand, True
        # 3) ligadura interna que el diccionario no conoce (inflexiones/latín),
        #    PERO nunca en un token capitalizado: eso sería un nombre propio
        #    CamelCase (LaVey, RavenWolf) y expandirlo lo destruiría.
        if (re.search(r"[a-z][WVXYZ][a-z]", tok)
                and not in_dict(tok) and not tok[0].isupper()):
            return cand, True
        return tok, False

    return fix_token


def process(text: str, fix_token):
    n = 0
    samples: list[str] = []

    def repl(m: re.Match[str]) -> str:
        nonlocal n
        fixed, changed = fix_token(m.group(0))
        if changed:
            n += 1
            if len(samples) < 30:
                samples.append(f"{m.group(0)} → {fixed}")
        return fixed

    return TOKEN.sub(repl, text), n, samples


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--report", action="store_true", help="solo reporta, no escribe")
    ap.add_argument("--out", type=Path, help="escribe a este archivo (solo 1 entrada)")
    args = ap.parse_args()

    words = load_words()
    if not words:
        sys.exit("error: no hay diccionario (apt install wbritish wamerican). "
                 "Sin diccionario no se corrige nada por seguridad.")
    fix_token = make_fixer(words)

    total = 0
    for path in args.files:
        text = path.read_text(encoding="utf-8")
        out, n, samples = process(text, fix_token)
        total += n
        dst = args.out or path
        if not args.report:
            dst.write_text(out, encoding="utf-8")
        print(f"{path.name}: {n} ligadura(s) corregida(s)")
        if args.report:
            for s in samples:
                print(f"    {s}")
    if len(args.files) > 1:
        print(f"— total: {total} —")
    return 0


if __name__ == "__main__":
    sys.exit(main())
