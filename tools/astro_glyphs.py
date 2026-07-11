#!/usr/bin/env python3
"""
astro_glyphs.py — Astrological-glyph reference + OCR-garble flagger for Markdown
tables.

Honest scope: NO OCR engine reads astrological symbols (♄ ♃ ♂ ☉ ♀ ☿ ☾ and the
zodiac signs). In scanned books their table cells come out as junk ("■ t?",
"£", "V", "r o n", "®sm"). There is no reliable automatic mapping — the only
faithful fix is to look at the page image and type the right glyph. This tool
therefore does two useful things:

  --flag FILE     Scan a Markdown file's table cells and print the ones that
                  look like garbled glyph cells (short, mostly non-alphanumeric,
                  inside a table), with line numbers, so you know exactly which
                  cells to correct against the source PDF page.

  --reference     Print the canonical Unicode glyphs with their names and common
                  OCR-garble forms, as a crib sheet while you fix cells by hand.

The dictionaries are importable (`GLYPHS`, `SIGNS`) for use by other scripts.

Usage:
  python3 astro_glyphs.py --reference
  python3 astro_glyphs.py --flag 03_Chapter.md
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# planet/luminary  ->  (unicode, english, spanish, common OCR garbles)
GLYPHS = {
    "sun":     ("☉", "Sun", "Sol", ["©", "®", "0", "O", "(f", "cP"]),
    "moon":    ("☾", "Moon", "Luna", ["C", "(", "€", "ts", "tS"]),
    "mercury": ("☿", "Mercury", "Mercurio", ["£", "V", "$", "cf", "5"]),
    "venus":   ("♀", "Venus", "Venus", ["$", "9", "?", "£"]),
    "mars":    ("♂", "Mars", "Marte", ["cf", "c?", "(f", "d", "cP"]),
    "jupiter": ("♃", "Jupiter", "Júpiter", ["If", "4", "2/", "t?", "2)"]),
    "saturn":  ("♄", "Saturn", "Saturno", ["t?", "b", "fj", "h", "■ t?"]),
}
# zodiac sign  ->  (unicode, english, spanish)
SIGNS = {
    "aries":       ("♈", "Aries", "Aries"),
    "taurus":      ("♉", "Taurus", "Tauro"),
    "gemini":      ("♊", "Gemini", "Géminis"),
    "cancer":      ("♋", "Cancer", "Cáncer"),
    "leo":         ("♌", "Leo", "Leo"),
    "virgo":       ("♍", "Virgo", "Virgo"),
    "libra":       ("♎", "Libra", "Libra"),
    "scorpio":     ("♏", "Scorpio", "Escorpio"),
    "sagittarius": ("♐", "Sagittarius", "Sagitario"),
    "capricorn":   ("♑", "Capricorn", "Capricornio"),
    "aquarius":    ("♒", "Aquarius", "Acuario"),
    "pisces":      ("♓", "Pisces", "Piscis"),
}
GLYPH_CHARS = set(g[0] for g in GLYPHS.values()) | set(s[0] for s in SIGNS.values())


def print_reference():
    print("PLANETS / LUMINARIES")
    for k, (u, en, es, garbles) in GLYPHS.items():
        print(f"  {u}  {en:9s} {es:10s}  garbles: {', '.join(garbles)}")
    print("\nZODIAC SIGNS")
    for k, (u, en, es) in SIGNS.items():
        print(f"  {u}  {en:12s} {es}")
    print("\nOrder for reconstruction (traditional): ♄ ♃ ♂ ☉ ♀ ☿ ☾  ·  ♈♉♊♋♌♍♎♏♐♑♒♓")


def looks_garbled(cell):
    c = cell.strip()
    if not c or len(c) > 16:
        return False
    if any(ch in GLYPH_CHARS for ch in c):
        return False  # already a real glyph
    letters = sum(ch.isalpha() for ch in c)
    junk = sum((not ch.isalnum()) and not ch.isspace() for ch in c)
    # short cell dominated by symbols / stray single letters
    return junk >= 1 and letters <= 3 and bool(re.search(r"[■£®©?½¾◄●◊□]|\b[a-zA-Z]\s?\?", c))


def flag(path):
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    hits = 0
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not (s.startswith("|") and "|" in s[1:]) or set(s) <= set("|-: "):
            continue
        cells = [c for c in s.strip("|").split("|")]
        for c in cells:
            if looks_garbled(c):
                print(f"  L{i}: garbled cell {c.strip()!r}  in: {s[:90]}")
                hits += 1
                break
    print(f"\n{hits} suspicious glyph cell(s). Fix each against the PDF page image "
          f"(see --reference for glyphs).")


def main():
    ap = argparse.ArgumentParser(description="Astrological glyph reference + garble flagger.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--reference", action="store_true", help="print the glyph crib sheet")
    g.add_argument("--flag", metavar="FILE", help="flag likely garbled glyph cells in a markdown file")
    args = ap.parse_args()
    if args.reference:
        print_reference()
    else:
        flag(args.flag)


if __name__ == "__main__":
    main()
