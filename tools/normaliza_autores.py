#!/usr/bin/env python3
"""
normaliza_autores.py — arregla el nombre de la AUTORIDAD al final de cada encabezado.

*Judges* es un compendio: cada capítulo se atribuye a una de nueve autoridades, y esa
atribución va al final del encabezado tras un guion largo («—Sahl», «—ʿUmar»). Es
información editorial de primer orden: saber si un juicio es de Sahl o de Doroteo cambia
cómo se lee.

El OCR del escaneo destroza justamente ahí, porque el volado de nota se pega al nombre:
se han medido más de cincuenta variantes de nueve nombres —«Sah», «SahF», «Sahb»,
«Jitjis», «Jisjis», «lJirjis», «al-Kindr», «al-Kind?», «aAristotle»—. Al quitar la basura
del final, además, algunos quedan TRUNCADOS («Sahl» → «Sah»).

Como el repertorio es CERRADO, se puede normalizar sin adivinar: se compara con la lista
canónica y solo se corrige por encima de un umbral alto de parecido.

DOS GUARDAS que importan:
  1. Un `[^N]` pegado al nombre es una LLAMADA DE NOTA legítima («Sahl[^1-126]»), no
     basura: se separa antes de comparar y se vuelve a pegar después.
  2. Si ningún candidato supera el umbral, NO se toca y se reporta. Inventar una
     atribución sería peor que dejar el nombre sucio.

Dry-run por defecto.
"""
from __future__ import annotations

import argparse
import difflib
import re
import unicodedata
from pathlib import Path

# Repertorios CERRADOS de autoridades. La normalización solo es segura si la lista está
# completa: lo que no se parezca a nada de ella se deja intacto y se reporta.
# `--autores` acepta una lista suelta («Sahl,ʿUmar,…») o un fichero con un nombre por línea,
# para cualquier libro que no sea de los presets.
PRESETS = {
    # *The Book of the Nine Judges* (Dykes) y el resto del clúster Essential Medieval Astrology
    "nine-judges:en": ["Sahl", "ʿUmar", "al-Kindī", "Dorotheus", "Jirjis", "al-Khayyāt",
                       "Māshā'allāh", "Aristotle", "al-Rijāl", "[Unknown]"],
    "nine-judges:es": ["Sahl", "ʿUmar", "al-Kindī", "Doroteo", "Jirjis", "al-Khayyāt",
                       "Māshā'allāh", "Aristóteles", "al-Rijāl", "[Desconocido]"],
}


def carga_canon(autores: str | None, idioma: str) -> list[str]:
    if not autores:
        return PRESETS[f"nine-judges:{idioma}"]
    p = Path(autores)
    if p.is_file():
        return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if autores in PRESETS:
        return PRESETS[autores]
    return [x.strip() for x in autores.split(",") if x.strip()]
# El separador de atribución es la RAYA LARGA. Un guion corto solo cuenta si va suelto
# («… -Sahl»), nunca el interno de «al-Rijāl» o «whole-sign»: tomarlo por separador
# convertía «APPENDIX D: … FROM AL-RIJĀL I.5.1» en «… FROM al-Rijāl», comiéndose la
# referencia. Se busca la ÚLTIMA raya de la línea, no la primera.
ATRIB = re.compile(r"(?P<sep>[—–]+|\s-{1,2}(?=\s*\S))\s*(?P<nom>[^—–]*?)\s*$")
ANCLA = re.compile(r"(\[\^[\w-]+\])\s*$")
# una atribución es un NOMBRE, no una cláusula: como mucho dos palabras y corto
def es_nombre(s: str) -> bool:
    return len(s) <= 24 and len(s.split()) <= 2


def plano(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return re.sub(r"[^a-z]", "", s.encode("ascii", "ignore").decode().lower())


def arregla(h: str, canon: list[str], umbral: float) -> tuple[str, str | None]:
    m = ATRIB.search(h)
    if not m or not m.group("nom"):
        return h, None
    nom = m.group("nom")
    ancla = ""
    if a := ANCLA.search(nom):                 # la llamada de nota NO es parte del nombre
        ancla, nom = a.group(1), nom[:a.start()].rstrip()
    if not es_nombre(nom):                     # es una cláusula del título, no una autoría
        return h, None
    if nom in canon:
        limpio = f"—{nom}" + (ancla if not ancla else ancla)
        return (h[:m.start()] + limpio, None) if m.group("sep") != "—" else (h, None)
    base = plano(nom)
    if not base:
        return h, None
    mejor, punt = None, 0.0
    for c in canon:
        r = difflib.SequenceMatcher(None, base, plano(c)).ratio()
        if r > punt:
            mejor, punt = c, r
    if punt < umbral:
        return h, f"sin resolver «{nom}»"
    return h[:m.start()] + f"—{mejor}{ancla}", f"«{nom}» → {mejor}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--idioma", choices=["en", "es"], required=True)
    ap.add_argument("--autores", metavar="LISTA|FICHERO|PRESET",
                    help="repertorio de autoridades: «Sahl,ʿUmar,…», un fichero con un "
                         "nombre por línea, o un preset (def: nine-judges del idioma)")
    ap.add_argument("--umbral", type=float, default=0.72)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    canon = carga_canon(a.autores, a.idioma)
    n = 0
    pendientes: list[str] = []
    for f in sorted(a.dir.glob("*.md")):
        ls = f.read_text(encoding="utf-8").split("\n")
        cam = False
        for i, l in enumerate(ls):
            if not l.startswith("#"):
                continue
            nuevo, aviso = arregla(l, canon, a.umbral)
            if aviso and aviso.startswith("sin resolver"):
                pendientes.append(f"{f.name[:22]:<22} {aviso}")
            if nuevo != l:
                print(f"  {f.name[:22]:<22} {aviso or 'separador'}")
                ls[i], cam = nuevo, True
                n += 1
        if cam and a.apply:
            f.write_text("\n".join(ls), encoding="utf-8")
    print(f"\n{n} atribuciones normalizadas{'' if a.apply else '  (dry-run: usa --apply)'}")
    if pendientes:
        print(f"\n{len(pendientes)} SIN RESOLVER (se dejan como están, revísalas):")
        for p in pendientes[:20]:
            print("   " + p)


if __name__ == "__main__":
    main()
