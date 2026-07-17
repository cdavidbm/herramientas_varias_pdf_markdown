#!/usr/bin/env python3
"""flag_ocr_artifacts.py — DETECTA (no corrige) ruido de OCR camuflado en markdown.

Pensado para localizar rápido los defectos finos que una conversión OCR deja y que
son fáciles de pasar por alto, para que el AGENTE los corrija A MANO, con criterio,
contra la imagen.  NO toca el texto: solo reporta `archivo:línea` + fragmento.  La
decisión (¿es basura?, ¿qué palabra es?, ¿se une el párrafo?) la toma el humano/agente
—esta obra es un diccionario de astrología: hay términos árabes/latín/griego, nombres
propios y tecnicismos que NINGÚN corrector automático debe tocar—.

Marca:
  [garbage]   línea de basura pura (racha de tokens sin sentido: «010 OQ Fo vio…»).
  [glued]     entrada de glosario pegada a otra o a basura («… . house: oikos. …»
              sin negrita al inicio).
  [split]     párrafo cortado por salto de página y sin unir (acaba a media frase y
              el siguiente empieza en minúscula).
  [dash]      guion espurio al inicio de párrafo («- such a manner…»).
  [bracket]   corchete/paréntesis colgando o sin pareja en la línea.
  [pagenum]   nº de página incrustado (párrafo que empieza con «35 texto…»).
  [stray]     cola de basura corta pegada a una frase («… by Ptolemy. ] Bt»).

Uso:  python3 flag_ocr_artifacts.py libro/*.md
      python3 flag_ocr_artifacts.py libro/*.md --only glued,split
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

ENTRY = re.compile(r"[a-z][a-z ()',-]{2,40}?:\s+[a-zāēīōūáéíóú]")   # «headword: greek»


def _noise(t):
    """Token de RUIDO de OCR — NO cuenta como ruido una palabra normal ni un nombre
    propio Capitalizado (Ptolemy, Robert) ni «I»/«a»."""
    t = t.strip(".,;:!?()[]'\"")
    if not t or t in ("I", "a", "A"):
        return False
    if re.fullmatch(r"[A-Z][a-z']+", t):          # nombre propio / palabra Capitalizada
        return False
    if re.fullmatch(r"[a-z]{2,}", t):              # palabra minúscula normal
        return False
    if len(t) == 1:
        return True
    if re.fullmatch(r"[A-Z]{2,}", t):              # MAYÚS (EEEE, SERAEES)
        return True
    if re.search(r"[a-z][A-Z]|[A-Z][a-z]*[A-Z]", t):   # mezcla de caja rara
        return True
    if re.fullmatch(r"[^A-Za-z]+", t):             # solo dígitos/símbolos
        return True
    return False


def is_garbage(s):
    s = s.strip()
    if not s or s.startswith(("|", "#", "**", "> ", "[^", "*")):
        return False
    toks = s.split()
    run = maxrun = noise = 0
    for t in toks:
        n = _noise(t)
        noise += n
        run = run + 1 if n else 0
        maxrun = max(maxrun, run)
    # ≥4 tokens-ruido SEGUIDOS, o >40 % de la línea es ruido (con ≥6 tokens)
    return maxrun >= 4 or (len(toks) >= 6 and noise > len(toks) * 0.4)


def check(files, only):
    hits = []
    def want(k): return not only or k in only
    for f in files:
        blocks = f.read_text(encoding="utf-8").split("\n\n")
        for i, b in enumerate(blocks):
            s = b.strip()
            if not s:
                continue
            body = not s.startswith(("#", "|", "**", "> ", "[^", "*", "- "))
            if want("garbage") and is_garbage(s):
                hits.append((f.name, "garbage", s[:80]))
            if want("dash") and re.match(r"^- [a-z]", s):
                hits.append((f.name, "dash", s[:60]))
            if want("pagenum") and re.match(r"^(1?\d{1,2}) [a-z]", s) and not s[0] == "0":
                hits.append((f.name, "pagenum", s[:60]))
            if want("bracket") and re.search(r"(^|\s)[\]\[)(]\s*$", s) and s[0] not in "#|":
                hits.append((f.name, "bracket", "…" + s[-45:]))
            if want("stray") and re.search(r"[.?!”\"']\s+[\]\[)(]?\s?[A-Z][a-z]?\s*$", s) and len(s.split()[-1]) <= 3:
                hits.append((f.name, "stray", "…" + s[-40:]))
            if want("glued"):
                # entrada de glosario «headword: greek» a MEDIA línea (precedida de
                # fin de frase) → está pegada a la entrada anterior o a basura
                for m in ENTRY.finditer(s):
                    if m.start() >= 2 and s[m.start()-2:m.start()] in (". ", "' ", "’ ", "— ", "] "):
                        hits.append((f.name, "glued", "…" + s[max(0, m.start()-2):m.start()+30])); break
            if want("split") and body and i + 1 < len(blocks):
                nxt = blocks[i+1].strip()
                if (not re.search(r'[.?!:;"”)\]]$', s) and nxt[:1].islower()
                        and not nxt.startswith(("|", "#", "*", "-"))):
                    hits.append((f.name, "split", "…" + s[-32:] + " ¶ " + nxt[:32] + "…"))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--only", default="", help="filtra tipos: garbage,glued,split,dash,bracket,pagenum,stray")
    args = ap.parse_args()
    only = set(x.strip() for x in args.only.split(",") if x.strip())
    hits = check(args.files, only)
    from collections import Counter
    by = Counter(k for _, k, _ in hits)
    for name, kind, snip in hits:
        print(f"[{kind:8}] {name}: {snip}")
    print(f"\nTOTAL: {len(hits)} marcas  ({', '.join(f'{k}={n}' for k,n in by.most_common())})")
    print("→ Revisa cada una A MANO contra la imagen; no es un corrector automático.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
