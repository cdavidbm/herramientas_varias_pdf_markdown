#!/usr/bin/env python3
"""
pdf_rich_to_markdown.py — Extrae un PDF DIGITAL a markdown conservando las
**cursivas y negritas**, que `pdftotext` y Docling tiran a la basura.

Por qué
-------
En un texto académico la cursiva NO es decoración: marca términos técnicos,
transliteraciones y títulos de obra. Dykes, por ejemplo, italiza los términos
técnicos «so the reader can track them» — perder la cursiva es perder ese aparato.
La información está en el PDF (fuentes `…-Italic` / `…-Bold` embebidas); solo hay
que leerla con pdfminer en vez de pedir texto plano.

Qué hace
--------
  * Lee cada línea carácter a carácter con pdfminer y agrupa los tramos por fuente:
    los de fuente *Italic* salen como `*texto*`, los *Bold* como `**texto**`.
  * Reconstruye los espacios por los huecos en x (los PDF de Calibre posicionan
    palabra a palabra y `get_text()` a secas las pega o mete tabuladores).
  * **Detecta las páginas a 2 columnas** y saca cada columna entera por separado,
    en vez de fundirlas línea a línea (ver abajo). Con `--mark-columns` las etiqueta.
  * Con `--footnotes`, **separa las notas al pie por CUERPO DE LETRA** (ver abajo):
    las llamadas salen como `[^N]` y las notas como definiciones `[^N]:`.
  * Reflowa las líneas en párrafos por el salto vertical entre ellas (`--gap`).
  * Ordena por posición (arriba→abajo) y no por el orden interno del PDF.

Las notas al pie (`--footnotes`)
--------------------------------
Donde `footnotes_rebuild.py` tiene que ADIVINAR por patrones de texto, un PDF digital
lo dice literalmente: cuerpo 11.8pt, notas 9.6pt, número de llamada 6pt. Se separan
por geometría, sin heurística — y así una lista numerada en prosa («4 What is
ascending…»), que al adivinar se confunde con una nota, aquí ni se roza: va en 11.8.

Tres cosas lo hacen fiable:

  * El número de llamada va **volado**, con la línea base tan alta que forma una FILA
    APARTE. Se funde con el renglón de abajo y se reordena por x (`merge_raised`).
    Si no, cuando dos notas comparten renglón sus dos números caen juntos («3 … 4») y
    el 4 acaba dentro del texto de la nota 3.
  * «Volado» se mide con un umbral MÁS DURO que «pequeño» (`RAISED` vs `SMALL`): una
    nota compuesta en cuerpo algo menor que sus vecinas se tomaría por volado y su
    texto saldría entrelazado carácter a carácter con el de la nota siguiente.
  * Como el número se reconoce por CUERPO y no por «la línea empieza con cifra», los
    años y grados que citan las notas no fingen ser notas.

La numeración suele reiniciar en cada obra, así que conviene correrlo **una vez por
obra** con `--first/--last`: cada archivo se lleva sus notas y la secuencia se valida
sola (la herramienta avisa de qué números faltan).

Las columnas (por qué no basta con mirar el hueco)
--------------------------------------------------
Un texto paralelo (original a la izquierda, traducción a la derecha) se destruye si
se lee línea a línea: salen frases mestizas que mezclan las dos versiones. Para
evitarlo hay que encontrar el CANAL entre columnas, y ahí hay tres trampas:

  1. **pdfminer ya fusiona las columnas** en una sola línea cuando el canal es
     estrecho. Si buscas el canal en las líneas que él te da, ya no existe. Por eso
     las filas se reconstruyen aquí desde los CARACTERES.
  2. **El canal puede ser estrechísimo** (7pt en un libro compuesto apretado: menos
     que algunos espacios entre palabras). Filtrar por ancho no sirve.
  3. **La prosa justificada finge canales**: al justificar se estiran los espacios y,
     por azar, muchas filas tienen un hueco ancho casi a la misma x.

Lo que de verdad delata a una columna es que **nadie cruza el canal**: se vota la x
del hueco fila a fila, y luego se exige que dentro del bloque que vota casi ninguna
fila lo atraviese. Los títulos y las notas al pie sí lo cruzan, pero caen fuera del
bloque (arriba o abajo) y se emiten aparte como «ancho completo». Una fila que cruza
el canal NUNCA se parte, para no cortar una palabra por la mitad.

Límites honestos
----------------
Solo PDF digitales (un escaneo no tiene nombres de fuente: ahí no hay señal).
Solo 2 columnas: a 3+ (algunos índices) se queda en una y respeta el orden de lectura.
`--footnotes` exige que las notas vayan AL PIE en cuerpo menor. En un PDF reflujado
(Calibre) van intercaladas en el texto y en el mismo cuerpo: ahí no hay señal que
leer y toca `footnotes_rebuild.py`.

Uso
---
    python3 pdf_rich_to_markdown.py libro.pdf --out crudo.md
    python3 pdf_rich_to_markdown.py libro.pdf --out x.md --first 86 --last 92
    python3 pdf_rich_to_markdown.py libro.pdf --out x.md --gap 1.6   # +/- párrafos
    python3 pdf_rich_to_markdown.py libro.pdf --out x.md --mark-columns  # texto paralelo
    python3 pdf_rich_to_markdown.py libro.pdf --out x.md --columns 1     # no separar
    python3 pdf_rich_to_markdown.py libro.pdf --out x.md --first 87 --last 136 \
            --footnotes                       # una obra, con sus notas [^N]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


SMALL = 0.88           # <= cuerpo_del_texto * esto = letra pequeña (nota al pie)

# Un VOLADO (el número de la llamada) es mucho más pequeño que su texto: ~62% (6pt
# sobre 9.6). Pero una nota suelta puede venir compuesta en cuerpo algo menor que
# sus vecinas —8.3 sobre 9.6, un 86%— y con el umbral de SMALL se tomaría por
# volado: su texto se acumularía con los números y, al reordenar por x, saldría
# ENTRELAZADO carácter a carácter con el de la nota siguiente. 0.75 separa las dos
# poblaciones (62% ≪ 75% ≪ 86%) sin tocar ninguna.
RAISED = 0.75


def _spans(chars, body: float | None = None, ratio: float = SMALL):
    """Agrupa caracteres consecutivos por estilo -> [(estilo, pequeña, texto), …].
    estilo: '' normal | 'i' cursiva | 'b' negrita | 'bi' negrita+cursiva.
    pequeña: el carácter va en cuerpo menor (volado de llamada) — solo si se pasa
    `body`, el cuerpo del texto corrido."""
    out = []
    for c in chars:
        fn = (c.fontname or "")
        low = fn.lower()
        st = ("b" if "bold" in low else "") + ("i" if ("italic" in low or "oblique" in low) else "")
        sm = bool(body) and c.size <= body * ratio
        ch = c.get_text()
        if out and out[-1][0] == st and out[-1][1] == sm:
            out[-1][2].append(ch)
        else:
            out.append([st, sm, [ch]])
    return [(st, sm, "".join(t)) for st, sm, t in out]


def detect_body_size(pdf: Path, sample: int = 12) -> float | None:
    """Cuerpo de letra del texto corrido = el tamaño más frecuente.

    Se mide sobre una muestra repartida por el libro (no solo el principio, que
    suele ser portada e índice). Sirve de referencia para saber qué es «pequeño»:
    las notas al pie y los volados de llamada.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTChar
    from collections import Counter
    from pdfminer.pdfpage import PDFPage

    with open(pdf, "rb") as fh:
        total = sum(1 for _ in PDFPage.get_pages(fh))
    step = max(1, total // sample)
    want = list(range(0, total, step))[:sample]
    sizes: Counter = Counter()
    for page in extract_pages(str(pdf), page_numbers=want):
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for line in el:
                if not hasattr(line, "__iter__"):
                    continue
                for c in line:
                    if isinstance(c, LTChar) and c.get_text().strip():
                        sizes[round(c.size, 1)] += 1
    return sizes.most_common(1)[0][0] if sizes else None


def _wrap(st: str, txt: str) -> str:
    """Envuelve el tramo en su marca markdown, dejando fuera los espacios de los
    bordes (`* texto *` no es cursiva en markdown; `*texto*` sí)."""
    if not st or not txt.strip():
        return txt
    lead = txt[:len(txt) - len(txt.lstrip())]
    trail = txt[len(txt.rstrip()):]
    core = txt.strip()
    mark = {"i": "*", "b": "**", "bi": "***"}[st]
    return f"{lead}{mark}{core}{mark}{trail}"


def line_markdown(chars, body: float | None = None,
                  ratio: float = SMALL) -> str:
    """Texto de una línea con las cursivas/negritas marcadas y los espacios
    reconstruidos por los huecos en x.

    Con `body` (el cuerpo del texto corrido), un tramo de CIFRAS en letra menor es
    un volado de llamada y sale como `[^N]`. OJO: no pasar `body` al componer una
    NOTA AL PIE — ahí todo va en letra menor y cada cifra del texto (un año, un
    grado) se convertiría en un marcador.
    """
    # 1) reconstruir espacios: si el hueco supera ~1/4 del cuerpo, va un espacio
    pieces, prev = [], None
    for c in chars:
        if prev is not None and c.x0 - prev > c.size * 0.25 and not c.get_text().isspace():
            pieces.append(" ")
        pieces.append(None)          # marcador de posición; el texto sale de _spans
        prev = c.x1
    # 2) estilos: se recorre en paralelo insertando los espacios calculados
    out, i = [], 0
    for st, sm, txt in _spans(chars, body, ratio):
        buf = []
        for ch in txt:
            while i < len(pieces) and pieces[i] == " ":
                buf.append(" ")
                i += 1
            buf.append(ch)
            i += 1
        piece = "".join(buf)
        if sm and re.search(r"\d", piece):
            # Un tramo volado puede traer VARIOS números y puntuación pegada
            # («216.217», «.215»): cuando dos notas comparten renglón, sus números
            # y el punto que cierra la primera caen en la misma fila alzada. Exigir
            # que el tramo sea SOLO cifras dejaba «.217» como texto plano y perdía
            # la nota. Se convierte cada racha de cifras y se respeta lo demás.
            out.append(re.sub(r"\d{1,3}", lambda m: f"[^{int(m.group())}]", piece))
        else:
            out.append(_wrap(st, piece))
    s = "".join(out)
    s = s.replace("\t", " ")
    return re.sub(r"[  ]{2,}", " ", s).strip()


ROW_TOL = 3.0          # dos caracteres son de la misma línea si su base dista < esto
MIN_GUTTER = 5.0       # hueco mínimo, en puntos, para considerarlo canal
MIN_SUPPORT = 6        # FILAS que deben compartir el hueco a la misma x
MAX_CROSSERS = 0.15    # fracción de filas del bloque que pueden cruzar el canal


def cluster_rows(chars):
    """Agrupa los caracteres de la página en filas por su línea base."""
    rows: list[list] = []
    for c in sorted(chars, key=lambda c: -c.y0):
        if rows and abs(rows[-1][0] - c.y0) <= ROW_TOL:
            rows[-1][1].append(c)
        else:
            rows.append([c.y0, [c]])
    return [(y, sorted(cs, key=lambda c: c.x0)) for y, cs in rows]


def find_gutter(rows, X0: float, X1: float) -> float | None:
    """Centro del canal que separa dos columnas, o None si la página va a una sola.

    NO se busca por el ANCHO del hueco: en un libro compuesto apretado el canal
    puede medir 7pt, menos que algunos espacios entre palabras. Lo que delata a una
    columna es que **muchas filas tengan el hueco a la MISMA x**; en la prosa cada
    hueco cae donde quiera y no se repite. Así que se vota: cada fila con un hueco
    suma un voto a las x que ese hueco cubre, y gana la x más votada.

    De paso resuelve el caso de las notas al pie y los títulos, que cruzan la página
    entera: esas filas simplemente no votan, y luego se tratan como ancho completo.
    """
    W = X1 - X0
    if W < 100 or len(rows) < MIN_SUPPORT:
        return None
    n = int(W) + 1
    support = [0] * n
    for _y, cs in rows:
        vis = [c for c in cs if c.get_text().strip()]
        for a, b in zip(vis, vis[1:]):
            if b.x0 - a.x1 >= MIN_GUTTER:
                for k in range(max(0, int(a.x1 - X0)), min(n, int(b.x0 - X0) + 1)):
                    support[k] += 1

    lo, hi = int(0.30 * W), int(0.70 * W)   # un canal está en el centro, no en un margen
    best = max(range(lo, min(hi + 1, n)), key=lambda k: support[k], default=None)
    if best is None or support[best] < MIN_SUPPORT:
        return None
    a = b = best                            # centro de la meseta de voto máximo
    while a > 0 and support[a - 1] == support[best]:
        a -= 1
    while b < n - 1 and support[b + 1] == support[best]:
        b += 1
    g = X0 + (a + b) / 2

    # Descartar el FALSO POSITIVO de la prosa justificada: al justificar se estiran
    # los espacios, y por azar unas cuantas filas tienen un hueco ancho a la misma x
    # sin que haya columna ninguna. La diferencia es que en una columna de verdad
    # NADIE cruza el canal: aquí se exige que, dentro del bloque que vota, casi
    # ninguna fila lo atraviese. (Las notas al pie y los títulos sí lo cruzan, pero
    # quedan FUERA del bloque, arriba o abajo, y por eso no cuentan.)
    voters = [y for y, cs in rows
              for vis in [[c for c in cs if c.get_text().strip()]]
              if any(bb.x0 - aa.x1 >= MIN_GUTTER and aa.x1 <= g <= bb.x0
                     for aa, bb in zip(vis, vis[1:]))]
    if not voters:
        return None
    top, bot = max(voters), min(voters)
    inside = crossers = 0
    for y, cs in rows:
        if not (bot <= y <= top):
            continue
        inside += 1
        if any(c.x0 <= g <= c.x1 for c in cs if c.get_text().strip()):
            crossers += 1
    if inside and crossers > MAX_CROSSERS * inside:
        return None
    return g


FOOT = -2              # columna ficticia: fila de nota al pie


def _msize(cs) -> float:
    """Cuerpo de letra mediano de una fila (mediano, no medio: un volado suelto no
    debe arrastrar a toda la línea)."""
    v = sorted(c.size for c in cs if c.get_text().strip())
    return v[len(v) // 2] if v else 0.0


def merge_raised(foot, tsz: float):
    """Devuelve el bloque de notas con cada fila de VOLADOS fundida en su renglón.

    En el pie, el número de nota es un volado muy pequeño (6pt frente a los 9.6pt
    del texto) y su línea base va tan alta que forma una FILA APARTE. Peor: cuando
    dos notas comparten renglón, sus dos números caen en la misma fila («3 … 4»),
    y leerla tal cual destruye el orden — el 4 acaba dentro del texto de la nota 3.

    Un volado se apoya SOBRE el renglón de abajo, así que se funde con él y se
    reordena por x. Eso reconstruye el orden de lectura real y, de paso, recompone
    los ordinales volados que también viven en su propia fila («3» + «rd» → «3rd»).
    """
    out: list = []
    pend: list = []
    for y, cs in foot:                     # de arriba a abajo
        if _msize(cs) <= tsz * RAISED:
            pend += cs                     # fila de volados: espera al renglón
            continue
        out.append((y, sorted(pend + cs, key=lambda c: c.x0)))
        pend = []
    if pend:                               # volados sin renglón debajo
        out.append((foot[-1][0], sorted(pend, key=lambda c: c.x0)))
    return out


def iter_lines(pdf: Path, first: int | None, last: int | None, columns: str = "auto",
               body: float | None = None):
    """(página, columna, y0, x0, texto, cuerpo) por línea.

    columna: 0 = izquierda, 1 = derecha, -1 = ancho completo, -2 = nota al pie.
    En páginas a 2 columnas se emite la izquierda ENTERA y luego la derecha, para
    que el reflujo no las funda línea a línea (que es justo lo que hace Calibre).

    Las filas se reconstruyen desde los CARACTERES, no desde las líneas que da
    pdfminer: pdfminer ya fusiona por su cuenta las dos columnas en una sola línea
    cuando el canal es estrecho, y entonces el canal ya no existe cuando lo buscas.

    Con `body`, las filas en cuerpo menor del PIE de la página se separan como notas
    ANTES de buscar columnas: así no estorban al canal (cruzan la página entera) y
    no se mezclan con la prosa.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LTChar
    except ImportError:
        sys.exit("error: falta pdfminer.six → python3 -m pip install --user "
                 "--break-system-packages pdfminer.six   (o: bash setup.sh)")
    pages = None
    if first or last:
        a = (first or 1) - 1
        b = (last or first or 1)
        pages = list(range(a, b))
    for i, page in enumerate(extract_pages(str(pdf), page_numbers=pages)):
        pno = (pages[i] if pages else i) + 1          # nº de página real, 1-based
        chars = []
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for line in el:
                if not hasattr(line, "__iter__"):
                    continue
                chars += [c for c in line if isinstance(c, LTChar)]
        if not chars:
            continue
        rows = cluster_rows(chars)

        def emit(cs, col, bd=None, ratio=SMALL):
            txt = line_markdown(cs, bd, ratio)
            if txt:
                return (pno, col, round(min(c.y0 for c in cs), 1),
                        round(min(c.x0 for c in cs), 1), txt,
                        round(sum(c.size for c in cs) / len(cs), 1))
            return None

        # Las notas al pie: bloque CONTIGUO de filas en cuerpo menor al final de la
        # página. Se sacan antes de nada; si no, cruzarían el canal de las páginas a
        # dos columnas y tumbarían su detección.
        foot = []
        if body:
            while rows and _msize(rows[-1][1]) <= body * SMALL:
                foot.insert(0, rows.pop())

        def emit_foot():
            """Las notas de esta página, con su número ya como [^N].

            Dentro del pie la referencia NO es el cuerpo del texto corrido (11.8)
            sino el de la propia nota (9.6): así el número volado (6pt) sale como
            marcador y las cifras del texto de la nota (años, grados) NO.
            """
            if not foot:
                return
            sizes = Counter(round(c.size, 1) for _y, cs in foot
                            for c in cs if c.get_text().strip())
            tsz = sizes.most_common(1)[0][0]
            for _y, cs in merge_raised(foot, tsz):
                r = emit(cs, FOOT, tsz, RAISED)
                if r:
                    yield r

        if not rows:
            yield from emit_foot()
            continue
        chars = [c for _y, cs in rows for c in cs]

        vis_all = [c for c in chars if c.get_text().strip()]
        X0 = min(c.x0 for c in vis_all)
        X1 = max(c.x1 for c in vis_all)
        g = find_gutter(rows, X0, X1) if columns == "auto" else None
        if g is None:
            for _y, cs in rows:
                r = emit(cs, -1, body)          # página normal: TODO es ancho completo
                if r:
                    yield r
            yield from emit_foot()
            continue

        # Una página a dos columnas NO es un solo bloque: es una pila de BANDAS
        # —rótulo a todo el ancho, bloque a dos columnas, rótulo, bloque…—. Si se
        # trata como un bloque único y se sacan «primero la izquierda entera, luego
        # la derecha», todo lo que cruza el canal (los rótulos de sección centrados
        # §5.1, §5.2…) acaba amontonado al final de la página, separado del texto
        # que titula. Así que una fila que cruza el canal CIERRA la banda en curso y
        # se emite en su sitio.
        band: list = []

        def flush_band():
            for y, cs, k in [b for b in band if b[2] == 0]:      # columna izquierda
                r = emit(cs, 0, body)
                if r:
                    yield r
            for y, cs, k in [b for b in band if b[2] == 1]:      # columna derecha
                r = emit(cs, 1, body)
                if r:
                    yield r
            band.clear()

        for y, cs in rows:
            vis = [c for c in cs if c.get_text().strip()]
            if not vis:
                continue
            # ¿la fila tiene un hueco JUSTO en el canal? Si no lo tiene, lo cruza de
            # lado a lado (rótulo, título): NO se puede partir sin cortar una palabra.
            split = any(b.x0 - a.x1 >= MIN_GUTTER and a.x1 <= g <= b.x0
                        for a, b in zip(vis, vis[1:]))
            if split:
                band.append((y, [c for c in cs if c.x1 <= g], 0))
                band.append((y, [c for c in cs if c.x0 >= g], 1))
            elif max(c.x1 for c in vis) <= g:
                band.append((y, cs, 0))
            elif min(c.x0 for c in vis) >= g:
                band.append((y, cs, 1))
            else:
                yield from flush_band()          # el rótulo cierra la banda…
                r = emit(cs, -1, body)
                if r:
                    yield r                      # …y va en su sitio, no al final
        yield from flush_band()
        yield from emit_foot()


def dehyph(a: str, b: str) -> str:
    """Une dos líneas resolviendo el guion de corte de línea."""
    return a[:-1] + b if re.search(r"[A-Za-zÀ-ÿ]-$", a) else a + " " + b


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--first", type=int, help="primera página (1-based)")
    ap.add_argument("--last", type=int, help="última página (1-based)")
    ap.add_argument("--gap", type=float, default=1.5,
                    help="salto vertical (en múltiplos del interlineado) que separa "
                         "párrafos (def. 1.5; súbelo si trocea de más)")
    ap.add_argument("--columns", choices=("auto", "1"), default="auto",
                    help="auto = detecta el canal y saca las columnas por separado; "
                         "1 = fuerza una columna (def. auto)")
    ap.add_argument("--mark-columns", action="store_true",
                    help="marca cada tramo de columna con «<!-- col N pág P -->» "
                         "(útil en textos paralelos: original / traducción)")
    ap.add_argument("--footnotes", action="store_true",
                    help="separa las notas al pie por CUERPO DE LETRA: los volados "
                         "salen como [^N] y las notas como definiciones [^N]: al final")
    ap.add_argument("--body-size", type=float,
                    help="cuerpo del texto corrido en pt (def: se detecta solo)")
    a = ap.parse_args()
    if not a.pdf.exists():
        sys.exit(f"error: no existe {a.pdf}")

    body = None
    if a.footnotes:
        body = a.body_size or detect_body_size(a.pdf)
        if not body:
            sys.exit("error: no se pudo detectar el cuerpo del texto (--body-size N)")
        print(f"cuerpo del texto: {body}pt   -> nota/volado: <= {body * SMALL:.1f}pt")

    paras: list[str] = []
    cur: list[str] = []
    prev_y = prev_page = prev_col = None
    leads: list[float] = []

    rows = list(iter_lines(a.pdf, a.first, a.last, a.columns, body))
    # interlineado típico = mediana de los saltos dentro de una misma página+columna
    for i in range(1, len(rows)):
        if rows[i][0] == rows[i - 1][0] and rows[i][1] == rows[i - 1][1]:
            d = rows[i - 1][2] - rows[i][2]
            if 0 < d < 60:
                leads.append(d)
    lead = sorted(leads)[len(leads) // 2] if leads else 16.0

    ncol = 0
    foot_txt: list[str] = []                      # renglones del pie, en orden
    for pno, col, y, x, txt, size in rows:
        if col == FOOT:
            foot_txt.append(txt)
            continue
        newp = False
        if prev_y is not None:
            if pno != prev_page or col != prev_col:
                newp = True                       # cambio de página o de columna
            elif (prev_y - y) > lead * a.gap:
                newp = True                       # salto grande: párrafo nuevo
        if newp and cur:
            paras.append(" ".join(cur))
            cur = []
        if a.mark_columns and col >= 0 and (col != prev_col or pno != prev_page):
            paras.append(f"<!-- col {col + 1} pág {pno} -->")   # pno ya es 1-based
        if col == 1 and col != prev_col:
            ncol += 1
        cur = [dehyph(" ".join(cur), txt)] if cur else [txt]
        prev_y, prev_page, prev_col = y, pno, col
    if cur:
        paras.append(" ".join(cur))

    md = "\n\n".join(p.strip() for p in paras if p.strip())

    # Las notas: el pie ya trae su número como [^N] (identificado por CUERPO, no por
    # «empieza con cifra»), así que basta partir el bloque por sus marcadores. Las
    # cifras del texto de una nota (años, grados) van en cuerpo de nota y NO son
    # marcadores, que es lo que antes descuadraba la numeración.
    notes: list[tuple[int, str]] = []
    if foot_txt:
        blob = " ".join(foot_txt)
        trozos = re.split(r"\[\^(\d{1,3})\]", blob)
        # trozos[0] = cola de una nota que venía de antes del rango: se descarta
        for k in range(1, len(trozos) - 1, 2):
            notes.append((int(trozos[k]), trozos[k + 1].strip()))
    if notes:
        md += "\n\n" + "\n\n".join(
            f"[^{n}]: {t}" if t else f"[^{n}]:" for n, t in notes)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    a.out.write_text(md, encoding="utf-8")
    it = len(re.findall(r"(?<!\*)\*(?!\*)[^*\n]+(?<!\*)\*(?!\*)", md))
    print(f"{a.out}: {len(paras)} párrafos, {len(md.split())} palabras, "
          f"~{it} tramos en cursiva  (interlineado={lead:.1f}, gap={a.gap})")
    if ncol:
        print(f"  2 columnas detectadas en {ncol} página(s); salen por separado "
              f"(izquierda entera y luego derecha)")
    if body:
        marks = len(re.findall(r"\[\^\d+\](?!:)", md))
        seq = [n for n, _ in notes]
        full = seq == list(range(1, len(seq) + 1))
        print(f"  notas: {len(notes)} definiciones "
              f"({'secuencia 1..%d COMPLETA' % seq[-1] if full else 'SECUENCIA ROTA'}), "
              f"{marks} llamadas [^N] en el texto")
        if not full and seq:
            falta = sorted(set(range(1, seq[-1] + 1)) - set(seq))
            print(f"  AVISO: faltan las notas {falta[:12]}{' …' if len(falta) > 12 else ''} "
                  f"-> revisa el rango de páginas o el cuerpo detectado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
