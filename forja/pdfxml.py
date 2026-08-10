"""forja.pdfxml — leer un PDF con `pdftohtml -xml`, con las trampas ya resueltas.

Por qué existe
--------------
`pdfxml_to_markdown` y `clearscan_to_markdown` atacan patologías distintas —capa
de texto incompleta el uno, fuentes sintéticas de ClearScan el otro— pero
entran al PDF por la misma puerta: `pdftohtml -xml`, que da posición, tamaño y
familia de fuente de cada token. Cada uno había resuelto por su cuenta las tres
mismas cosas, y **cada uno documentaba la misma trampa en su propio docstring**,
que es la señal de que el conocimiento estaba en el sitio equivocado.

Las dos trampas, ambas medidas
------------------------------
1. **Los `<fontspec>` son GLOBALES.** Se declaran donde la fuente aparece por
   primera vez, no en cada página. Construir el mapa por página pierde los ids
   heredados: medido en ClearScan, **el 40 % del texto se quedaba sin estilo**, y
   en un libro donde la cursiva es el contenido eso es perder el aparato. Por eso
   `fontspecs()` recorre el XML ENTERO y acumula.
2. **La cursiva puede venir ABREVIADA en el nombre de la familia.** No siempre
   dice «Italic»: `AdobeTextNYUP-It` es la fuente cursiva de la Library of Arabic
   Literature, y un detector que solo mire «italic»/«oblique» da por redonda toda
   la cursiva del libro **en silencio** — el ratio sale perfecto y el balance de
   notas cuadra. Medido en al-Tilimsānī: 1.558 tramos recuperados al reconocer
   también `-It` y `-Ita`.

Lo que NO se comparte, y está bien así
--------------------------------------
`clearscan` mide la inclinación real de los contornos embebidos porque en un PDF
de ClearScan el `/FontDescriptor` MIENTE (`ItalicAngle` 0 en las 384 fuentes), y
`pdfxml` reconoce la llamada de nota por la línea base alzada o por el enlace.
Eso es cada libro, no infraestructura.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

# Marcas de cursiva en el NOMBRE de la familia, incluidas las abreviaturas.
# El `-it`/`-ita` va anclado a un guion para no casar con «Times» ni «Digital».
_CURSIVA = re.compile(r"italic|oblique|-it\b|-ita\b|-it$|-ita$", re.I)
_NEGRITA = re.compile(r"bold|semibold|-bd\b|-bd$", re.I)


def es_cursiva(familia: str) -> bool:
    """¿El nombre de la familia dice que es cursiva? (trampa 2)."""
    return bool(_CURSIVA.search(familia or ""))


def es_negrita(familia: str) -> bool:
    return bool(_NEGRITA.search(familia or ""))


def ejecuta(pdf: Path | str, primera: int | None = None, ultima: int | None = None,
            *, sin_imagenes: bool = False) -> str:
    """Corre `pdftohtml -xml` y devuelve el XML como texto."""
    cmd = ["pdftohtml", "-xml", "-stdout"]
    if sin_imagenes:
        cmd.append("-i")
    if primera:
        cmd += ["-f", str(primera)]
    if ultima:
        cmd += ["-l", str(ultima)]
    cmd.append(str(pdf))
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"pdftohtml falló: {r.stderr.decode('utf-8', 'replace')[:400]}")
    return r.stdout.decode("utf-8", "replace")


def fontspecs(xml: str) -> dict[str, tuple[float, str]]:
    """id → (tamaño, familia), acumulando sobre el XML ENTERO (trampa 1).

    Se hace con regex a propósito, y no con el árbol: así funciona igual sobre un
    XML completo que sobre un fragmento de una página suelta, que es como lo
    trocea `clearscan` para medir contornos.
    """
    out: dict[str, tuple[float, str]] = {}
    for m in re.finditer(r'<fontspec\s+id="(\d+)"[^>]*size="(-?[\d.]+)"[^>]*'
                         r'family="([^"]*)"', xml):
        out[m.group(1)] = (float(m.group(2)), m.group(3))
    return out


def tokens(xml: str) -> list[dict]:
    """[{num, width, height, toks:[…]}] con estilo ya resuelto por token.

    Cada token trae `size`, `fam`, `bold`, `ital` y `link`. El estilo se decide
    por las etiquetas hijas (`<b>`, `<i>`, `<a>`) Y por el nombre de la familia,
    porque muchas maquetas no emiten las etiquetas y solo cambian de fuente.
    """
    root = ET.fromstring(xml)
    specs = fontspecs(xml)          # global: nunca por página
    paginas = []
    for pg in root.iter("page"):
        toks = []
        for t in pg.iter("text"):
            size, fam = specs.get(t.get("font") or "", (0.0, ""))
            tags = {c.tag for c in t.iter() if c is not t}
            toks.append(dict(
                top=int(t.get("top") or 0), left=int(t.get("left") or 0),
                w=int(t.get("width") or 0), h=int(t.get("height") or 0),
                size=size, fam=fam, txt="".join(t.itertext()),
                # Un `<a>` dentro del token: en los PDF hechos con Calibre desde
                # un EPUB, la llamada de nota es un ENLACE al aparato del final,
                # y ahí el número se LEE, no se cuenta.
                link=("a" in tags),
                bold=("b" in tags) or es_negrita(fam),
                ital=("i" in tags) or es_cursiva(fam),
            ))
        paginas.append(dict(num=int(pg.get("number") or 0), toks=toks,
                            width=float(pg.get("width") or 0),
                            height=float(pg.get("height") or 0)))
    return paginas
