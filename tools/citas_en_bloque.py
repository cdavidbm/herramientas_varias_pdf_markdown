#!/usr/bin/env python3
"""citas_en_bloque.py — convierte en `>` los párrafos que son una CITA ENTERA, y
pega las llamadas de nota a la palabra anterior.

Un converter (de EPUB, de PDF) saca las citas largas como párrafos normales que
abren y cierran con comillas, porque la maqueta las distinguía solo por la
sangría y esa señal se pierde. El markdown se lee, pero **una cita de cinco
renglones es indistinguible de la prosa del autor**, que es justo lo que el
lector necesita ver de un vistazo. Aquí se marcan como bloque y se les quitan las
comillas que las envuelven (el bloque ya dice que es cita; dejar ambas cosas es
redundante y feo). Las comillas INTERIORES se respetan.

Sabe tres cosas que un `sed` no sabe:

* **Citas de varios párrafos.** La comilla de cierre puede estar tres párrafos
  más abajo; los intermedios no abren comilla y son cita igual. Además, entre dos
  bloques `>` separados por un renglón EN BLANCO, pandoc ve DOS citas distintas:
  el separador de una cita continuada tiene que llevar su propio `>`.
* **Cita que cierra a media línea.** Muchas maquetas pegan al final de la cita la
  frase de transición del autor («…living Images."[^45] Agrippa goes on to note
  that…»). Ahí hay que PARTIR el párrafo, o la voz del autor queda dentro de la
  cita.
* **Llamadas de nota.** `imágenes [^1]` va sin espacio, y un punto detrás de la
  llamada cuando la frase ya cerró con `."` es espurio.

Con `--comillas` normaliza además las rectas a tipográficas (“ ”, ’) y `...` a `…`.

**Trampa medida** (y por la que existe la prueba correspondiente): un regex
`^(#+ .*?)\\s*:\\s*$` en modo multilínea **se come el renglón en blanco de
después** y pega el encabezado al párrafo — `\\s` incluye `\\n`. Hay que anclar
con `[ \\t]*`.

Uso:
    python3 citas_en_bloque.py ./markdown/*.md            # dry-run, informa
    python3 citas_en_bloque.py ./markdown/*.md --apply
    python3 citas_en_bloque.py cap.md --apply --comillas  # + tipografía
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

QUOTE_OPEN = re.compile(r'^\s*["“]')
# Cierre de cita al FINAL: comilla + opcional llamada + opcional puntuación.
QUOTE_CLOSE_END = re.compile(r'["”]\s*(\[\^[^\]]+\])?\s*[.,]?\s*$')
# Cierre EN MEDIO con prosa del autor detrás (empieza en mayúscula).
QUOTE_CLOSE_MID = re.compile(r'["”]\s*(\[\^[^\]]+\])?\s+(?=[A-ZÁÉÍÓÚÑ])')
NO_PROSE = ("#", "[^", "!", "---", ">", "|", "- ", "* ", "1.")


def blocks(text: str) -> list[str]:
    """Trocea en bloques separados por renglón en blanco, conservando el orden."""
    out: list[str] = []
    cur: list[str] = []
    for ln in text.split("\n"):
        if ln.strip() == "":
            if cur:
                out.append("\n".join(cur))
                cur = []
            out.append("")
        else:
            cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def is_prose(b: str) -> bool:
    s = b.strip()
    return bool(s) and not s.startswith(NO_PROSE)


def strip_wrapping_quotes(s: str) -> str:
    """Quita SOLO las comillas que envuelven la cita, no las interiores."""
    s = re.sub(r'^\s*["“]\s*', "", s)
    s = re.sub(r'["”](\s*\[\^[^\]]+\])?\s*([.,])?\s*$',
               lambda m: (m.group(1) or "") + (m.group(2) or ""), s)
    return s.strip()


def curl_quotes(text: str) -> str:
    """Comillas rectas → tipográficas, alternando abre/cierra dentro de cada línea."""
    out = []
    for ln in text.split("\n"):
        opening = True
        res = []
        for ch in ln:
            if ch == '"':
                res.append("“" if opening else "”")
                opening = not opening
            else:
                res.append(ch)
        out.append("".join(res))
    return "\n".join(out)


def process(text: str) -> tuple[str, dict[str, int]]:
    stats = {"cita": 0, "cita_multiparrafo": 0, "cita_partida": 0}
    out: list[str] = []
    in_quote = False
    for b in blocks(text):
        if not is_prose(b):
            if b.strip():
                in_quote = False
            out.append(b)
            continue
        s = b.strip()

        if in_quote:
            closes = bool(QUOTE_CLOSE_END.search(s))
            body = strip_wrapping_quotes(s) if closes else s
            # Sin `>` en el separador, pandoc parte la cita en dos.
            if len(out) > 1 and out[-1] == "" and out[-2].startswith(">"):
                out[-1] = ">"
            out.append("> " + body)
            stats["cita_multiparrafo"] += 1
            if closes:
                in_quote = False
            continue

        if QUOTE_OPEN.match(s):
            mid = QUOTE_CLOSE_MID.search(s)
            ends = QUOTE_CLOSE_END.search(s)
            if mid and not (ends and mid.start() >= ends.start()):
                cut = mid.end()
                out.append("> " + strip_wrapping_quotes(s[:cut].strip()))
                out.append("")
                out.append(s[cut:].strip())
                stats["cita_partida"] += 1
                continue
            if ends:
                out.append("> " + strip_wrapping_quotes(s))
                stats["cita"] += 1
            else:
                out.append("> " + re.sub(r'^\s*["“]\s*', "", s))
                stats["cita"] += 1
                in_quote = True
            continue
        out.append(b)
    return "\n".join(out), stats


def glue_footnotes(text: str) -> tuple[str, int]:
    """La llamada de nota se pega a lo anterior; un punto detrás de ella sobra."""
    n = len(re.findall(r'(?m)(\S)[ \t]+(\[\^[^\]]+\])', text))
    text = re.sub(r'(?m)(\S)[ \t]+(\[\^[^\]]+\])', r'\1\2', text)
    text = re.sub(r'([.!?"”])(\[\^[^\]]+\])\.(\s)', r'\1\2\3', text)
    return text, n


def fix_headings(text: str) -> str:
    # `\s*$` en multilínea SE COME el renglón en blanco siguiente: anclar [ \t]*.
    text = re.sub(r'(?m)^(#+ .*?)[ \t]*:[ \t]*$', r'\1', text)
    # Y por si ya venía pegado, restituir el renglón en blanco.
    return re.sub(r'(?m)^(#+ .+)\n(?=[^\n])', r'\1\n\n', text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    ap.add_argument("--comillas", action="store_true",
                    help="normaliza comillas rectas a “ ”, apóstrofos a ’ y ... a …")
    ap.add_argument("--no-notas", action="store_true",
                    help="no tocar el espacio de las llamadas [^N]")
    args = ap.parse_args()

    total = {"cita": 0, "cita_multiparrafo": 0, "cita_partida": 0, "notas": 0}
    tocados = 0
    for f in args.files:
        if not f.is_file():
            print(f"warning: no existe {f}", file=sys.stderr)
            continue
        orig = f.read_text(encoding="utf-8")
        t, st = process(orig)
        if not args.no_notas:
            t, n = glue_footnotes(t)
            total["notas"] += n
        t = fix_headings(t)
        if args.comillas:
            t = t.replace("...", "…")
            t = re.sub(r"(\w)'(\w)", r"\1’\2", t)
            t = curl_quotes(t)
        t = re.sub(r"\n{3,}", "\n\n", t).rstrip() + "\n"
        for k in st:
            total[k] += st[k]
        if t != orig:
            tocados += 1
            if args.apply:
                f.write_text(t, encoding="utf-8")
            print(f"  {'escrito ' if args.apply else 'cambiaría'} {f.name}: "
                  f"{st['cita']} cita(s), {st['cita_multiparrafo']} continuación(es), "
                  f"{st['cita_partida']} partida(s)")

    print(f"\n{'APLICADO' if args.apply else 'DRY-RUN'} — {tocados} archivo(s); "
          f"{total['cita']} citas en bloque, {total['cita_partida']} partidas, "
          f"{total['notas']} llamadas pegadas")
    if not args.apply and tocados:
        print("Revisa la lista y vuelve a lanzarlo con --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
