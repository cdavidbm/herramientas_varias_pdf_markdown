#!/usr/bin/env python3
"""footnote_chain.py — Separa el APARATO de notas del CUERPO cuando la única señal fiable
es que los números de nota son CONSECUTIVOS, no la sangría.

El problema
-----------
Al extraer una página de PDF, el bloque de notas al pie va SIEMPRE al fondo. La forma
habitual de detectarlo —«las continuaciones van indentadas»— FALLA en dos situaciones muy
comunes:
  · se recortó una columna (p.ej. la mitad inglesa de un facing árabe|inglés) y el recorte
    reinició el origen X, así que las continuaciones de nota quedan en la columna 0;
  · el OCR aplastó la sangría.
Sin la sangría, una línea de nota y una de cuerpo se parecen demasiado.

La idea clave
-------------
Los números de nota corren CONSECUTIVOS (…, n, n+1, n+2, …). Esa es la señal robusta:
  1. El aparato = el trailing run que arranca en la primera línea-nota cuyos números forman
     una cadena n, n+1, n+2… hasta el pie.
  2. Un número de línea que NO es «anterior+1» (una remisión interna «128 below», un
     «3.3 above», o una cifra de cuerpo) se trata como CONTINUACIÓN, no como nota nueva,
     así que no rompe la cadena ni abre una nota falsa.
  3. El número de página del pie (también una línea-número) no es consecutivo con la
     cadena → no la contamina.

Dos formatos de marcador (ambos vistos en ediciones reales)
-----------------------------------------------------------
  · MISMA LÍNEA  (por defecto): «  26 Latin: 'argumentum'.»  ·  incluso pegado: «25P gives…»
    (edición Brill de la Abbreviation de Abū Maʿshar).
  · NÚMERO SOLO  (--number-only): el volado va solo en su renglón y el texto en el siguiente
    («4\n  I cannot find…»)  (Flowers de Abū Maʿshar, trad. Dykes).

Las LLAMADAS (volados aplastados por el OCR: «voice,9», «beginning7») se anclan con un
CURSOR ascendente: como aparecen en el mismo orden que las notas, se busca cada número a
partir de donde se ancló el anterior, lo que evita anclar una cifra de prosa anterior.

Medido en «The Abbreviation of the Introduction to Astrology» (Brill; notas 1-112 completas)
y «The Flowers of Abū Maʿshar» (Dykes; notas 1-308, 0 huecos). La lógica de estas dos
conversiones vive aquí para que el próximo bisturí la importe en vez de reinventarla.

Uso como MÓDULO (lo normal, dentro de un extractor):
    from footnote_chain import process_page
    md = process_page(texto_de_una_pagina, number_only=False)

Uso como CLI (procesa un archivo como UN bloque; útil para probar o un caso suelto):
    python3 footnote_chain.py pagina.txt [--number-only]
"""
import argparse
import re
import sys
from pathlib import Path

# marcador en la MISMA línea: número (0-6 esp de sangría variable) + texto; admite el número
# PEGADO a una mayúscula («25P gives») porque el OCR a veces se come el espacio.
FN_SAMELINE = re.compile(r"^ {0,6}(\d{1,3})(?:\s+|(?=[A-Z]))(\S.*)$")
# marcador NÚMERO SOLO en su línea (el texto va en las siguientes).
FN_NUMONLY = re.compile(r"^\s*(\d{1,3})\s*$")
PAGENUM = re.compile(r"^\s*\d{1,4}\s*$")


def _fn_re(number_only):
    return FN_NUMONLY if number_only else FN_SAMELINE


