#!/usr/bin/env python3
"""
split_scan_spreads.py — Parte un escaneo 2-up en IMÁGENES de una página, listas
para transcribir por visión (una imagen = una página del libro).

Complementa a `split_pdf_spreads.py`, que produce un PDF 1-up cortando cada hoja
por la mitad geométrica. Aquí el objetivo es distinto: sacar imágenes limpias del
escaneo, y el corte NO va por la mitad sino por el LOMO detectado, porque en los
escaneos reales el libro nunca está centrado.

Tres lecciones medidas (Travaglia, *Magic, Causality and Intentionality*, SISMEL
1999, 100 hojas → 194 páginas):

1. **Cortar por el lomo, nunca ajustándose a la caja de texto.** Ajustar al texto
   parece más limpio, pero se come el arranque de cada línea de la página derecha
   («I decided to extend…» → «d to extend…»), y esa pérdida es INVISIBLE en el
   markdown final. Cortar dentro de la franja negra del lomo no puede tocar texto:
   a lo sumo deja asomar unas letras de la página vecina en el margen.
2. **El perfil de tinta se mide sólo en la banda de la caja de texto**; si no, el
   ruido de los bordes superior e inferior inventa columnas con tinta.
3. **El recorte de bordes negros alterna filas y columnas RECALCULANDO**: una banda
   negra horizontal infla la media de todas las columnas, y sin recalcular el
   recorte lateral se lleva texto real.

Extrae la imagen embebida de cada página con `pdfimages` en vez de rasterizar con
`pdftoppm`: en un escaneo con una imagen por página es un orden de magnitud más
rápido y da el original sin remuestrear.

Comprueba el resultado con `check_scan_margins.py`, que detecta las páginas cuyo
margen interior quedó a cero (señal de que el corte se comió texto).

Uso:
  python3 split_scan_spreads.py libro.pdf ./paginas [primera] [ultima]

Salida: `paginas/pdfNNNL.png`, `pdfNNNR.png` (izquierda/derecha de la hoja NNN),
`pdfNNNsingle.png` para cubiertas y hojas de una sola página, y un `manifest.tsv`.
Requiere poppler (`pdfimages`, `pdfinfo`), numpy y Pillow.

Cómo verificar el corte, y las trampas medidas
-----------------------------------------------
**Nunca ajustes el corte a la caja de texto.** Se come el arranque de cada línea de la
página derecha («I decided to extend…» → «d to extend…»), y en el markdown final eso es
INVISIBLE. Cortar dentro de la franja negra del lomo no puede tocar texto; que asomen
unas letras de la página vecina es inofensivo.

Verifica siempre con `check_scan_margins.py ./paginas` **y mirando los anchos anómalos**
frente a la mediana: una página mucho más estrecha que las demás es un corte que se
comió texto.

Tres trampas más, todas medidas:

* Promediar la tinta sobre TODA la altura trunca la caja de las páginas con pocas líneas
  (la última de un capítulo, las portadillas).
* El recorte de bordes negros debe alternar filas y columnas **recalculando**: una banda
  negra horizontal infla el perfil de todas las columnas.
* El **folio impreso** da el mapeo página↔imagen y hay que validarlo. En Travaglia salía
  `libro = 2·N − 6 / 2·N − 5`, pero el desfase cambia con el front matter de cada libro.

Cuadernillo de anillas escaneado ABIERTO (spread girado 90° en la imagen)
--------------------------------------------------------------------------
Aquí `qpdf` y `split_pdf_spreads` no sirven: el MediaBox es vertical, `Page rot` es 0 y
la rotación está en el contenido de la imagen. El OSD de tesseract da baja confianza.

Se resuelve por imagen: extraer, girar (prueba los cuatro ángulos y OCR-ea para ver cuál
da texto real) y partir en mitades, descartando las vacías por densidad de tinta. Orden
de lectura: izquierda antes que derecha por hoja.

**Y si es para transcribir por visión, no partas por la mitad ni por el valle de una
banda fija en torno al centro:** el escaneo lleva un margen de mesa que DESCENTRA el
spread, el corte cae dentro del texto y la página izquierda pierde el final de cada
línea —invisible después en el markdown—. Localiza las **dos cajas de texto** por el
perfil de tinta suavizado y corta en mitad del hueco que las separa; recorta cada mitad
a su caja de tinta, no por «bandas oscuras», porque con fondo CLARO ese recorte actúa
distinto en cada hoja y descuadra el partido. Medido en *On the Stellar Rays*
(Zoller/Hand): 44 hojas → 88 páginas en 12 s usando `pdfimages` en vez de `pdftoppm`.
"""
import subprocess, sys, os, glob
import numpy as np
from PIL import Image

PDF = sys.argv[1]
OUT = sys.argv[2]
FIRST = int(sys.argv[3]) if len(sys.argv) > 3 else 1
LAST = int(sys.argv[4]) if len(sys.argv) > 4 else 0

os.makedirs(OUT, exist_ok=True)
TMP = os.path.join(OUT, "_tmp")
os.makedirs(TMP, exist_ok=True)


