#!/usr/bin/env python3
"""morinus_directions_clean.py — Normaliza los volcados de DIRECCIONES del programa
Morinus que el OCR deja regados en el markdown de libros de astrología predictiva.

El programa Morinus imprime listados de direcciones primarias/simbólicas con este
aspecto crudo (glifos rotos por el OCR: la «Z» inicial es el significador Asc y la
«D» = «dirigido»):

    Z (Virgo)Jupiter D --> Asc 29.714593 1969.12.11
    Z Sextile Moon D --> Asc 13.926553 1954.02.27

Al convertir a PDF quedan como fragmentos extraños intercalados en la prosa (unas
veces como párrafo suelto, otras dentro de ``` ```), rompiendo la lectura aunque
son DATOS legítimos que el análisis siguiente comenta. Esta herramienta:

  * reconoce cada registro «<sig> <aspecto|(signo)planeta> D --> <punto> <arco> <fecha>»,
  * quita los glifos rotos (Z, D) y traduce planeta/signo/aspecto al español,
  * lo reescribe como una línea de dato limpia y uniforme, en monospace:
        Asc  ·  sextil a la Luna           ·  13.93°  ·  1954.02.27
        Asc  ·  término de Júpiter en Virgo ·  29.71°  ·  1969.12.11
  * agrupa los registros contiguos en un solo bloque ``` ```; respeta cualquier
    otro bloque de código que no sea de direcciones.

Conserva TODA la información (punto dirigido, promisor, arco y fecha); solo elimina
los artefactos de OCR y unifica el formato. Por defecto REPORTA; --apply escribe.

Uso:
    python3 morinus_directions_clean.py cap.md [--apply]
    for f in ./markdown-es/*.md; do python3 morinus_directions_clean.py "$f" --apply; done
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

PLANET = {
    "Sun": "el Sol", "Moon": "la Luna", "Mercury": "Mercurio", "Venus": "Venus",
    "Mars": "Marte", "Jupiter": "Júpiter", "Saturn": "Saturno", "Uranus": "Urano",
    "Neptune": "Neptuno", "Pluto": "Plutón",
}
SIGN = {
    "Aries": "Aries", "Taurus": "Tauro", "Gemini": "Géminis", "Cancer": "Cáncer",
    "Leo": "Leo", "Virgo": "Virgo", "Libra": "Libra", "Scorpio": "Escorpio",
    "Scorpius": "Escorpio", "Sagittarius": "Sagitario", "Capricorn": "Capricornio",
    "Capricornus": "Capricornio", "Aquarius": "Acuario", "Pisces": "Piscis",
}
# Morinus rotula los aspectos en inglés o en alemán según la instalación:
ASPECT = {
    "Conjunction": "conjunción con", "Konjunktion": "conjunción con",
    "Opposition": "oposición a",
    "Trine": "trígono a", "Trigon": "trígono a",
    "Square": "cuadratura a", "Quadrat": "cuadratura a", "Quadrate": "cuadratura a",
    "Sextile": "sextil a", "Sextil": "sextil a",
    "Semisextile": "semisextil a", "Semisextil": "semisextil a",
    "Quincunx": "quincuncio a",
    "Sesquiquadrate": "sesquicuadratura a", "Semisquare": "semicuadratura a",
}
TARGET = {"Asc": "Asc", "MC": "MC", "IC": "IC", "Dsc": "Desc", "Desc": "Desc", "DSC": "Desc"}

# un registro. El token inicial (glifo roto del significador: Z, «...», ♄…) puede
# faltar. Cuerpo = aspecto+planeta  Ó  (signo)planeta  Ó  planeta suelto. Luego
# «D --> punto [arco] fecha»; el ARCO puede faltar (algunos listados solo dan fecha).
_ASPECTS = "|".join(ASPECT)
_SIGNS = "|".join(SIGN)
_PLANETS = "|".join(PLANET)
RECORD_RE = re.compile(
    r"(?:(?P<aspect>" + _ASPECTS + r")\s+(?P<aplanet>" + _PLANETS + r")"
    r"|\(\s*(?P<sign>" + _SIGNS + r")\s*\)\s*(?P<bplanet>" + _PLANETS + r")"
    r"|(?P<pplanet>" + _PLANETS + r"))"
    r"\s+D\s+-->\s+(?P<target>Asc|MC|IC|Dsc|Desc|DSC)"
    r"(?:\s+(?P<arc>\d+(?:\.\d+)?))?"
    r"\s+(?P<date>\d{3,4}\.\d{2}\.\d{2})"
)


def _fmt(m):
    target = TARGET.get(m.group("target"), m.group("target"))
    arc = "%.2f°" % float(m.group("arc")) if m.group("arc") else ""
    date = m.group("date")
    if m.group("aspect"):
        asp = ASPECT[m.group("aspect")]
        pl = PLANET.get(m.group("aplanet"), m.group("aplanet"))
        what = f"{asp} {pl}"
    elif m.group("sign"):
        pl = PLANET.get(m.group("bplanet"), m.group("bplanet"))
        sg = SIGN.get(m.group("sign"), m.group("sign"))
        what = f"término de {pl} en {sg}"
    else:                                                # planeta suelto (cuerpo a cuerpo)
        what = PLANET.get(m.group("pplanet"), m.group("pplanet"))
    what = re.sub(r"\ba el\b", "al", what)               # «oposición a el Sol» -> «al Sol»
    return target, what, arc, date


def _reformat_line(line):
    """Devuelve la lista de líneas de dato limpias para todos los registros de `line`
    (una línea física puede traer varios registros concatenados)."""
    recs = [_fmt(m) for m in RECORD_RE.finditer(line)]
    if not recs:
        return None
    wmax = max(len(w) for _, w, _, _ in recs)
    amax = max(len(a) for _, _, a, _ in recs)
    out = []
    for t, w, a, d in recs:
        mid = f" {a.ljust(amax)} ·" if amax else ""      # columna de arco solo si hay alguno
        out.append(f"{t} · {w.ljust(wmax)} ·{mid} {d}")
    return out


def clean(text):
    lines = text.split("\n")
    out, recbuf, n = [], [], 0

    def flush():
        if recbuf:
            out.append("```")
            out.extend(recbuf)
            out.append("```")
            recbuf.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "```":                          # abre un bloque de código
            j = i + 1
            block = []
            while j < len(lines) and lines[j].strip() != "```":
                block.append(lines[j]); j += 1
            is_rec = block and all(RECORD_RE.search(b) or not b.strip() for b in block)
            if is_rec:                                   # bloque de direcciones: reescribir
                for b in block:
                    r = _reformat_line(b)
                    if r: recbuf.extend(r); n += len(r)
                i = j + 1
                continue
            flush()                                      # otro código: conservar intacto
            out.append(ln); out.extend(block)
            if j < len(lines): out.append(lines[j])
            i = j + 1
            continue
        r = _reformat_line(ln)
        if r:                                            # registro suelto en prosa
            recbuf.extend(r); n += len(r); i += 1; continue
        flush(); out.append(ln); i += 1
    flush()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)), n


def main():
    ap = argparse.ArgumentParser(description="Limpia volcados de direcciones de Morinus en markdown.")
    ap.add_argument("input")
    ap.add_argument("--apply", action="store_true", help="escribe en el sitio (por defecto: solo reporta)")
    a = ap.parse_args()
    src = Path(a.input)
    final, n = clean(src.read_text(encoding="utf-8"))
    print(f"{src.name}: {n} registros de dirección normalizados")
    if a.apply:
        src.write_text(final, encoding="utf-8"); print("  escrito en el sitio.")
    else:
        print("  (solo reporte; usa --apply para escribir)")


if __name__ == "__main__":
    main()
