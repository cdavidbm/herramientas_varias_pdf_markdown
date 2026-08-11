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


def capitulos_con_deficit(pares, minimo: float = 0.85, maximo: float = 1.15):
    """(nombre, ratio) de las secciones cuyo tamaño se sale del rango esperado.

    `pares` es un iterable de `(nombre, texto_esperado, texto_presente)`.

    Existe por dos razones distintas, y la segunda se aprendió tarde:

    **Por defecto**, porque el ratio GLOBAL no ve una laguna de capítulo: en
    Ficino el del libro era 0,98 y el del capítulo perdido, 0,62. Medir por
    archivo es lo único que la destapa.

    **Por EXCESO**, porque una comprobación de una sola dirección no es una
    comprobación. La versión anterior solo avisaba de ratios bajos, y con eso
    dio por buenas cuatro secciones de Greenbaum que tenían 1,53 · 1,31 · 1,38 ·
    1,41 — es decir, hasta un 53 % de texto de MÁS, porque el aparato de notas
    se había duplicado dentro del cuerpo. Sobrar texto es tan defecto como
    faltar, y se ve igual de poco al leer.
    """
    out = []
    for nombre, esperado, presente in pares:
        n = len(esperado.split())
        if n < 200:            # una sección muy corta da ratios ruidosos
            continue
        r = len(presente.split()) / n
        if not minimo <= r <= maximo:
            out.append((nombre, round(r, 3)))
    return out


def notas_duplicadas_en_cuerpo(cuerpo: str, aparato: str, minimo_palabras: int = 8,
                               muestra: int = 150) -> int:
    """Cuántas definiciones del aparato aparecen TAMBIÉN en el cuerpo.

    Es el defecto que produce reponer un aparato perdido sin reconstruir el
    cuerpo: la misma nota queda dos veces, una en su sitio y otra empotrada en
    la prosa. No lo denuncia el balance de notas —las etiquetas cuadran—, ni el
    recuento de palabras si solo se mira que no falte.

    Medido en Greenbaum al reparar un truncamiento: 43 de 70 notas duplicadas en
    el capítulo 1 y 102 de 200 en el capítulo 6, mientras los capítulos intactos
    daban 0. Ese contraste es la señal: en un libro sano el número es cero, no
    «bajo».
    """
    plano = re.sub(r"\s+", " ", cuerpo)
    n = 0
    for linea in aparato.split("\n"):
        if len(linea.split()) < minimo_palabras:
            continue
        # se compara SIN el número de nota: en el cuerpo la frase aparece sin él
        limpia = re.sub(r"^\s*(?:\[\^)?\d{1,3}\]?[.:)]?\s+", "", re.sub(r"\s+", " ", linea)).strip()
        if len(limpia) >= 30 and limpia[:50] in plano:
            n += 1
        muestra -= 1
        if muestra <= 0:
            break
    return n