def split_apparatus(lines, number_only=False, max_gap=15):
    """Devuelve (líneas_cuerpo, líneas_notas). El aparato = primer arranque cuyos números
    forman una cadena consecutiva de ≥2 con PROXIMIDAD (cada nota a ≤`max_gap` líneas de la
    anterior). La proximidad es esencial: una LLAMADA volada que el OCR dejó sola en su
    renglón cerca del cuerpo (p.ej. «132» flotando bajo un título) NO debe abrir el bloque
    aunque más abajo exista la nota «133» — están a 40 líneas, no forman aparato contiguo;
    el bloque real va al pie, con sus números juntos. En su defecto, una nota única en el
    tercio final."""
    fn = _fn_re(number_only)
    marks = [(i, int(fn.match(l).group(1))) for i, l in enumerate(lines) if fn.match(l)]

    for si, (i0, n0) in enumerate(marks):
        last_i, last_n, count = i0, n0, 1
        for i, n in marks[si + 1:]:
            if n == last_n + 1:
                if i - last_i <= max_gap:      # consecutiva y CONTIGUA → misma cadena
                    last_i, last_n, count = i, n, count + 1
                else:
                    break                       # consecutiva pero lejos → otro bloque
            # un número no consecutivo es continuación: ni suma ni rompe
        if count >= 2:
            return lines[:i0], lines[i0:]
    for i, ln in enumerate(lines):
        if fn.match(ln) and i >= len(lines) * 2 // 3:
            return lines[:i], lines[i:]
    return lines, []


def parse_notes(fn_lines, number_only=False, stop_re=None):
    """Reúne el texto de cada nota. Solo abre nota nueva si el número es «anterior+1»; toda
    otra línea (incl. una que empiece por cifra no consecutiva) se acumula como continuación.
    `stop_re`: patrón opcional que cierra el bloque (p.ej. un pie de página repetido)."""
    fn = _fn_re(number_only)
    notes, cur = {}, None
    for ln in fn_lines:
        if stop_re and stop_re.search(ln):
            break
        m = fn.match(ln)
        if m and (cur is None or int(m.group(1)) == cur + 1):
            cur = int(m.group(1))
            notes[cur] = "" if number_only else m.group(2).strip()
        elif cur is not None and ln.strip() and not PAGENUM.match(ln):
            notes[cur] = (notes[cur] + " " + ln.strip()).strip()
    return {n: t for n, t in notes.items() if t}


def anchor_calls(text, note_nums):
    """Ancla las llamadas pegadas ('voice,9'→'voice,[^9]') con un cursor ascendente: cada
    nota se busca a partir de donde se ancló la anterior (mismo orden de lectura)."""
    cursor = 0
    for n in sorted(note_nums):
        glued = re.compile(rf"(?<=[A-Za-z\)\.\,\;\'’]){n}(?![0-9])")
        spaced = re.compile(rf"(?<=[A-Za-z\)\.\,\;\'’]) {n}(?![0-9])")
        m = glued.search(text, cursor) or spaced.search(text, cursor)
        if m:
            text = text[:m.start()] + f"[^{n}]" + text[m.end():]
            cursor = m.start() + len(f"[^{n}]")
    return text


def process_page(page_text, number_only=False, stop_re=None):
    """Separa cuerpo/aparato de UNA página, ancla llamadas y emite markdown con `[^N]`.
    (El cuerpo se devuelve tal cual, línea a línea; el reflow de párrafos y la promoción de
    encabezados los hace el extractor concreto, que conoce la maqueta del libro.)"""
    lines = page_text.split("\n")
    body_lines, fn_lines = split_apparatus(lines, number_only)
    notes = parse_notes(fn_lines, number_only, stop_re)
    body = "\n".join(body_lines).strip()
    if notes:
        body = anchor_calls(body, notes.keys())
        body += "\n\n" + "\n".join(f"[^{n}]: {notes[n]}" for n in sorted(notes))
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, help="texto de una página (o bloque) a separar")
    ap.add_argument("--number-only", action="store_true",
                    help="el número de nota va solo en su línea (estilo Flowers/Dykes)")
    a = ap.parse_args()
    txt = a.file.read_text(encoding="utf-8")
    md = process_page(txt, number_only=a.number_only)
    sys.stdout.write(md + "\n")
    defs = len(re.findall(r"(?m)^\[\^\d+\]:", md))
    sys.stderr.write(f"\n{defs} notas separadas\n")


if __name__ == "__main__":
    main()
