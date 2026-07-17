#!/usr/bin/env python3
"""ocr_spellfix.py — corrección ortográfica CONSERVADORA de erratas de OCR.

El problema de un spellcheck normal (aspell, etc.) en textos académicos y
multilingües: «corrige» transliteraciones válidas (Hōroskopos→«Horoscopes»,
zōidion→basura), nombres propios y latín, y su primera sugerencia suele fallar
(Bosk→«Bask» en vez de «Book»).  Eso DEGRADA el texto.

Idea central: usar **el propio libro como modelo de frecuencia**.  Una palabra
que aparece muchas veces en el corpus (aunque no esté en el diccionario) es
correcta —así se protegen las transliteraciones y los términos de dominio— y es
además un buen *destino* de corrección (Bosk/boks → «book», que sale mil veces).

Algoritmo (estilo Norvig, pero el «modelo de lenguaje» es el corpus + un
diccionario base):

  KNOWN = palabras del diccionario del sistema  ∪  palabras que aparecen ≥ `--min`
          veces en el corpus (por defecto 3).
  Una palabra es SOSPECHOSA si NO está en KNOWN.  Para ella se generan candidatos
  a distancia de edición ≤ 2 que SÍ estén en KNOWN, y se elige el de mayor
  frecuencia EN EL CORPUS.  Solo se corrige si además:
    · la palabra original es rara (< `--min` en el corpus),
    · no es toda mayúsculas (siglas/acrónimos: T, P, CCAG…),
    · no lleva caracteres no-ASCII (ō, ā… → transliteración),
    · el candidato es claramente más frecuente.
  Se preserva la capitalización.  Todo lo dudoso se REPORTA, no se toca.

Uso:
  python3 ocr_spellfix.py libro/*.md               # dry-run: lista los cambios
  python3 ocr_spellfix.py libro/*.md --apply       # escribe
  python3 ocr_spellfix.py libro/*.md --min 4 --max-edits 1
El corpus = TODOS los archivos pasados (pásalos juntos para un modelo mejor).
"""
from __future__ import annotations
import argparse, re, sys
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[A-Za-z]+")
ALPHA = "abcdefghijklmnopqrstuvwxyz"


def load_dict() -> set[str]:
    for p in ("/usr/share/dict/words", "/usr/share/dict/american-english"):
        f = Path(p)
        if f.is_file():
            return {w.strip().lower() for w in f.read_text(errors="ignore").splitlines()
                    if w.strip() and "'" not in w}
    return set()


def edits1(w: str) -> set[str]:
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    dels = [a + b[1:] for a, b in splits if b]
    trans = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
    reps = [a + c + b[1:] for a, b in splits if b for c in ALPHA]
    ins = [a + c + b for a, b in splits for c in ALPHA]
    return set(dels + trans + reps + ins)


def edits2(w: str) -> set[str]:
    return {e2 for e1 in edits1(w) for e2 in edits1(e1)}


def match_case(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


class Fixer:
    """Corrector CONSERVADOR.  Reglas de seguridad (para NO degradar nombres
    propios, latín ni transliteraciones):
      · solo corrige a un destino MUY COMÚN en el corpus (freq ≥ `common`),
      · prioriza distancia de edición 1 sobre 2 (cercanía antes que frecuencia),
      · edición 2 solo para palabras en minúscula y destino muy común,
      · palabra ORIGINAL capitalizada (posible nombre) → exige destino aún más
        común (× `--cap-factor`),  y nunca toca no-ASCII, MAYÚSCULAS o ≤3 letras.
    """
    def __init__(self, corpus_text: str, min_freq: int, max_edits: int,
                 common: int = 8, cap_factor: int = 2):
        self.freq = Counter(w.lower() for w in WORD.findall(corpus_text))
        self.dict = load_dict()
        self.min = min_freq
        self.max_edits = max_edits
        self.common = common
        self.cap_factor = cap_factor
        self.known = set(self.dict) | {w for w, c in self.freq.items() if c >= min_freq}
        self._cache: dict = {}

    def _common(self, cands):
        # candidato aceptable = palabra conocida Y frecuente en el corpus
        return {w for w in cands if w in self.known and self.freq.get(w, 0) >= 1}

    def correction(self, wl: str, allow_e2: bool):
        key = (wl, allow_e2)
        if key in self._cache:
            return self._cache[key]
        e1 = self._common(edits1(wl))
        best = max(e1, key=lambda c: (self.freq.get(c, 0), c in self.dict, len(c)), default=None)
        if best is None and allow_e2 and 4 <= len(wl) <= 12:
            e2 = self._common(edits2(wl))
            best = max(e2, key=lambda c: (self.freq.get(c, 0), c in self.dict, len(c)), default=None)
        self._cache[key] = best
        return best

    def protected(self, w: str) -> bool:
        wl = w.lower()
        if wl in self.known: return True               # ya es palabra buena
        if any(ord(c) > 127 for c in w): return True    # ō, ā… → transliteración
        if w.isupper() or len(w) <= 3: return True       # siglas/acrónimos, muy corta
        if self.freq.get(wl, 0) >= self.min: return True # aparece a menudo → correcta
        return False

    def fix_text(self, text: str, changes: list) -> str:
        def repl(m):
            w = m.group(0)
            if self.protected(w):
                return w
            cap = w[:1].isupper()
            best = self.correction(w.lower(), allow_e2=not cap)   # e2 solo en minúscula
            if not best or best == w.lower():
                return w
            thresh = self.common * (self.cap_factor if cap else 1)
            if self.freq.get(best, 0) < thresh:            # destino no lo bastante común → no tocar
                return w
            out = match_case(w, best)
            changes.append((w, out))
            return out
        lines = []
        for ln in text.split("\n"):
            if ln.lstrip().startswith(("|", "```", "###")):
                lines.append(ln); continue
            lines.append(WORD.sub(repl, ln))
        return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe los cambios (def: dry-run)")
    ap.add_argument("--min", type=int, default=3, help="frecuencia mínima en corpus para 'palabra buena' (def 3)")
    ap.add_argument("--max-edits", type=int, default=1, help="distancia de edición máxima (1=seguro por defecto; 2=agresivo, arriesga latín/árabe/fragmentos)")
    ap.add_argument("--common", type=int, default=8, help="frecuencia mínima del DESTINO de corrección (def 8)")
    ap.add_argument("--cap-factor", type=int, default=2, help="factor extra de frecuencia si el original va capitalizado (def 2)")
    args = ap.parse_args()

    corpus = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in args.files)
    fx = Fixer(corpus, args.min, args.max_edits, args.common, args.cap_factor)

    grand = Counter()
    for f in args.files:
        ch = []
        new = fx.fix_text(f.read_text(encoding="utf-8"), ch)
        if ch:
            print(f"\n{f.name}: {len(ch)} cambio(s)")
            c = Counter((a, b) for a, b in ch)
            for (a, b), n in c.most_common(80):
                print(f"   «{a}» → «{b}»" + (f"  ×{n}" if n > 1 else ""))
            grand.update(b for _, b in ch)
        if args.apply and ch:
            f.write_text(new, encoding="utf-8")
    print(f"\n{'APLICADOS' if args.apply else 'DRY-RUN'}: {sum(grand.values())} correcciones. "
          "Revisa la lista: es conservador, pero verifica los nombres propios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
