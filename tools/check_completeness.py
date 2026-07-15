#!/usr/bin/env python3
"""
check_completeness.py — Detecta (y opcionalmente REPARA) el TEXTO PERDIDO durante
la conversión de un PDF a markdown. Es la red de seguridad más importante de La
Forja: los bisturíes pueden dejar caer trozos de texto SIN AVISAR (años, cláusulas
enteras) según el layout, y eso es invisible salvo que compares contra una
referencia completa.

Cómo funciona
-------------
Extrae una referencia COMPLETA con `pdftotext -layout` (que preserva el flujo de
texto mejor que cualquier troceo) y la ALINEA (difflib) contra el markdown. Cada
tramo de la referencia que falta en el markdown = una laguna. Con --repair los
reinserta con mayúsculas/puntuación correctas (limpiando ligaduras y diacríticos
del tramo recuperado). Los tramos que además chocan con texto revuelto ('replace')
se reportan para revisión manual (p. ej. órdenes de lectura rotos por imágenes).

Uso
---
    # verificar un markdown contra su PDF de capítulo:
    python3 check_completeness.py cap.pdf cap.md
    # contra un rango de páginas de un PDF grande:
    python3 check_completeness.py libro.pdf sec.md --pages 304-320
    # reparar in situ (revisa el reporte antes):
    python3 check_completeness.py cap.pdf cap.md --repair
    # excluir un falso positivo (p. ej. front-matter que quitaste a propósito):
    python3 check_completeness.py intro.pdf intro.md --repair --exclude "left blank"

Sale con código 1 si encuentra lagunas (útil en scripts de QA); 0 si está completo.
"""
from __future__ import annotations
import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

LIG = {"W": "fi", "V": "ff", "X": "fl", "Y": "ffi", "Z": "ffl"}
_WORDS: set[str] = set()
for _p in ("/usr/share/dict/british-english", "/usr/share/dict/american-english"):
    try:
        _WORDS |= {w.strip().lower() for w in open(_p, encoding="utf-8", errors="ignore")}
    except FileNotFoundError:
        pass

ACUTE = dict(zip("aeiouAEIOU", "áéíóúÁÉÍÓÚ")); GRAVE = dict(zip("aeiouAEIOU", "àèìòùÀÈÌÒÙ"))
DIA = dict(zip("aeiouAEIOU", "äëïöüÄËÏÖÜ")); UML = {"o": "ö", "u": "ü", "a": "ä", "O": "Ö", "U": "Ü", "A": "Ä"}


def _expand(t: str) -> str:
    return "".join(LIG.get(c, c) for c in t)


def _fix_token(t: str) -> str:
    """Ligadura con guarda de diccionario (protege nombres propios CamelCase)."""
    if not any(c in LIG for c in t):
        return t
    cand = _expand(t)
    if cand == t:
        return t
    if re.search(r"[a-z][WVXYZ]", t) and cand.lower() in _WORDS:
        return cand
    if cand.lower() in _WORDS and t.lower() not in _WORDS:
        return cand
    if re.search(r"[a-z][WVXYZ][a-z]", t) and t.lower() not in _WORDS and not t[0].isupper():
        return cand
    return t


def clean_ref(text: str) -> str:
    """Limpia la referencia -layout: running-heads, guiones de corte, ligaduras,
    diacríticos — para que aline bien con el markdown ya limpio y el texto que se
    reinserte salga correcto."""
    keep = []
    for ln in text.split("\n"):
        s = ln.strip()
        if re.fullmatch(r"\d{1,3}", s):                 # nº de página suelto
            continue
        if re.search(r"\|\s*\d{1,3}\s*$", s) or re.match(r"^\d{1,3}\s*\|", s):
            continue                                     # running-head 'Título | 123'
        keep.append(ln)
    t = "\n".join(keep)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)         # des-guionar cortes de línea
    t = re.sub(r"[ \t]*\n[ \t]*", " ", t)               # aplanar a espacios
    t = re.sub(r"[A-Za-z][A-Za-z']*", lambda m: _fix_token(m.group(0)), t)
    t = re.sub(r"([aeiouAEIOU]) ?[´́]", lambda m: ACUTE[m.group(1)], t)
    t = re.sub(r"([aeiouAEIOU]) ?[`̀]", lambda m: GRAVE[m.group(1)], t)
    t = re.sub(r"([aeiouAEIOU]) ?[¨̈]", lambda m: DIA[m.group(1)], t)
    t = re.sub(r"€\s?([ouaOUA])", lambda m: UML[m.group(1)], t)
    t = re.sub(r" +", " ", t)
    return t


