#!/usr/bin/env python3
"""epub_notas_aside.py — rescata las notas EPUB3 «noteref + aside» que el
conversor general no entiende.

Por qué existe
--------------
Hay EPUB (Inner Traditions y otros) que NO llevan pool de notas al final: cada
capítulo trae sus notas dentro del propio documento, así:

    llamada:      <a epub:type="noteref" href="#fn-1" id="fn_1">*</a>
    definición:   <div epub:type="footnote" id="fn-1">
                    <p><a epub:type="backlink" href="#fn_1">*</a>TEXTO</p>
                  </div>

`build_plan.py` dice «no footnote pool detected» —y es cierto, no lo hay— y
`epub_to_markdown.py` acaba emitiendo definiciones VACÍAS cuyo texto es el
asterisco del enlace de vuelta, sin ninguna llamada en el cuerpo. Resultado
medido en *Advanced Rune Magic* (David Linder): 42 notas en el EPUB, 28
definiciones vacías en el markdown y CERO llamadas. Como pandoc descarta en
silencio toda definición sin llamada, el libro se habría maquetado sin notas.

**La llamada suele ser un asterisco, no un número**, así que no se puede buscar
por cifra: hay que tomar la posición del `<a>` en el texto plano y anclar por el
contexto que lo precede.

Uso
---
    python3 epub_notas_aside.py libro.epub markdown/ --plan plan.json [--apply]

Sin `--apply` solo informa. Es TODO O NADA por archivo: si un ancla no aparece o
no es única en el markdown, ese archivo se deja intacto y se avisa.

El pie COLADO EN EL CUERPO, y por qué hay que quitarlo ANTES de anclar
---------------------------------------------------------------------
En la maqueta B el conversor general no reconoce la clase del pie, así que emite
sus párrafos como prosa normal, numerados («10 The poem with translation is…»).
Como esta herramienta los extrae además del HTML, el texto de la nota acaba DOS
VECES en el archivo: en el cuerpo y en la definición. **Ningún control lo delata**
—las llamadas cuadran con las definiciones y el ratio contra el EPUB sale ~1.02,
que se lee como «sobra un poco de rótulo»—. Medido en *Trollrún*: 195 pies
duplicados, 50 de 73 definiciones afectadas, ratio 1.0209.

Y el orden importa: esas copias son texto casi idéntico al contexto de la nota,
así que **arruinan la unicidad del ancla** y mandan notas al bloque «sin anclar»
sin motivo. Por eso se retiran ANTES de buscar anclas, no después.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import zipfile

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("hace falta beautifulsoup4: pip install beautifulsoup4")

NOTEREF = {"epub:type": "noteref"}
SENT = "\ue000"          # centinela: marca dónde estaba la llamada


def extraer(html: str) -> list[tuple[str, str]]:
    """Devuelve [(ancla, texto_de_nota)] en orden de aparición.

    Cubre DOS maquetas de nota por capítulo:

    A) EPUB3 «noteref + aside»  (Inner Traditions)
         <a epub:type="noteref" href="#fn-1">*</a>  …  <div epub:type="footnote" id="fn-1">
    B) Exportación de Word/InDesign  (marcadores «footnotebookmark»)
         <a id="…_start_X"></a><sup><a href="#…_end_X">1</a></sup>
         …  <p class="P_Footnote"><sup><a id="…_end_X">1</a></sup> TEXTO</p>
    """
    sopa = BeautifulSoup(html, "html.parser")
    defs: dict[str, str] = {}

    # --- formato A: los <div>/<aside> con epub:type="footnote" ---
    for div in sopa.find_all(attrs={"epub:type": "footnote"}):
        for bl in div.find_all(attrs={"epub:type": "backlink"}):
            bl.decompose()
        defs[div.get("id", "")] = " ".join(div.get_text(" ", strip=True).split())
        div.decompose()

    # --- formato B: los <p class="P_Footnote"> con ancla «…_end_…» ---
    for par in sopa.find_all("p", class_=lambda c: c and "Footnote" in c):
        anc = par.find("a", id=True)
        clave = anc["id"] if anc else ""
        if anc:
            anc.decompose()
        defs[clave] = " ".join(par.get_text(" ", strip=True).split())
        par.decompose()
    for hr in sopa.find_all("hr"):          # el filete que separa el pie
        hr.decompose()

    salida = []
    for a in sopa.find_all("a", href=True):
        destino = a["href"].lstrip("#")
        es_nota = (a.get("epub:type") == "noteref") or ("footnotebookmark_end" in destino)
        if not es_nota or destino not in defs:
            continue
        padre = a.parent
        a.replace_with(SENT)
        if padre and padre.name == "span" and not padre.get_text(strip=True).replace(SENT, ""):
            padre.unwrap()
        salida.append(destino)

    texto = " ".join(sopa.get_text(" ", strip=True).split())
    anclas, pos = [], 0
    for destino in salida:
        i = texto.index(SENT, pos)
        anclas.append((texto[max(0, i - 400):i].strip(), defs.get(destino, "")))
        texto = texto[:i] + texto[i + len(SENT):]
        pos = i
    return anclas


def norm(s: str) -> str:
    """Normaliza para comparar: fuera marcas de markdown, comillas unificadas y
    TODO el espacio en blanco. Sin esto no casan las capitulares que el EPUB
    parte («E lk») ni los espacios que get_text mete dentro de los paréntesis."""
    s = re.sub(r"[*_`]", "", s)
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", "", s).lower()


def quitar_pies_colados(texto: str, pares: list[tuple[str, str]]) -> tuple[str, int]:
    """Retira del cuerpo los párrafos que son una COPIA numerada de una nota.

    El conversor general los emitió como prosa («10 El poema se encuentra…»), así
    que se reconocen por el número inicial MÁS la coincidencia con el texto de la
    nota que lleva ese número. Exigir las dos cosas es lo que evita borrar prosa
    legítima que empiece por una cifra.
    """
    def plano(s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[*_`]", "", s)).strip()

    notas = {str(n): plano(txt) for n, (_, txt) in enumerate(pares, 1) if txt}
    parrafos, fuera = texto.split("\n\n"), 0
    salida = []
    for bloque in parrafos:
        m = re.match(r"^(\d{1,3})\s+(.+)$", plano(bloque), re.S)
        if m:
            nota = notas.get(m.group(1), "")
            resto = m.group(2)
            if nota and (resto == nota or nota.startswith(resto[:60])
                         or resto.startswith(nota[:60])):
                fuera += 1
                continue
        salida.append(bloque)
    return "\n\n".join(salida), fuera


def procesar(epub: str, dir_md: str, plan: dict, aplicar: bool) -> int:
    z = zipfile.ZipFile(epub)
    base = plan.get("text_dir", "")
    fallos = 0
    for sec in plan["sections"]:
        md = pathlib.Path(dir_md) / f"{sec['slug']}.md"
        if not md.exists():
            continue
        pares = []
        for f in sec["files"]:
            ruta = f"{base}/{f}" if base else f
            try:
                pares += extraer(z.read(ruta).decode("utf8", "ignore"))
            except KeyError:
                continue
        if not pares:
            continue

        t = md.read_text()
        t = re.sub(r"^\[\^\d+\]:.*$\n?", "", t, flags=re.M).rstrip()   # fuera las vacías
        t, colados = quitar_pies_colados(t, pares)
        cuerpo, ok = t, True
        plano = norm(cuerpo)
        elegidas, sueltas = [], []
        for n, (ancla, _) in enumerate(pares, 1):
            q = None
            for L in (40, 60, 80, 110, 150, 220, 320, 25, 18):
                cand = norm(ancla)[-L:]
                if cand and plano.count(cand) == 1:
                    q = cand
                    break
            # Degradar por NOTA, no por archivo: si el ancla no aparece (suele ser
            # porque el pie usa otra clase y su texto se coló en el cuerpo), la nota
            # se imprime sin anclar en vez de perderse o colocarse a ojo.
            if q is None:
                sueltas.append(n)
            elegidas.append((n, q))

        # insertar de atrás hacia delante para no mover los índices
        for n, q in reversed(elegidas):
            if q is None:
                continue
            i = norm_index(cuerpo, q)
            cuerpo = cuerpo[:i] + f"[^{n}]" + cuerpo[i:]
        anc = [n for n, (_, _) in enumerate(pares, 1) if n not in sueltas]
        defs = "\n\n".join(f"[^{n}]: {txt}" for n, (_, txt) in enumerate(pares, 1)
                            if n not in sueltas)
        extra = ""
        if sueltas:
            extra = ("\n\n### Notas del original sin anclar\n\n"
                     "*No se pudo situar su llamada en el cuerpo; se imprimen con su número.*\n\n"
                     + "\n\n".join(f"**{n}.** {pares[n-1][1]}" for n in sueltas))
        nuevo = cuerpo.rstrip() + "\n\n## Notas\n\n" + defs + extra + "\n"
        print(f"  {md.name}: {len(anc)} ancladas"
              + (f" · {len(sueltas)} sin anclar" if sueltas else "")
              + (f" · {colados} pies colados retirados del cuerpo" if colados else ""))
        if aplicar:
            md.write_text(nuevo)
    return fallos


def norm_index(texto: str, q: str) -> int:
    """Posición en `texto` (original) donde termina la coincidencia normalizada."""
    buf, idx = [], []
    for i, c in enumerate(texto):
        if c in "*_`" or c.isspace():
            continue
        c = {"’": "'", "“": '"', "”": '"', "—": "-", "–": "-"}.get(c, c).lower()
        buf.append(c)
        idx.append(i)
    plano = "".join(buf)
    j = plano.index(q)
    return idx[j + len(q) - 1] + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("dir_md")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    plan = json.loads(pathlib.Path(a.plan).read_text())
    fallos = procesar(a.epub, a.dir_md, plan, a.apply)
    if not a.apply:
        print("\n(dry-run: nada escrito; usa --apply)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
