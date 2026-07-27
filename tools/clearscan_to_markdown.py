#!/usr/bin/env python3
"""clearscan_to_markdown.py — PDF de **Acrobat ClearScan** -> markdown CON CURSIVAS.

ClearScan (Acrobat «Paper Capture») no deja el OCR como capa invisible: sustituye el
texto escaneado por **fuentes sintéticas**, una por «racimo de formas». El resultado se
extrae bien con `pdftotext`… pero **pierde todo el estilo**, y en una edición académica
la cursiva es información (términos técnicos, transliteraciones, títulos de obra, y a
veces los propios subapartados). Se pierde SIN AVISAR, que es lo peor.

Por qué no sirve ninguna vía normal:
  · `pdffonts` no da ni un nombre con «italic»: son `Fd<n>-Identity-H`.
  · `pdftohtml -xml` emite **cero** marcas `<i>`.
  · el `/FontDescriptor` MIENTE: `ItalicAngle` = 0 y `Flags` idéntico en todas.

Lo que sí es verdad: **los contornos están inclinados de verdad**. Este script mide la
inclinación real de cada fuente embebida (mediana del desplazamiento horizontal entre lo
alto y lo bajo de cada glifo) y con eso decide redonda vs. cursiva. Medido en *The Search
of the Heart* (Dykes, 239 pp): distribución claramente bimodal —92.8 % redonda, 4.9 %
cursiva, 2.3 % en zona gris (que resultaron ser los TITULILLOS en versalita cursiva, que
se descartan igual)—, y validado contra la imagen de una página cuyo estilo se conocía.

Requiere: `pdftohtml` (poppler), `pikepdf`, `fontTools`.

Uso:
    python3 clearscan_to_markdown.py libro.pdf --plan plan.json --out ./en
    python3 clearscan_to_markdown.py libro.pdf --pages 110-112          # a stdout, para mirar
"""
import argparse
import collections
import io
import json
import pathlib
import re
import statistics
import subprocess
import sys
import unicodedata

# ---------------------------------------------------------------- inclinación de fuentes

def _puntos(charstring):
    from fontTools.pens.recordingPen import RecordingPen
    pen = RecordingPen()
    charstring.draw(pen)
    pts = []
    for _op, args in pen.value:
        for a in args:
            if isinstance(a, tuple) and len(a) == 2:
                pts.append(a)
    return pts


def _inclinacion_glifo(pts):
    """Desplazamiento horizontal por unidad vertical entre la banda alta y la baja."""
    ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys)
    if hi - lo < 50:
        return None
    banda = (hi - lo) * 0.18
    arr = [p[0] for p in pts if p[1] >= hi - banda]
    aba = [p[0] for p in pts if p[1] <= lo + banda]
    if len(arr) < 2 or len(aba) < 2:
        return None
    return (statistics.median(arr) - statistics.median(aba)) / (hi - lo)


def mapa_inclinacion(pdf_path, cache=None, min_glifos=4):
    """{nombre_fuente: inclinación}. Se cachea: medir 350 fuentes tarda minutos."""
    if cache and pathlib.Path(cache).exists():
        return json.loads(pathlib.Path(cache).read_text(encoding="utf-8"))
    import pikepdf
    from fontTools.cffLib import CFFFontSet
    pdf = pikepdf.open(str(pdf_path))
    mapa = {}
    for obj in pdf.objects:
        try:
            if obj.get("/Type") != "/FontDescriptor":
                continue
            nombre = str(obj.get("/FontName", "")).lstrip("/")
            ff = obj.get("/FontFile3")
            if not nombre or ff is None:
                continue
            cff = CFFFontSet()
            cff.decompile(io.BytesIO(bytes(ff.read_bytes())), None)
            cs = cff[cff.fontNames[0]].CharStrings
            incl = []
            for g in cs.keys():
                try:
                    v = _inclinacion_glifo(_puntos(cs[g]))
                except Exception:
                    continue
                if v is not None:
                    incl.append(v)
            if len(incl) >= min_glifos:
                mapa[nombre] = round(statistics.median(incl), 4)
        except Exception:
            continue
    if cache:
        pathlib.Path(cache).write_text(json.dumps(mapa, indent=0, sort_keys=True),
                                       encoding="utf-8")
    return mapa

