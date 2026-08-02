#!/usr/bin/env python3
"""djvu_to_markdown.py — bisturí para libros en **DjVu** con capa de texto.

Primer formato DjVu de la suite. Un DjVu escaneado suele traer ya su OCR incrustado
(chunks `TXTz`), y `djvutxt` lo saca con la GEOMETRÍA de cada línea, que es justo lo
que hace falta para no entregar un bloque de texto por página:

  · **párrafos por SANGRÍA** — la primera línea de párrafo entra ~40 px; medido en
    Ficino, cuerpo a x≈155 y arranque de párrafo a x≈195-245. Sin esto el capítulo
    sale como un párrafo gigante, igual que en las maquetas eruditas de PDF.
  · **titulillos y folios por POSICIÓN** — van en la franja superior, separados del
    cuerpo por un hueco mayor que el interlineado.
  · **edición bilingüe a PÁGINAS ENFRENTADAS** (`--parity`) — verso en una lengua y
    recto en la otra. Es el caso fácil frente a las dos columnas de la misma página:
    se separa por paridad, que es determinista. **Verifica de qué lado cae cada
    lengua antes de fiarte**: el front matter desplaza la paridad, y un libro puede
    cambiarla a media obra (en Ficino lo hace en la página del *Sigla*).

Diagnóstico sin abrir el archivo (útil cuando falta djvulibre): la cabecera dice
páginas, tamaño y si hay capa de texto —
    python3 djvu_to_markdown.py x.djvu --info

Uso:
    python3 djvu_to_markdown.py x.djvu --info
    python3 djvu_to_markdown.py x.djvu --pages 110-415 --parity even --out la/
    python3 djvu_to_markdown.py x.djvu --pages 11-99 --out en/ --title "Introducción"

Requiere `djvulibre-bin` (`djvutxt`). Sin él, `--info` sigue funcionando.
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path

LINEA = re.compile(rb'\(line (\d+) (\d+) (\d+) (\d+)\s*"((?:[^"\\]|\\.)*)"', re.S)
PAGINA = re.compile(rb"\(page \d+ \d+ \d+ \d+")


def desescapa(b: bytes) -> str:
    """Los escapes de djvutxt son OCTALES sobre BYTES, no `unicode_escape`.

    Decodificarlos como texto rompe el UTF-8: un `—` (E2 80 94) sale como `â€"`.
    Hay que reconstruir los bytes y decodificar UTF-8 al final.
    """
    out = bytearray()
    i = 0
    while i < len(b):
        if b[i:i + 1] == b"\\" and i + 1 < len(b):
            c = b[i + 1:i + 2]
            if c.isdigit():
                j = i + 1
                while j < len(b) and b[j:j + 1].isdigit() and j - i <= 3:
                    j += 1
                out.append(int(b[i + 1:j], 8)); i = j; continue
            out += {b"n": b"\n", b"t": b"\t", b"r": b"\r"}.get(c, c); i += 2; continue
        out += b[i:i + 1]; i += 1
    return bytes(out).decode("utf-8", errors="replace")


def info(djvu: Path) -> dict:
    """Páginas, tamaño y presencia de capa de texto, leídos de la CABECERA."""
    d = djvu.read_bytes()
    i = d.find(b"DIRM")
    n = struct.unpack(">H", d[i + 9:i + 11])[0] if i > 0 else 0
    dims = {}
    j = 0
    while True:
        j = d.find(b"DJVUINFO", j)
        if j < 0:
            break
        b = d[j + 12:j + 22]
        w, h = struct.unpack(">HH", b[0:4])
        dpi = struct.unpack("<H", b[6:8])[0]
        dims[(w, h, dpi)] = dims.get((w, h, dpi), 0) + 1
        j += 8
    return {"paginas": n, "texto": d.count(b"TXTz") + d.count(b"TXTa"),
            "bitonal": d.count(b"Sjbz"), "dims": dims}


def lineas(djvu: Path, pag: int) -> list[tuple[int, int, int, int, str]]:
    raw = subprocess.run(["djvutxt", "--detail=line", f"--page={pag}", str(djvu)],
                         capture_output=True).stdout
    return [(int(a), int(b), int(c), int(dd), desescapa(t))
            for a, b, c, dd, t in LINEA.findall(raw)]


def pagina_md(ls, sangria: int, cabecera: int, aparato: bool = False) -> str:
    """Una página → párrafos. `sangria` = px extra que marca inicio de párrafo.

    `aparato=True` aparta la banda del pie compuesta en CUERPO MENOR —el aparato
    crítico de variantes de una edición como esta— en vez de dejarla dentro de la
    prosa. La señal es la ALTURA de la línea: 40-42 px el cuerpo, 33-36 el aparato.
    """
    ls = [l for l in ls if l[4].strip()]
    if not ls:
        return ""
    pie = []
    if aparato and len(ls) > 6:
        alt = sorted(l[3] - l[1] for l in ls[cabecera:])   # en DjVu, y crece hacia ARRIBA
        m = alt[len(alt) // 2]
        k = len(ls)
        while k > cabecera + 3 and (ls[k - 1][3] - ls[k - 1][1]) < m - 2:
            k -= 1
        if k < len(ls):
            pie = [l[4].strip() for l in ls[k:]]
            ls = ls[:k]
    # El titulillo y el folio van arriba y quedan separados del cuerpo por un hueco
    # mayor que el interlineado. `cabecera` = cuántas líneas de cabecera descartar.
    cuerpo = ls[cabecera:]
    if not cuerpo:
        return ""
    izq = sorted(l[0] for l in cuerpo)
    base = izq[len(izq) // 2]                 # margen del cuerpo (mediana, robusta)
    # La sangría se mide RESPECTO A LA LÍNEA ANTERIOR, no en absoluto. Con umbral
    # absoluto, las DOS primeras líneas de un capítulo —las que rodean la capitular—
    # van metidas y el primer párrafo sale partido en dos; y un título centrado de
    # tres renglones sale como tres párrafos. Exigiendo que la anterior estuviera al
    # margen, la capitular y el título se recomponen solos.
    # Segunda señal, y la que separa el TÍTULO del cuerpo: el HUECO VERTICAL. Entre
    # renglones de un párrafo hay 4-13 px; antes de un título de capítulo, 71; antes
    # del primer párrafo tras él, 108. La sangría sola no los distingue, porque el
    # título va centrado y la primera línea del capítulo también entra.
    huecos = sorted(cuerpo[i - 1][1] - cuerpo[i][3] for i in range(1, len(cuerpo)))
    med = huecos[len(huecos) // 2] if huecos else 0
    corte = max(med * 2 + 8, med + 18)
    parrafos, act, prev_sangrada = [], [], False
    for k, (x0, y0, x1, y1, t) in enumerate(cuerpo):
        t = t.strip()
        sangrada = x0 > base + sangria
        salto = k and (cuerpo[k - 1][1] - y1) > corte
        if act and (salto or (sangrada and not prev_sangrada)):
            parrafos.append(act); act = []
        prev_sangrada = sangrada
        act.append(t)
    if act:
        parrafos.append(act)
    out = []
    for p in parrafos:
        s = ""
        for ln in p:
            if s.endswith("-"):
                s = s[:-1] + ln            # palabra partida al final de renglón
            else:
                s = (s + " " + ln).strip() if s else ln
        out.append(re.sub(r"\s+", " ", s).strip())
    if pie:
        out.append("<!-- aparato crítico -->\n> " +
                   re.sub(r"\s+", " ", " ".join(pie)).strip())
    return "\n\n".join(x for x in out if x)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("djvu", type=Path)
    ap.add_argument("--info", action="store_true", help="solo diagnóstico")
    ap.add_argument("--pages", help="rango 1-based, p. ej. 110-415")
    ap.add_argument("--parity", choices=("even", "odd", "all"), default="all",
                    help="quedarse solo con las páginas pares o impares (bilingüe "
                         "a páginas enfrentadas)")
    ap.add_argument("--out", type=Path, help="archivo .md de salida")
    ap.add_argument("--title", help="título H1")
    ap.add_argument("--sangria", type=int, default=25,
                    help="px de sangría que marcan párrafo nuevo (def. 25)")
    ap.add_argument("--cabecera", type=int, default=2,
                    help="líneas de titulillo/folio a descartar por página (def. 2)")
    ap.add_argument("--aparato", action="store_true",
                    help="aparta la banda del pie en cuerpo menor (aparato crítico)")
    ap.add_argument("--marcar-paginas", action="store_true",
                    help="inserta <!-- p. N --> al principio de cada página")
    a = ap.parse_args()

    if a.info or not a.pages:
        d = info(a.djvu)
        print(f"páginas: {d['paginas']}")
        print(f"capa de texto (OCR ya incrustado): {d['texto']} páginas")
        print(f"imágenes bitonales: {d['bitonal']}")
        for (w, h, dpi), n in sorted(d["dims"].items(), key=lambda kv: -kv[1])[:3]:
            print(f"   {n:4} págs · {w}x{h} px · {dpi} ppp · "
                  f"{w/dpi:.2f}x{h/dpi:.2f} pulgadas")
        if not a.pages:
            return 0

    ini, fin = (int(x) for x in a.pages.split("-"))
    trozos = []
    for p in range(ini, fin + 1):
        if a.parity == "even" and p % 2:
            continue
        if a.parity == "odd" and not p % 2:
            continue
        md = pagina_md(lineas(a.djvu, p), a.sangria, a.cabecera, a.aparato)
        if md:
            trozos.append((f"<!-- p. {p} -->\n\n" if a.marcar_paginas else "") + md)
    texto = ("# " + a.title + "\n\n" if a.title else "") + "\n\n".join(trozos) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(texto, encoding="utf-8")
        print(f"  {a.out}: {len(texto.split())} palabras · "
              f"{texto.count(chr(10)+chr(10))+1} párrafos")
    else:
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
