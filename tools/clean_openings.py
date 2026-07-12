#!/usr/bin/env python3
"""
clean_openings.py — Limpia la BASURA DE APERTURA de capítulo que dejan muchos PDF
maquetados con tipografía de display:

  1. Portadilla revuelta: el rótulo "CHAPTER ONE" y el título en versalitas salen
     descolocados por la letra decorativa, p. ej.:
         # 1. Ancient and Medieval Grimoires
         APTER ONE          ← "CH" + "APTER ONE" descolocado
         CH
         ANCIENT AND MEDIEVAL
         GRIMOIRES
         The modern history…   ← aquí empieza el cuerpo real
  2. Capitular (drop cap) partida: la mayúscula inicial del cuerpo queda separada:
         "T he modern…" → "The modern…"   "W e saw…" → "We saw…"
  3. Primera línea del párrafo 1 huérfana (separada por línea en blanco de su
     continuación): se vuelve a unir.

Estrategia: tras el `# H1`, el CUERPO empieza en la primera línea que casa
`^[A-Z] [a-z]` (mayúscula sola + espacio + minúscula = capitular partida). Todo lo
anterior (fragmentos y versalitas, que el H1 ya representa) se descarta. NO toca
el H1 ni nada por debajo del inicio del cuerpo salvo unir la capitular y su
párrafo huérfano.

Pensado para prosa a una columna (bisturí). Si un capítulo NO tiene capitular
partida (p. ej. el cuerpo empieza con "Much has been…"), se deja intacto y se
avisa. Uso:

    python3 clean_openings.py cap.md [cap2.md ...]      # in situ
    python3 clean_openings.py cap.md --report            # muestra qué haría
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

DROP = re.compile(r"^([A-Z]) (?=[a-z])")


def clean(text: str) -> tuple[str, str | None]:
    lines = text.split("\n")
    if not lines or not lines[0].startswith("#"):
        return text, "sin H1 al inicio; no se toca"
    h1 = lines[0]
    body_i = None
    for i in range(1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if re.match(r"^[A-Z] [a-z]", lines[i]):     # capitular partida → inicio del cuerpo
            body_i = i
            break
        # GUARDA: si aparece PROSA (una palabra en minúscula de 4+ letras) antes de
        # hallar la capitular, el capítulo ya está limpio (no hay portadilla): abortar.
        # Las líneas de portadilla legítimas son versalitas/fragmentos (sin minúsculas).
        if re.search(r"[a-zàáéíóúüñ]{4,}", s):
            return text, "ya limpio (prosa antes de cualquier capitular); no se toca"
    if body_i is None:
        return text, "no se detecta capitular partida; no se toca"

    body = lines[body_i:]
    body[0] = DROP.sub(r"\1", body[0])                 # unir capitular
    out = h1 + "\n\n" + "\n".join(body)

    # unir la primera línea del párrafo 1 con su continuación si quedó huérfana
    # (línea que acaba a media frase + \n\n + siguiente párrafo)
    parts = out.split("\n\n")
    if len(parts) >= 3 and re.search(r"[a-z,]$", parts[1].rstrip()):
        parts[1] = parts[1].rstrip() + " " + parts[2].lstrip()
        del parts[2]
        out = "\n\n".join(parts)

    dropped = body_i - 1
    return out, f"portadilla eliminada ({dropped} líneas), cuerpo → {body[0][:48]!r}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--report", action="store_true", help="muestra qué haría, no escribe")
    args = ap.parse_args()

    for path in args.files:
        text = path.read_text(encoding="utf-8")
        out, msg = clean(text)
        changed = out != text
        if changed and not args.report:
            path.write_text(out, encoding="utf-8")
        print(f"{path.name}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