def toks(s: str):
    # `\w` Unicode: incluye griego, cirílico y letras acentuadas. Con el antiguo
    # [A-Za-z0-9] el texto no-ASCII era INVISIBLE a la verificación y un capítulo
    # entero en griego podía «faltar» sin que se detectara (falso ✅ sin lagunas).
    return [(m.group(0).lower(), m.start(), m.end())
            for m in re.finditer(r"[^\W_]+", s, re.UNICODE)]


def layout_text(pdf: Path, pages: str | None) -> str:
    cmd = ["pdftotext", "-layout"]
    if pages:
        a, _, b = pages.partition("-")
        cmd += ["-f", a, "-l", (b or a)]
    cmd += [str(pdf), "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    # Si pdftotext falla (PDF cifrado, dañado, binario ausente) devolvería stdout
    # vacío → difflib no vería «lagunas» → falso «✅ sin lagunas». Abortar claro.
    if r.returncode != 0:
        sys.stderr.write(
            f"ERROR: pdftotext falló (returncode={r.returncode}) sobre {pdf}\n"
            f"{r.stderr[:500]}\n"
            "  No se puede verificar la completitud: revisa el PDF (¿cifrado? "
            "¿dañado? ¿poppler instalado?).\n")
        raise SystemExit(2)
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path, help="PDF fuente (de capítulo o el grande)")
    ap.add_argument("md", type=Path, help="markdown a verificar")
    ap.add_argument("--pages", help="rango 1-based 'A-B' si el PDF es el libro grande")
    ap.add_argument("--min", type=int, default=4, help="mín. palabras de un tramo (def. 4)")
    ap.add_argument("--repair", action="store_true", help="reinserta los tramos perdidos")
    ap.add_argument("--exclude", action="append", default=[],
                    help="ignora tramos que contengan este texto (falsos positivos)")
    args = ap.parse_args()

    ref_str = clean_ref(layout_text(args.pdf, args.pages))
    cur_str = args.md.read_text(encoding="utf-8")
    rt, ct = toks(ref_str), toks(cur_str)
    sm = difflib.SequenceMatcher(None, [w for w, _, _ in rt], [w for w, _, _ in ct], autojunk=False)

    inserts, replaces = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        # (i2-i1)<min = tramo demasiado corto (ruido). El i1==0 se salta SOLO cuando
        # es corto (un título/encabezado que el md reformatea); si al principio del
        # capítulo faltan ≥15 palabras es pérdida real de texto y SÍ debe reportarse.
        if (i2 - i1) < args.min:
            continue
        if i1 == 0 and (i2 - i1) < 15:
            continue
        span = ref_str[rt[i1][1]:rt[i2 - 1][2]]
        if any(x in span for x in args.exclude):
            continue
        if tag == "delete":
            pos = ct[j1][1] if j1 < len(ct) else len(cur_str)
            inserts.append((pos, span))
        elif tag == "replace":
            replaces.append((span, " ".join(w for w, _, _ in ct[j1:j2])))

    name = args.md.name
    if not inserts and not replaces:
        print(f"✅ {name}: sin lagunas (ref={len(rt)} palabras de referencia, todas presentes)")
        return 0

    print(f"⚠️  {name}: {len(inserts)} tramo(s) perdido(s), "
          f"{len(replaces)} a revisar  (ref={len(rt)} vs md={len(ct)} palabras)")
    for pos, span in inserts:
        print(f"   + tras «…{cur_str[max(0,pos-45):pos].strip()}»  FALTA: {span[:90]!r}")
    for span, cur in replaces:
        print(f"   ~ revisar: md tiene «…{cur}…» donde el PDF dice «{span[:70]}…»")

    if args.repair and inserts:
        out = cur_str
        for pos, span in sorted(inserts, key=lambda x: -x[0]):
            out = out[:pos] + span.strip() + " " + out[pos:]
        out = re.sub(r"(\d)–\s+(\d)", r"\1–\2", out)     # rangos de años 1769– 1832
        out = re.sub(r"([a-z,])\n\n(\d)", r"\1 \2", out)  # unir año insertado tras \n\n
        out = re.sub(r"[ \t]{2,}", " ", out)
        args.md.write_text(out, encoding="utf-8")
        print(f"   ↳ reparado: {len(inserts)} tramo(s) reinsertado(s). "
              f"Revisa los 'replace' a mano si los hay.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