# ---------------------------------------------------------------- lectura del XML

Span = collections.namedtuple("Span", "top left width height size cursiva texto")


def paginas_xml(pdf_path, ini=None, fin=None):
    """[(nº_página, [Span…])]. Los `fontspec` de pdftohtml son GLOBALES y se declaran
    donde aparecen por primera vez: un mapa por página pierde los ids heredados de
    páginas anteriores (medido: el 40 % del texto se quedaba sin estilo)."""
    cmd = ["pdftohtml", "-xml", "-stdout", "-i"]
    if ini:
        cmd += ["-f", str(ini)]
    if fin:
        cmd += ["-l", str(fin)]
    cmd.append(str(pdf_path))
    xml = subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")
    spec = {m[0]: (m[1], m[2]) for m in
            re.findall(r'<fontspec id="(\d+)"[^>]*size="(\d+)"[^>]*family="([^"]*)"', xml)}
    return xml, spec


def _desescapa(s):
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#34;", '"'),
                 ("&quot;", '"'), ("&apos;", "'"), ("&#39;", "'")):
        s = s.replace(a, b)
    return s

# ---------------------------------------------------------------- montaje del markdown

RUNNING = re.compile(r"^\s*(BOOK\s|APPENDIX\s|CHAPTER\s|INTRODUCTION\b|\d{1,4}\s*$)", re.I)


def es_titulillo(linea_texto, titulo_corto=""):
    t = linea_texto.strip()
    if not t:
        return False
    if re.fullmatch(r"\d{1,4}", t):
        return True
    letras = [c for c in t if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) > 0.75 and len(t) > 8:
        return True
    if titulo_corto and titulo_corto.lower()[:18] in t.lower():
        return True
    return False


def spans_de_pagina(pg_xml, spec, umbral):
    spans = []
    for m in re.finditer(
            r'<text\s+top="(-?\d+)"\s+left="(-?\d+)"\s+width="(-?\d+)"\s+height="(-?\d+)"'
            r'\s+font="(\d+)"[^>]*>(.*?)</text>', pg_xml, re.S):
        top, left, w, h, fid, cont = m.groups()
        txt = _desescapa(cont)
        if not txt.strip():
            continue
        size, fam = spec.get(fid, ("0", ""))
        base = fam.split("-")[0]
        spans.append(Span(int(top), int(left), int(w), int(h), int(size),
                          umbral.get(base, False), txt))
    return spans


def agrupa_lineas(spans, tol=4):
    """Spans -> líneas por coordenada vertical (tolerancia en px)."""
    lineas = []
    for s in sorted(spans, key=lambda z: (z.top, z.left)):
        if lineas and abs(s.top - lineas[-1][0]) <= tol:
            lineas[-1][1].append(s)
        else:
            lineas.append((s.top, [s]))
    return [(t, sorted(g, key=lambda z: z.left)) for t, g in lineas]


def corta_notas(lineas):
    """(cuerpo, notas). El aparato es el bloque FINAL de líneas de cuerpo menor.

    El primer intento fue partir por el hueco vertical antes del pie —que es la señal
    robusta cuando el tamaño no distingue—, pero aquí falla en muchas páginas (las que
    van llenas hasta abajo, sin hueco) y entonces las notas se quedan DENTRO del cuerpo
    y la numeración se reconstruye mal. En un ClearScan sí hay señal de tamaño fiable:
    la prosa va a 12-13 y el aparato a 10-11, así que se recorre de abajo arriba mientras
    las líneas sean menores que la mediana del cuerpo."""
    if len(lineas) < 4:
        return lineas, []
    def tam(g):
        return statistics.median([sp.size for sp in g])
    tams = [tam(g) for _t, g in lineas]
    cuerpo_tam = statistics.median(tams)
    if cuerpo_tam <= 0:
        return lineas, []
    i = len(lineas)
    while i > 0 and tams[i - 1] < cuerpo_tam:
        i -= 1
    # exigir que el bloque final sea de verdad un pie: ha de empezar con un volado
    # (span pequeño pegado al margen), no ser solo la última línea corta de un párrafo
    if i >= len(lineas):
        return lineas, []
    izq = min(g[0].left for _t, g in lineas)
    sp0 = lineas[i][1][0]
    if not (sp0.left <= izq + 6 and re.match(r"\s*[0-9lIioO]", sp0.texto)):
        return lineas, []
    if i < len(lineas) * 0.25:      # no puede ser aparato tres cuartos de página
        return lineas, []
    return lineas[:i], lineas[i:]


