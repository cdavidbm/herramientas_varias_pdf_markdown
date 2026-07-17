#!/usr/bin/env python3
"""fix_roman_numerals.py — corrige numerales romanos corrompidos por el OCR.

El OCR confunde constantemente los romanos con letras/dígitos parecidos y con el
pronombre inglés «I»:  II→«IT/Il/I1/1I/ll/11»,  III→«IIL/Ill/111»,  IV→«1V/lV/TV»,
IX→«1X/lX»,  y el pronombre «I»→«T/l/|/1».  Ejemplos reales medidos:
  «In Volume IT T will publish» → «In Volume II I will publish»
  «the so-called Book of Aristotle» (ver ocr_spellfix.py para las palabras)

Hace DOS correcciones, ambas **con contexto** (nunca a ciegas):

  1. NUMERAL TRAS PALABRA-CONTADOR.  Detrás de Book/Volume/Chapter/Part/Vol./Bk./
     Ch./No./Tome/Section/Canto/Appendix/Book el token siguiente TIENE que ser un
     numeral romano → se coacciona al romano válido más cercano (IT→II, IIL→III,
     1V→IV…).  Alta confianza.

  2. PRONOMBRE «I».  Un token de 1 carácter «T/l/|» (o «1») que va seguido de un
     verbo/auxiliar de 1ª persona (will, am, have, think, publish, present…) →
     «I».  NO toca las SIGLAS de manuscrito (en estos libros «T reads», «P reads»,
     «B and E») porque exige un verbo que NO sea 3ª persona del singular: una sigla
     va con «reads/omits/has», un pronombre con «read/will/am/have…».

Determinista y conservador.  Por defecto **--dry-run** (lista los cambios); usa
`--apply` para escribir.  No toca romanos ya correctos ni texto entre ``` ` `` ni
tablas (`| … |`).
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

# --- romanos válidos 1..39 (cubre Book/Chapter/Volume realistas) ---
def _int_to_roman(n: int) -> str:
    vals = [(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s; n -= v
    return out
VALID_ROMAN = {_int_to_roman(n) for n in range(1, 40)}

COUNTER = r"(?:Book|Volume|Vol|Chapter|Chap|Ch|Part|Section|Sect|No|Tome|Canto|Appendix|Bk)"

# verbos/auxiliares que siguen al pronombre «I» (1ª persona) y NO a una sigla:
FIRST_PERSON = {
    "will","shall","would","could","should","can","may","might","must","am","have",
    "had","do","did","think","believe","present","publish","published","translate",
    "translated","wrote","write","note","noted","mean","meant","suggest","suggested",
    "use","used","see","saw","find","found","know","knew","hope","intend","intended",
    "want","wanted","give","gave","take","took","make","made","say","said","call",
    "called","read","consider","assume","argue","cannot","won","don","ll","ve","m",
}
# formas en 3ª persona → sugieren SIGLA («T reads»), no pronombre → NO convertir
THIRD_PERSON = {"reads","omits","has","says","gives","adds","reads","writes","notes","means"}


def coerce_roman(tok: str) -> str | None:
    """Devuelve el romano válido que representa `tok` corrupto, o None si no lo es."""
    if tok in VALID_ROMAN:
        return None                      # ya correcto
    if re.fullmatch(r"\d+", tok):
        return None                      # número arábigo legítimo (p. ej. «chapter 16»)
    if re.search(r"[A-Za-z][0-9]", tok):
        return None                      # dígito TRAS letras → ambiguo «II.9» vs «III»: no adivinar
    if not re.search(r"[IVXLTl|1!]", tok):
        return None                      # sin ningún carácter romano-izable
    s = tok.upper()
    # caracteres que el OCR confunde con «I»:  l  |  1  T  !  L(intrusa)
    c = (s.replace("L", "I").replace("|", "I").replace("T", "I")
          .replace("1", "I").replace("!", "I"))
    c = re.sub(r"[^IVX]", "", c)
    if c in VALID_ROMAN and c != tok:
        return c
    return None


def fix_line(line: str, changes: list) -> str:
    if line.lstrip().startswith("|") or line.lstrip().startswith("```"):
        return line                       # no tocar tablas ni bloques de código

    # 1) numeral tras palabra-contador
    def _counter(m):
        pre, tok = m.group(1), m.group(2)
        fixed = coerce_roman(tok)
        if fixed:
            changes.append((tok, fixed, f"tras «{pre.strip()}»"))
            return f"{pre}{fixed}"
        return m.group(0)
    line = re.sub(rf"\b({COUNTER}\.?\s+)([A-Za-z0-9|!]{{1,5}})\b", _counter, line)

    # 2) pronombre «I» corrompido: token de 1 char T/l/| (no '1' para evitar cifras)
    #    seguido de verbo de 1ª persona.
    def _pron(m):
        pre, tok, sp, nxt = m.group(1), m.group(2), m.group(3), m.group(4)
        if nxt.lower() in THIRD_PERSON:
            return m.group(0)             # «T reads» = sigla → no tocar
        if nxt.lower() in FIRST_PERSON:
            changes.append((tok, "I", f"pronombre ante «{nxt}»"))
            return f"{pre}I{sp}{nxt}"
        return m.group(0)
    line = re.sub(r"(^|[\s(])([Tl|])(\s+)([A-Za-z']+)", _pron, line)
    return line


def process(text: str):
    changes = []
    out = [fix_line(ln, changes) for ln in text.split("\n")]
    return "\n".join(out), changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe los cambios (por defecto: dry-run)")
    args = ap.parse_args()
    total = 0
    for f in args.files:
        new, ch = process(f.read_text(encoding="utf-8"))
        total += len(ch)
        if ch:
            print(f"\n{f.name}: {len(ch)} cambio(s)")
            for a, b, why in ch[:60]:
                print(f"   «{a}» → «{b}»   ({why})")
        if args.apply and ch:
            f.write_text(new, encoding="utf-8")
    print(f"\n{'APLICADOS' if args.apply else 'DRY-RUN'}: {total} cambios en {len(args.files)} archivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
