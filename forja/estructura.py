"""forja.estructura — los encabezados y subtítulos que el bisturí no vio.

Por qué existe
--------------
Tres defectos distintos con la misma firma: **el markdown se lee sin sobresaltos
y el ratio global sonríe**, mientras el libro pierde su estructura interna o, en
el peor caso, mil palabras de texto que nadie vuelve a mirar.

Ninguno lo ve el balance de notas, ni el recuento de palabras del archivo, ni una
lectura por encima. Por eso están aquí y no en una advertencia del manual.

1. **Encabezado partido en dos renglones.** Un título centrado en dos líneas: el
   bisturí promueve una y deja la otra como párrafo suelto. Molesto pero visible.
2. **Encabezado en el sitio equivocado**, que es el caro. Si el promovido es el
   SEGUNDO renglón, la primera mitad se queda al final del capítulo anterior y el
   encabezado puede acabar **mil palabras más abajo de donde empieza el capítulo**.
   Entonces el traductor cierra el capítulo donde dice el encabezado y **el tramo
   intermedio no se traduce nunca**. Medido en Ficino, *De vita* III: 1.484
   palabras perdidas, con ratio global 0,98 y ratio de ESE capítulo 0,62. De ahí
   la regla: **la completitud de una traducción se mide POR CAPÍTULO**.
3. **Subtítulo fundido al párrafo.** Cuando el libro marca sus apartados con una
   línea en cursiva y no con cuerpo mayor, el bisturí no los ve y quedan pegados
   al párrafo que abren. El libro entero acaba sin estructura interna y el índice
   solo lista capítulos. Medido en Lehrich: 86 por idioma.
"""
from __future__ import annotations

import re

ENCABEZADO = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
# Un tramo en cursiva al ARRANQUE del párrafo, seguido de prosa en la misma línea.
_SUBTITULO = re.compile(r"^\*([^*\n]{3,80})\*\s+(?=[A-ZÁÉÍÓÚÑ])")
_LEYENDA = re.compile(r"^\**\s*(fig(ura|ure)?|tab(la|le)?|lám(ina)?|plate)\b", re.I)


def titulos_en_minuscula(md: str) -> list[str]:
    """Encabezados que empiezan en minúscula: la señal barata de título partido.

    Un título no empieza en minúscula por gusto. Si lo hace, casi siempre es la
    segunda mitad de uno centrado en dos renglones, y la primera anda suelta al
    final del capítulo anterior.
    """
    out = []
    for m in ENCABEZADO.finditer(md):
        txt = m.group(2).strip().lstrip("*_·—- ")
        if txt and txt[0].islower():
            out.append(m.group(0).strip())
    return out


def encabezados_partidos(md: str) -> list[tuple[str, str]]:
    """(encabezado, huérfano) cuando tras un título va un párrafo en minúscula.

    Es la otra mitad del mismo defecto: aquí el promovido fue el PRIMER renglón y
    el segundo quedó como párrafo suelto justo debajo.

    Al coserlo, la coma depende de la sintaxis: sin coma si es continuación
    genitiva («…del significador» + «del consultante»), con coma si es cláusula
    nueva. Y si la continuación YA está en el encabezado —porque se recompuso
    antes contra el índice impreso— el huérfano se BORRA, no se duplica.
    """
    out = []
    bloques = re.split(r"\n\s*\n", md)
    for i, b in enumerate(bloques[:-1]):
        b = b.strip()
        if not ENCABEZADO.match(b) or "\n" in b:
            continue
        sig = bloques[i + 1].strip()
        if not sig or ENCABEZADO.match(sig):
            continue
        primera = sig.split("\n")[0]
        # un huérfano de título es CORTO y abre en minúscula; un párrafo de
        # cuerpo que empiece en minúscula por casualidad suele ser largo
        if len(primera.split()) <= 12 and primera[:1].islower():
            out.append((b, primera))
    return out


def subtitulos_fundidos(md: str) -> list[tuple[str, str]]:
    """(subtítulo, arranque del párrafo) de los apartados pegados a su prosa.

    Dos guardas que evitan falsos positivos garantizados, ambas medidas:

    * **Las leyendas de figura quedan fuera.** Una regla de «bloque entero en
      cursiva» las promovería a encabezado —5 por idioma en Lehrich—.
    * **Si el párrafo arranca con OTRA cursiva pegada** (`*Character and
      Hieroglyph* *DOP* does not…`), el patrón no dispara: ahí no se puede
      distinguir el subtítulo de un título de obra citado.

    Y antes de promover a `##`, **verifícalo contra el PDF**: un subtítulo real
    aparece como LÍNEA SUELTA en `pdftotext`, y un párrafo que empieza por un
    título de obra en cursiva no. Con esa comprobación salieron 86 de 86.
    """
    out = []
    for b in re.split(r"\n\s*\n", md):
        b = b.strip()
        if not b or b.startswith(("#", ">", "|", "!", "[^")):
            continue
        if _LEYENDA.match(b):
            continue
        m = _SUBTITULO.match(b)
        if not m:
            continue
        resto = b[m.end():].lstrip()
        if resto.startswith("*"):          # otra cursiva pegada: ambiguo
            continue
        if not resto:                      # bloque entero en cursiva: no es esto
            continue
        out.append((m.group(1).strip(), resto[:60]))
    return out


def capitulos_con_deficit(pares, minimo: float = 0.85) -> list[tuple[str, float]]:
    """(nombre, ratio) de los capítulos cuya traducción se queda corta.

    `pares` es un iterable de `(nombre, texto_origen, texto_destino)`.

    Existe porque **el ratio GLOBAL no ve una laguna de capítulo**: en Ficino el
    del libro era 0,98 y el del capítulo perdido, 0,62. Medir por archivo es lo
    único que la destapa.
    """
    out = []
    for nombre, en, es in pares:
        n = len(en.split())
        if n < 200:            # un capítulo muy corto da ratios ruidosos
            continue
        r = len(es.split()) / n
        if r < minimo:
            out.append((nombre, round(r, 3)))
    return out
