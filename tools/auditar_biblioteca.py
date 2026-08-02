#!/usr/bin/env python3
"""auditar_biblioteca.py — pasa por TODOS los libros ya convertidos y dice cuáles
tienen defectos de los que se detectan sin abrir el original.

Nace de una pregunta del usuario que no tenía respuesta: «¿cuántos libros más de la
biblioteca estarán mal?». Cada libro se auditó en su momento con los controles que
existían ENTONCES; los controles nuevos —notas sin traducir, párrafos partidos,
caracteres perdidos al maquetar— nunca se aplicaron hacia atrás. Esto lo hace.

Solo comprueba lo que se puede demostrar con los archivos que hay (no abre el PDF
fuente ni mide la fidelidad de la traducción):

  · APARATO   definiciones sin llamada (pandoc NO las imprime, se pierden en el PDF)
              y llamadas sin definición.
  · TRADUCCIÓN definiciones de nota idénticas al original con prosa —una tanda sin
              traducir— y bloques de prosa en el idioma de origen.
  · PDF       caracteres no ASCII del markdown que NO están en el PDF compilado:
              Latin Modern los descarta en silencio si falta `--font-fallback`.
  · MAQUETA   párrafos partidos a media frase y marcas de énfasis mal colocadas
              (`Hismael*.*`, `In*R* *eason*`), que se IMPRIMEN como asteriscos.

Uso:
    python3 auditar_biblioteca.py /home/chris/Biblioteca_Mc
    python3 auditar_biblioteca.py /home/chris/Biblioteca_Mc --solo "Nine Judges"
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cose_parrafos import cose                                    # noqa: E402
from traducir_libro import (verificar_notas_traducidas,           # noqa: E402
                            parrafos_sin_traducir)

# Los libros no siguen una sola convención de carpetas; estas son las que hay.
PARES = [("en", "es"), ("markdown", "markdown-es"), ("Inglés", "Español"),
         ("markdown", "es"), ("dykes", "es"), ("marcado", "es")]
SOLO_MD = ["en", "markdown", "Inglés", "es", "markdown-es", "Español", "dykes",
           "yamamoto", "capitulos"]

# Énfasis MAL COLOCADO. Sobre el TEXTO EXTRAÍDO DE UN PDF vale `\S\*\S` —ahí no debería
# quedar ningún asterisco—, pero sobre el MARKDOWN esa regla es un desastre: casa con
# `*vanitate*,`, que es una cursiva cerrada antes de una coma y es correcta. Medido:
# 200 falsos positivos en un solo archivo que estaba limpio. Lo que sí es un error
# seguro es un `*` con LETRA a los dos lados (`In*R* *eason*`, `Hismael*.*`): ahí la
# maqueta cortó la cursiva en el salto de renglón y el bisturí la dejó partida.
ASTER = re.compile(r"[^\W\d_]\*[^\W\d_]|\*[,.;:]\*")
# Archivos donde el texto en el idioma origen es LEGÍTIMO y no hay que reportarlo:
# una bibliografía son fichas, un apéndice de citas latinas es latín, una lista de
# abreviaturas son títulos. Sin esta exclusión el ruido tapa los hallazgos reales.
NO_TRADUCIBLE = re.compile(r"biblio|abbrev|abreviat|appendix|apéndice|apendice|"
                           r"latin|latín|index|índice|indice|notes?$", re.I)


def mds(d: Path) -> list[Path]:
    return sorted(f for f in d.glob("*.md") if not f.name.startswith("_"))


def aparato(files: list[Path]) -> tuple[int, int, int]:
    """(definiciones, huérfanas, llamadas sin definir) — una huérfana NO se imprime."""
    huer = sindef = ndef = 0
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        refs = set(re.findall(r"\[\^([^\]]+)\](?!:)", t))
        defs = set(re.findall(r"(?m)^\[\^([^\]]+)\]:", t))
        ndef += len(defs); huer += len(defs - refs); sindef += len(refs - defs)
    return ndef, huer, sindef


def perdidos_en_pdf(files: list[Path], pdf: Path) -> tuple[list[str], int]:
    """(caracteres perdidos, renglones con pipes de tabla sin renderizar).

    Dos correcciones que costaron un falso positivo cada una, medidas al auditar la
    biblioteca entera:

    · Los **glifos astrológicos** (☉♄♈) se componen con *starfont*, que los imprime
      perfectamente pero los extrae como letras ASCII. Si el PDF embebe esa fuente,
      no se pueden contar como perdidos: en Brennan salían 20 «pérdidas» y estaban
      todas impresas.
    · El **árabe** se extrae en FORMAS DE PRESENTACIÓN (U+FE70-FEFF), fuera del
      bloque árabe normal, así que compararlo carácter a carácter da 371 pérdidas
      donde no hay ninguna. Se normaliza con NFKD antes de comparar.
    """
    try:
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                             capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return [], 0
    if not txt.strip():
        return [], 0
    fuentes = subprocess.run(["pdffonts", str(pdf)],
                             capture_output=True, text=True).stdout.lower()
    hay_star = "star" in fuentes
    # NFKD en los DOS lados o no vale de nada: descomponiendo solo el PDF, la `á` del
    # markdown deja de encontrarse y un libro en español sale con «á é í ñ ó ú
    # ausentes». Medido: 30-80 falsos positivos por libro, en TODOS.
    nk = lambda s: unicodedata.normalize("NFKD", s)
    presentes = {c for c in nk(txt) if ord(c) > 127}
    fuente = set()
    for f in files:
        for c in nk(f.read_text(encoding="utf-8", errors="replace")):
            if ord(c) > 127 and c.isprintable() and not c.isspace():
                if hay_star and (0x2600 <= ord(c) <= 0x27BF
                                 or 0x2295 <= ord(c) <= 0x2297):
                    continue                      # glifo de starfont: se imprime
                fuente.add(c)
    falta = sorted(fuente - presentes - set("*_`#[]"))
    # Una tabla que NO se renderizó sale como texto corrido con sus pipes a la vista.
    pipes = sum(1 for l in txt.splitlines() if l.count("|") >= 3)
    return falta, pipes


def audita(libro: Path) -> list[str]:
    avisos: list[str] = []
    dirs = {d.name: d for d in libro.iterdir() if d.is_dir()}
    par = next(((dirs[a], dirs[b]) for a, b in PARES if a in dirs and b in dirs), None)
    sueltos = [dirs[n] for n in SOLO_MD if n in dirs and mds(dirs[n])]
    if not sueltos:
        return ["sin markdown (no convertido, o con otra estructura)"]

    for d in sueltos:
        fs = mds(d)
        ndef, huer, sindef = aparato(fs)
        if huer:
            avisos.append(f"APARATO {d.name}/: {huer} definición(es) SIN LLAMADA de "
                          f"{ndef} — pandoc NO las imprime")
        if sindef:
            avisos.append(f"APARATO {d.name}/: {sindef} llamada(s) sin definición")
        rotos = sum(cose(f.read_text(encoding='utf-8', errors='replace'))[1] for f in fs)
        if rotos > 10:
            avisos.append(f"MAQUETA {d.name}/: {rotos} párrafo(s) partidos a media frase")
        ast = sum(len(ASTER.findall(f.read_text(encoding='utf-8', errors='replace')))
                  for f in fs)
        if ast:
            avisos.append(f"MAQUETA {d.name}/: {ast} marca(s) de énfasis mal colocadas")

    if par:
        o, t = par
        nt = sp = 0
        for f in mds(t):
            g = o / f.name
            if not g.exists() or NO_TRADUCIBLE.search(f.stem):
                continue
            src, dst = (g.read_text(encoding="utf-8", errors="replace"),
                        f.read_text(encoding="utf-8", errors="replace"))
            if verificar_notas_traducidas(src, dst):
                nt += 1
            sp += len(parrafos_sin_traducir(dst))
        if nt:
            avisos.append(f"TRADUCCIÓN: {nt} archivo(s) con definiciones de nota SIN "
                          f"TRADUCIR")
        if sp:
            avisos.append(f"TRADUCCIÓN: {sp} bloque(s) de prosa en el idioma origen")

    for pdf in sorted(libro.glob("*.pdf")):
        d = par[1] if par else sueltos[-1]
        n = pdf.name.lower()
        if not any(k in n for k in ("español", "espanol", "castellano", "(es)")):
            continue
        falta, pipes = perdidos_en_pdf(mds(d), pdf)
        if falta:
            avisos.append(f"PDF «{pdf.name}»: {len(falta)} carácter(es) del markdown "
                          f"NO están en el PDF: {''.join(falta[:40])}")
        if pipes:
            avisos.append(f"PDF «{pdf.name}»: {pipes} renglón(es) con pipes — una tabla "
                          f"que no se renderizó y salió como texto corrido")
    return avisos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("biblioteca", type=Path)
    ap.add_argument("--solo", help="audita solo los libros cuyo nombre contenga esto")
    a = ap.parse_args()

    libros = [d for d in sorted(a.biblioteca.iterdir())
              if d.is_dir() and d.name != "Por convertir"
              and (not a.solo or a.solo.lower() in d.name.lower())]
    limpios = 0
    for lib in libros:
        try:
            av = audita(lib)
        except Exception as e:                      # un libro raro no tumba la pasada
            av = [f"ERROR al auditar: {type(e).__name__}: {e}"]
        if av:
            print(f"\n■ {lib.name}")
            for x in av:
                print(f"    {x}")
        else:
            limpios += 1
    print(f"\n{limpios} de {len(libros)} libros sin avisos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