def ink_profile(a):
    """Fracción de píxeles de tinta por columna (a = bool array, True = tinta)."""
    return a.mean(axis=0)


def _bounds(v, thr):
    """Último borde negro por delante y primero por detrás.

    Se busca en el 45 % de cada extremo: así el ruido blanco salpicado dentro de
    la banda negra no corta la búsqueda prematuramente (una sola línea con media
    baja no basta para declarar que la banda terminó).
    """
    n = len(v)
    m = int(n * 0.45)
    black = v > thr
    lo = 0
    for i in range(m):
        if black[i]:
            lo = i + 1
    hi = n
    for i in range(n - 1, n - m, -1):
        if black[i]:
            hi = i
    return lo, hi


def trim_borders(img, thr=0.55, rounds=3):
    """Recorta las bandas negras del escaneo dejando un margen blanco.

    Una banda de borde es casi toda tinta; el texto nunca lo es. Filas y columnas
    se recortan ALTERNANDO y recalculando el perfil: una banda negra horizontal
    infla la media de TODAS las columnas y, sin recalcular, haría que el recorte
    lateral se comiera texto real.
    """
    pad = 12
    for _ in range(rounds):
        a = np.array(img) < 128
        h, w = a.shape
        y0, y1 = _bounds(a.mean(axis=1), thr)
        y0 = max(0, y0 - pad); y1 = min(h, y1 + pad)
        if y1 - y0 > 200 and (y0, y1) != (0, h):
            img = img.crop((0, y0, w, y1))

        a = np.array(img) < 128
        h, w = a.shape
        x0, x1 = _bounds(a.mean(axis=0), thr)
        x0 = max(0, x0 - pad); x1 = min(w, x1 + pad)
        if x1 - x0 > 200 and (x0, x1) != (0, w):
            img = img.crop((x0, 0, x1, h))
        else:
            break
    return img


def process(page_no):
    for f in glob.glob(os.path.join(TMP, "*")):
        os.remove(f)
    subprocess.run(["pdfimages", "-png", "-f", str(page_no), "-l", str(page_no),
                    PDF, os.path.join(TMP, "s")], check=True)
    files = sorted(glob.glob(os.path.join(TMP, "s-*.png")))
    if not files:
        print(f"  pág {page_no}: SIN IMAGEN", file=sys.stderr)
        return []
    img = trim_borders(Image.open(files[0]).convert("L"))
    w, h = img.size
    if w < h * 1.15:  # portada/contraportada: página única
        return [("single", img)]
    a = np.array(img) < 128
    mid = w // 2

    # Se corta por la FRANJA NEGRA DEL LOMO, no por la caja de texto. Intentar
    # ajustar el corte al texto acaba comiéndose el arranque de las líneas en las
    # páginas con pocas líneas o con figuras, y esa pérdida es invisible después.
    # Cortar dentro del lomo nunca puede tocar texto: a lo sumo deja asomar unas
    # letras de la página vecina en el margen, que no estorban al transcriptor.
    prof = ink_profile(a[int(h * 0.08):int(h * 0.92)])
    lo, hi = int(w * 0.35), int(w * 0.65)
    gutter = lo + int(np.argmax(prof[lo:hi]))

    if prof[gutter] > 0.50:          # hay lomo negro: cortar por sus bordes
        gl = gutter
        while gl > lo and prof[gl] > 0.30:
            gl -= 1
        gr = gutter
        while gr < hi and prof[gr] > 0.30:
            gr += 1
        cut_left, cut_right = gl, gr
    else:                            # sin lomo marcado: cortar por el valle
        k = 41
        smooth = np.convolve(prof, np.ones(k) / k, mode="same")
        valley = lo + int(np.argmin(smooth[lo:hi]))
        cut_left = cut_right = valley
    if not (0 < cut_left <= cut_right < w):
        cut_left = cut_right = mid
    left = img.crop((0, 0, cut_left, h))
    right = img.crop((cut_right, 0, w, h))
    out = []
    for side, part in (("L", left), ("R", right)):
        if part.size[0] < 200:
            continue
        part = trim_borders(part)
        pa = np.array(part) < 128
        if pa.mean() < 0.005 or pa.mean() > 0.9:
            continue  # mitad en blanco o degenerada
        out.append((side, part))
    return out


last = LAST or int(subprocess.run(["pdfinfo", PDF], capture_output=True, text=True)
                   .stdout.split("Pages:")[1].split()[0])
manifest = []
for p in range(FIRST, last + 1):
    parts = process(p)
    for side, im in parts:
        name = f"pdf{p:03d}{side}.png"
        im.save(os.path.join(OUT, name))
        manifest.append((name, p, side, im.size))
    print(f"pdf {p}: {len(parts)} páginas -> {[m[0] for m in manifest[-len(parts):]]}")

with open(os.path.join(OUT, "manifest.tsv"), "w") as fh:
    for name, p, side, size in manifest:
        fh.write(f"{name}\t{p}\t{side}\t{size[0]}x{size[1]}\n")
print(f"\nTotal: {len(manifest)} páginas de libro")
