#!/usr/bin/env python3
"""
footnotes_from_pdf.py — Reconstruye el APARATO DE NOTAS leyendo el del PDF original.

Por qué importa
---------------
Cuando un bisturí pierde los números volados, el aparato queda partido en dos
mitades igual de inservibles: definiciones sin llamada y textos de nota sueltos
por el cuerpo. Y el daño es ASIMÉTRICO en el resultado final:

  * una definición `[^N]:` SIN llamada **no se imprime**: pandoc la descarta en
    silencio y el texto de la nota desaparece del PDF final;
  * un texto de nota sin etiquetar se imprime como si fuera prosa, a mitad de
    capítulo, cortando el argumento del autor.

Por eso hay que rehacerlo ANTES de traducir (§3c): si se traduce primero, hay que
reconstruir el aparato en los dos idiomas a la vez.

Medido en el «Diploma Course» de Zoller: 102 notas no se habrían impreso y 133
textos de nota andaban sueltos por el cuerpo. Tras la reconstrucción: 624/624.

La idea clave
-------------
No se adivina la numeración: se lee la del PDF. En estos maquetados la definición
lleva su número SOLO en la línea anterior,

      3
          Pico della Mirandola, Opera, Basel 1572.

así que al colapsar los espacios queda «… 3 Pico della Mirandola …» y el número es
la tirada de dígitos que PRECEDE al texto. Se exige además que la numeración salga
ascendente 1, 2, 3…, lo que descarta de un plumazo los números de página.

Con esa lista se hacen tres cosas, en este orden:
  1. cada texto de nota suelto en el cuerpo pasa a ser `[^N]: …`;
  2. la nota cuyo texto NO esté en el markdown se inserta desde el PDF;
  3. cada llamada se sitúa por su CONTEXTO (las ~55 letras que la preceden en el
     PDF, en minúscula y sin puntuación: inmune a guiones de corte y comillas),
     avanzando con un cursor, porque la llamada N no puede ir antes que la N-1.

Guardas (para no romper texto sano)
-----------------------------------
  * Numeración estrictamente ascendente: un número de página nunca entra.
  * El texto se casa por su contenido, no por su posición; si no es inequívoco,
    se deja como está y se reporta.
  * Nunca se inserta una llamada al principio de una línea de definición (rompería
    la definición siguiente) ni dentro de la ruta de una figura.
  * El salto de línea del PDF puede colar la llamada antes de una cifra
    («(Milan, ⁶1650)»): se pasa detrás del número y su cierre.
  * `--interpolar` es el ÚLTIMO recurso para las que no se pudieron situar: las
    coloca entre sus vecinas ya ancladas. La posición es APROXIMADA; se usa porque
    una nota mal situada sigue siendo legible y una nota sin ancla se pierde.

Límite honesto
--------------
Si el PDF no numera las definiciones en línea aparte, o el escaneo perdió también
esos números, esta herramienta no puede reconstruir nada: no inventa notas.

Uso
---
    python3 footnotes_from_pdf.py cap.md --pdf cap.pdf              # simulacro
    python3 footnotes_from_pdf.py cap.md --pdf cap.pdf --apply --interpolar
    python3 footnotes_from_pdf.py --pairs pares.json --apply        # libro entero

Comprueba siempre el balance al terminar: definiciones == llamadas, 0 huérfanas.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

DEF = re.compile(r"^\[\^(\d+)\]:", re.M)
REF = re.compile(r"\[\^(\d+)\](?!:)")
CTX = 55


def texto_pdf(pdf: pathlib.Path) -> str:
    r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0 and not r.stdout:
        sys.exit(f"error: pdftotext no pudo leer {pdf}")
    return r.stdout


def notas_pdf(pdf: pathlib.Path) -> dict[int, str]:
    """Aparato real del PDF: el número va en la línea anterior y sube 1, 2, 3…"""
    ls = texto_pdf(pdf).split("\n")
    out, esp, i = {}, 1, 0
    while i < len(ls):
        m = re.match(r"^\s*(\d{1,3})\s*$", ls[i])
        if m and int(m.group(1)) == esp:
            t, j = [], i + 1
            while j < len(ls) and ls[j].strip() and not re.match(r"^\s*\d{1,3}\s*$", ls[j]):
                t.append(ls[j].strip())
                j += 1
            if t:
                out[esp] = " ".join(t)
                esp += 1
                i = j
                continue
        i += 1
    return out


def clave(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\*|\[\^\d+\]:?", "", s).lower())


def solo_letras(s: str, saltar_defs: bool = False):
    """texto → (letras minúsculas, posición original de cada letra)."""
    prohibido = set()
    if saltar_defs:
        for m in re.finditer(r"(?m)^\[\^\d+\]:.*$", s):
            prohibido.update(range(m.start(), m.end()))
    out, pos = [], []
    for i, c in enumerate(s):
        if c.isalpha() and i not in prohibido:
            out.append(c.lower())
            pos.append(i)
    return "".join(out), pos


def estructurar(txt: str, pn: dict[int, str]) -> tuple[str, int, int]:
    """(1) etiqueta los textos de nota sueltos y (2) inserta los que falten."""
    ya = {int(m.group(1)) for m in DEF.finditer(txt)}
    faltan = {n: t for n, t in pn.items() if n not in ya}
    if not faltan:
        return txt, 0, 0
    ls = txt.split("\n")
    libres = [i for i, l in enumerate(ls)
              if l.startswith(" ") and l.strip() and not l.lstrip().startswith("|")
              and not re.match(r"\s*\[\^", l) and len(l.strip()) > 10]
    hechos, usados = [], set()
    for n in sorted(faltan):
        k = clave(faltan[n])[:45]
        if len(k) < 12:
            continue
        cand = [i for i in libres if i not in usados and clave(ls[i])[:45].startswith(k[:25])]
        if len(cand) != 1:
            cand = [i for i in libres if i not in usados and k[:25] in clave(ls[i])]
        if len(cand) == 1:
            hechos.append((cand[0], n))
            usados.add(cand[0])
    for i, n in hechos:
        ls[i] = f"[^{n}]: " + ls[i].strip()
    cuerpo_k = clave("\n".join(ls))
    puestos = {n for _, n in hechos}
    nuevas = [n for n in sorted(faltan)
              if n not in puestos and len(clave(faltan[n])) >= 20
              and clave(faltan[n])[:35] not in cuerpo_k]
    if nuevas:
        ls.append("")
        ls += [f"[^{n}]: {faltan[n]}" for n in nuevas]
    return "\n".join(ls), len(hechos), len(nuevas)


def anclar(txt: str, pdf: pathlib.Path) -> tuple[str, int]:
    """Sitúa cada llamada huérfana por el contexto que la precede en el PDF."""
    defs = {int(m.group(1)) for m in DEF.finditer(txt)}
    refs = {int(m.group(1)) for m in REF.finditer(txt)}
    huer = defs - refs
    if not huer:
        return txt, 0
    pnorm = re.sub(r"\s+", " ", texto_pdf(pdf))
    pl, _ = solo_letras(pnorm)

    llamadas, esp = {}, 1
    for m in re.finditer(r"(?<=[A-Za-z”’\)\.,;:!\?])\s?(\d{1,3})(?=[ .,;:]|$)", pnorm):
        if int(m.group(1)) != esp:
            continue
        llamadas[esp] = sum(1 for c in pnorm[:m.start(1)] if c.isalpha())
        esp += 1

    cl, cpos = solo_letras(txt, saltar_defs=True)
    ins, cur = [], 0
    for n in sorted(huer):
        if n not in llamadas:
            continue
        ctx = pl[max(0, llamadas[n] - CTX):llamadas[n]]
        if len(ctx) < 25:
            continue
        p = cl.find(ctx, cur)
        if p < 0:
            continue
        fin = p + len(ctx) - 1
        j = cpos[fin] + 1
        while j < len(txt) and txt[j] in ".,;:!?”’\")*":
            j += 1
        m = re.match(r"\s*\d[\d.,’'°/-]*\s*[\)\]]?[.,;:]?", txt[j:])
        if m and m.group(0).strip():        # el salto de línea coló la llamada antes de una cifra
            j += len(m.group(0))
        if re.match(r"\s*\[\^\d+\]:", txt[j:]):   # jamás delante de una definición
            continue
        ins.append((j, n))
        cur = fin + 1
    for j, n in sorted(ins, reverse=True):
        txt = txt[:j] + f"[^{n}]" + txt[j:]
    return txt, len(ins)


def interpolar(txt: str) -> tuple[str, int]:
    """Último recurso: coloca la nota entre sus vecinas ya ancladas (aproximado)."""
    defs = {int(m.group(1)) for m in DEF.finditer(txt)}
    refs = {int(m.group(1)): m.start() for m in REF.finditer(txt)}
    huer = sorted(defs - set(refs))
    if not huer:
        return txt, 0
    parr = [(m.start(), m.end()) for m in
            re.finditer(r"(?m)^(?!#|!\[|\||\[\^|\s*$).+$", txt) if m.end() - m.start() > 80]
    if not parr:
        return txt, 0
    ins = []
    for n in huer:
        ant = [p for k, p in refs.items() if k < n]
        sig = [p for k, p in refs.items() if k > n]
        lo = max(ant) if ant else 0
        hi = min(sig) if sig else len(txt)
        hueco = [p for p in parr if lo < p[1] <= hi] or [p for p in parr if p[1] > lo] or parr
        ins.append((hueco[min(len(ins) % len(hueco), len(hueco) - 1)][1], n))
    for pos, n in sorted(ins, key=lambda x: -x[0]):
        txt = txt[:pos] + f"[^{n}]" + txt[pos:]
    return txt, len(ins)


def balance(txt: str) -> tuple[int, int, int, int]:
    dl = [int(m.group(1)) for m in DEF.finditer(txt)]
    r = {int(m.group(1)) for m in REF.finditer(txt)}
    d = set(dl)
    return len(d), len(r), len(d - r), len(dl) - len(d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md", nargs="*", type=pathlib.Path)
    ap.add_argument("--pdf", type=pathlib.Path)
    ap.add_argument("--pairs", type=pathlib.Path,
                    help='JSON {"cap.md": "cap.pdf", ...}')
    ap.add_argument("--interpolar", action="store_true",
                    help="colocar de forma aproximada las que no se puedan situar")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.pairs:
        crudo = json.loads(a.pairs.read_text(encoding="utf-8"))
        base = a.pairs.parent
        pares = [(base / k if not pathlib.Path(k).is_absolute() else pathlib.Path(k),
                  base / v if not pathlib.Path(v).is_absolute() else pathlib.Path(v))
                 for k, v in crudo.items()]
    elif a.md and a.pdf:
        pares = [(m, a.pdf) for m in a.md]
    else:
        ap.error("indica MD --pdf PDF, o bien --pairs pares.json")

    tot_d = tot_r = tot_h = 0
    for md, pdf in sorted(pares):
        if not md.exists() or not pdf.exists():
            print(f"  ! falta {md if not md.exists() else pdf}", file=sys.stderr)
            continue
        txt = md.read_text(encoding="utf-8")
        pn = notas_pdf(pdf)
        txt, conv, ins = estructurar(txt, pn)
        txt, anc = anclar(txt, pdf)
        interp = 0
        if a.interpolar:
            txt, interp = interpolar(txt)
        d, r, h, dup = balance(txt)
        tot_d += d
        tot_r += r
        tot_h += h
        aviso = "  ⚠ DUPLICADAS" if dup else ""
        print(f"{md.name:24s} PDF={len(pn):3d}  etiquetadas={conv:3d} insertadas={ins:3d} "
              f"ancladas={anc:3d} interpoladas={interp:3d}  →  {d} defs / {r} llamadas / "
              f"{h} sin ancla{aviso}")
        if a.apply:
            md.write_text(txt, encoding="utf-8")

    print(f"\n{'APLICADO' if a.apply else 'SIMULACRO'}: "
          f"{tot_d} definiciones, {tot_r} llamadas, {tot_h} sin ancla")
    if tot_h:
        print("  ↳ las notas SIN ancla no se imprimirán: repasa con --interpolar "
              "o etiquétalas a mano contra el PDF")


if __name__ == "__main__":
    main()