def texto_de_linea(grupo):
    """Une los spans de una línea marcando las cursivas con `*…*`."""
    partes, abierto = [], False
    for sp in grupo:
        t = sp.texto
        if sp.cursiva and not abierto:
            partes.append("*"); abierto = True
        elif not sp.cursiva and abierto:
            partes.append("*"); abierto = False
        partes.append(t)
    if abierto:
        partes.append("*")
    s = "".join(partes)
    s = re.sub(r"\*\s*\*", " ", s)          # cursivas contiguas: fusionar
    # ClearScan crea alguna fuente «racimo» que MEZCLA estilos (los fragmentos que el OCR
    # reconoció peor). Eso parte una cursiva en dos con un trocito redondo en medio
    # («*Chapter *II.3.1: *Relation…*»). Si el trozo intercalado es corto, se absorbe.
    s = re.sub(r"\*(?P<a>[^*]+)\*(?P<mid>[^*]{1,14}?)\*(?P<b>[^*]+)\*",
               lambda m: "*%s%s%s*" % (m.group("a"), m.group("mid"), m.group("b")), s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


# Dykes numera los párrafos con corchetes: «[3] And so, having seen…».
NUM_PARR_RE = re.compile(r"^\s*\[\d+[a-z]?\]")

HEAD_RE = re.compile(r"^\s*Chapter\s+([IVXivx0-9]+(?:\.\s?[0-9]+)*)\s*[:.]", re.I)


def como_encabezado(txt):
    """«Chapter II.3.1: …» -> encabezado markdown del nivel que le toca por su numeración.

    Se decide por el TEXTO y no por la tipografía: en este PDF los subapartados van en
    cursiva y los apartados en negrita, pero el `[3]` que abre párrafo comparte cuerpo y
    negrita con los apartados, así que la geometría sola confundiría ambas cosas."""
    m = HEAD_RE.match(txt)
    if not m:
        return None
    niveles = len(re.findall(r"[0-9]+", m.group(1))) + 1
    return "#" * min(max(niveles, 2), 5) + " " + txt.strip()


def parrafos(lineas, sangria_extra=6):
    """Líneas -> párrafos. Abre párrafo cuando la línea entra SANGRADA respecto a la
    mediana del margen izquierdo (señal estable aunque el OCR mueva un poco el texto)."""
    if not lineas:
        return []
    # El margen de referencia es el de las líneas de CONTINUACIÓN, que es el más a la
    # izquierda; las que ABREN párrafo van sangradas a la derecha. Por eso se toma un
    # percentil BAJO y no la mediana: con la mediana el umbral cae en mitad de la
    # sangría y no dispara nunca (medido: 28 líneas -> 1 solo párrafo).
    lefts = sorted(g[0].left for _t, g in lineas)
    izq = lefts[max(0, int(len(lefts) * 0.2))]
    textos = [texto_de_linea(g) for _t, g in lineas]
    out, actual = [], []
    for i, (_t, g) in enumerate(lineas):
        txt = textos[i]
        if not txt:
            continue
        enc = como_encabezado(txt)
        if enc:
            if actual:
                out.append(" ".join(actual)); actual = []
            out.append(enc)
            continue
        # ¿abre párrafo?
        #  (a) el propio texto lo dice: Dykes numera los párrafos «[3]», «[4]»…
        #  (b) sangría RELATIVA: la 1.ª línea de un párrafo entra más que la 2.ª. Mirar
        #      solo la sangría absoluta rompe los párrafos en BLOQUE (las citas y los
        #      párrafos numerados van con ambos márgenes metidos, así que TODAS sus
        #      líneas superan el margen base y se partían una a una).
        sig = lineas[i + 1][1][0].left if i + 1 < len(lineas) else None
        abre = bool(NUM_PARR_RE.match(txt)) or (
            sig is not None and g[0].left > sig + sangria_extra)
        if actual and abre:
            out.append(" ".join(actual)); actual = [txt]
        else:
            actual.append(txt)
    if actual:
        out.append(" ".join(actual))
    return [re.sub(r"\s+", " ", p).strip() for p in out if p.strip()]


def une_guiones(parrs):
    """Rehace las palabras partidas por guion al final de renglón.

    Ojo al GUION SUAVE (U+00AD): ClearScan lo emite tal cual, así que un regex que solo
    mire `-` deja «un\u00adcovering» sin unir y encima con un carácter invisible dentro."""
    out = []
    for p in parrs:
        p = re.sub(r"(\w)[-\u00ad]\s+(\w)", r"\1\2", p)
        p = p.replace("\u00ad", "")
        out.append(p)
    return out


def convierte(pdf, ini, fin, incl, umbral_incl, titulo_corto):
    xml, spec = paginas_xml(pdf, ini, fin)
    es_cursiva = {f: (v > umbral_incl) for f, v in incl.items()}
    cuerpo_out, notas_out, no_puestas = [], [], []
    for pg in re.split(r"<page ", xml)[1:]:
        spans = spans_de_pagina(pg, spec, es_cursiva)
        if not spans:
            continue
        lineas = agrupa_lineas(spans)
        # fuera el titulillo (1.ª línea) y el folio suelto
        while lineas and es_titulillo(texto_de_linea(lineas[0][1]), titulo_corto):
            lineas.pop(0)
        cuerpo, notas = corta_notas(lineas)
        parr = une_guiones(parrafos(cuerpo))
        nn = separa_notas(notas)
        # Las llamadas se sitúan PÁGINA A PÁGINA, no sobre la sección entera: la llamada
        # de una nota está en la misma página que su definición, así que el espacio de
        # búsqueda es mínimo. Buscando sobre todo el capítulo, una sola coincidencia falsa
        # adelanta el puntero y arrastra a TODAS las siguientes (medido: 50 de 99 notas
        # sin situar en el Libro I, y justo las altas).
        parr, faltan = inserta_llamadas(parr, [n for n, _ in nn])
        cuerpo_out += parr
        notas_out += nn
        no_puestas += faltan
    # una nota puede continuar de una página a la siguiente: si la primera de una página
    # repite el número de la última de la anterior, es su continuación, no una nota nueva
    fundidas = []
    for n, txt in notas_out:
        if fundidas and n <= fundidas[-1][0]:
            fundidas[-1] = (fundidas[-1][0], fundidas[-1][1] + " " + txt)
        else:
            fundidas.append((n, txt))
    fundidas = [(n, " ".join(une_guiones([txt]))) for n, txt in fundidas]
    return cuerpo_out, fundidas, sorted(set(no_puestas))



# ---------------------------------------------------------------- aparato de notas

# El OCR de ClearScan destroza los volados: «12;» por 125, «l20» por 120, «S» por 5…
_OCR_DIG = str.maketrans({"l": "1", "I": "1", "i": "1", "|": "1", "O": "0", "o": "0",
                          "S": "5", "s": "5", ";": "", ":": "", ".": "", ",": "",
                          "'": "", "`": "", "\u00b0": "0"})


def _num_ocr(s):
    """«12;» -> 125? No: devuelve los dígitos que se puedan leer, o None."""
    d = "".join(c for c in s.translate(_OCR_DIG) if c.isdigit())
    return int(d) if d else None


def separa_notas(lineas_notas):
    """Aparato -> [(nº, texto)]. Una nota EMPIEZA cuando la línea abre con un span
    pegado al margen y de cuerpo MENOR que el del texto de nota (el volado).

    Los volados mal reconocidos se reparan con la CADENA CONSECUTIVA: si el anterior
    fue n, el siguiente arranque vale n+1 aunque su OCR diga «12;» o «''»."""
    if not lineas_notas:
        return []
    tam = [sp.size for _t, g in lineas_notas for sp in g]
    tam_txt = statistics.median(tam)
    izq = min(g[0].left for _t, g in lineas_notas)
    notas, actual, num = [], [], None
    for _t, g in lineas_notas:
        sp0 = g[0]
        # ClearScan a veces FUNDE el volado con el principio del texto de la nota en un
        # solo span («124  This refers to…»). Por eso no basta con exigir un span corto:
        # se buscan los dígitos INICIALES y se parte ahí.
        m0 = re.match(r"\s*([0-9lIioOSs;:'`|]{1,4})\s+(.*)$", sp0.texto)
        arranque = (sp0.left <= izq + 4 and sp0.size < tam_txt and m0 is not None
                    and _num_ocr(m0.group(1)) is not None)
        if arranque:
            if actual:
                notas.append((num, " ".join(actual)))
            num = _num_ocr(m0.group(1))
            resto = m0.group(2).strip()
            actual = ([resto] if resto else []) + (
                [texto_de_linea(g[1:])] if len(g) > 1 else [])
        else:
            actual.append(texto_de_linea(g))
    if actual:
        notas.append((num, " ".join(actual)))
    # reparar la numeración por la cadena
    salida, esperado = [], None
    for n, txt in notas:
        if esperado is not None and (n is None or abs(n - esperado) > 3):
            n = esperado
        elif n is None:
            n = 1
        salida.append((n, re.sub(r"\s+", " ", txt).strip()))
        esperado = n + 1
    return salida


# Candidato a llamada: grupo de cifras PEGADO a una palabra o a un signo de puntuación
# —nunca una cifra suelta, que sería una cantidad del propio texto.
# Debe EMPEZAR por una cifra de verdad y no continuar en letra. Admitir `l`/`I` como
# dígito inicial parecía buena idea (el OCR confunde 1 con l) pero convierte la «l» de
# cualquier palabra en una llamada: medido, «detail what» salía como «detai[^120]what».
# Dos formas: empezar por cifra de verdad, o por `l`/`I` (el OCR las confunde con el 1)
# PERO seguida de al menos dos cifras reales. Esa guarda es la que evita el desastre:
# admitir `l` suelta convierte la de cualquier palabra en llamada («detail what» salía
# como «detai[^120]what»); exigiendo «l» + 2 cifras, «signsl25» sí se reconoce.
CAND_RE = re.compile(r"(?<=[A-Za-zÀ-ÿ.,;:!?)\]])[ ]?((?:[0-9][0-9lI ]{0,4}|[lI][0-9]{2,3}))"
                     r"(?![A-Za-z0-9])")


def _parecido(cand, n):
    """¿Este grupo de cifras puede ser el volado nº n? El OCR de ClearScan les quita y
    les añade caracteres («1211» por 120, «12;» por 125), así que se compara con holgura."""
    d = "".join(c for c in cand.translate(_OCR_DIG) if c.isdigit())
    if not d or abs(len(d) - len(str(n))) > 1:
        return False
    if d == str(n):
        return True
    s = str(n)
    if d.startswith(s) or s.startswith(d[:len(s)]):
        return True
    # El escaneo de este libro trae el MARGEN IZQUIERDO RECORTADO en muchas páginas y se
    # come la primera cifra del volado: un «24» queda impreso como «4». Por eso el
    # candidato puede ser un SUFIJO del número esperado.
    if len(d) < len(s) and s.endswith(d):
        return True
    try:
        return abs(int(d[:len(s)]) - n) <= 1
    except ValueError:
        return False


def inserta_llamadas(parrafos_cuerpo, numeros):
    """Mete `[^N]` en el cuerpo. Devuelve (párrafos, no_situadas).

    NO se busca cada número por su valor: los volados salen mutilados y así casi ninguno
    casaría. Se alinean POR ORDEN los candidatos con la lista de notas —que es una
    secuencia consecutiva conocida— y solo se acepta un candidato si además se parece.
    Es deliberadamente conservador: antes dejar una llamada sin poner (y reportarla) que
    convertir en nota una cifra de la prosa."""
    texto = "\n\n".join(parrafos_cuerpo)
    no_situadas, desplazamiento = [], 0
    pos = 0
    for n in numeros:
        colocada = False
        for m in CAND_RE.finditer(texto, pos):
            if _parecido(m.group(1), n):
                marca = "[^%d]" % n
                texto = texto[:m.start(1)] + marca + texto[m.end(1):]
                pos = m.start(1) + len(marca)
                colocada = True
                break
        if not colocada:
            no_situadas.append(n)
    return texto.split("\n\n"), no_situadas


def slug(s, n):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return f"{n:02d}_" + re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--plan", help="plan.json de La Forja (secciones con pages [ini,fin])")
    ap.add_argument("--pages", help="rango suelto «110-112» (salida por stdout)")
    ap.add_argument("--out", default="./en", help="carpeta de salida (con --plan)")
    ap.add_argument("--slant-cache", default=None,
                    help="JSON donde cachear la inclinación medida (def: junto al PDF)")
    ap.add_argument("--umbral", type=float, default=0.12,
                    help="inclinación a partir de la cual se considera CURSIVA (def: 0.12)")
    ap.add_argument("--titulo-corto", default="",
                    help="trozo del titulillo para reconocerlo y quitarlo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pdf = pathlib.Path(a.pdf)
    cache = a.slant_cache or str(pdf.with_suffix("")) + ".slant.json"
    sys.stderr.write("midiendo la inclinación de las fuentes embebidas…\n")
    incl = mapa_inclinacion(pdf, cache)
    n_it = sum(1 for v in incl.values() if v > a.umbral)
    sys.stderr.write(f"  {len(incl)} fuentes; {n_it} por encima de {a.umbral} (cursivas)\n")

    if a.pages:
        ini, _, fin = a.pages.partition("-")
        cuerpo, notas, no_puestas = convierte(pdf, int(ini), int(fin or ini), incl,
                                              a.umbral, a.titulo_corto)
        print("\n\n".join(cuerpo))
        if notas:
            print("\n")
            print("\n".join("[^%d]: %s" % (n, txt) for n, txt in notas))
        if no_puestas:
            sys.stderr.write("llamadas no situadas: %s\n" % no_puestas)
        return

    if not a.plan:
        sys.exit("hace falta --plan o --pages")
    plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8"))
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for i, sec in enumerate(plan["sections"], 1):
        p0, p1 = sec["pages"]
        cuerpo, notas, no_puestas = convierte(pdf, p0, p1, incl, a.umbral, a.titulo_corto)
        md = f"# {sec['title']}\n\n" + "\n\n".join(cuerpo)
        if notas:
            md += "\n\n" + "\n".join("[^%d]: %s" % (n, txt) for n, txt in notas)
        # Nada se pierde en silencio: una definición SIN llamada no se imprime en el PDF,
        # así que las que no se pudieron situar quedan anotadas para la pasada manual.
        if no_puestas:
            md += ("\n\n<!-- LLAMADAS SIN SITUAR (definición sin [^N] en el cuerpo): %s -->"
                   % ", ".join(str(n) for n in no_puestas))
        huerfanas = len(no_puestas)
        destino = out / (sec.get("slug") or slug(sec["title"], i)) + ".md" \
            if False else out / ((sec.get("slug") or slug(sec["title"], i)) + ".md")
        print(f"  {destino.name}: {len(cuerpo)} párrafos, {len(notas)} notas"
              + (f", {huerfanas} llamadas SIN situar: {no_puestas[:8]}" if huerfanas else ""))
        if not a.dry_run:
            destino.write_text(md + "\n", encoding="utf-8")
    if a.dry_run:
        print("\n(dry-run: nada escrito)")


if __name__ == "__main__":
    main()
