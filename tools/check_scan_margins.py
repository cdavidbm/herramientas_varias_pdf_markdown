#!/usr/bin/env python3
"""
check_scan_margins.py — Control de calidad del partido de un escaneo 2-up: avisa
de las páginas a las que el corte del lomo pudo comerse el arranque de las líneas.

Un spread mal partido deja la página SIN margen blanco por el lado interior y el
texto sale truncado carácter a carácter. Es de los defectos más caros de detectar:
en el markdown final el texto parece correcto y sólo se descubre leyendo contra la
imagen. Aquí se mide, para cada página, el blanco que queda del lado del lomo
dentro de la banda de la caja de texto.

Se usa después de `split_scan_spreads.py`. **Ojo con los falsos positivos:** el
moteado que deja la sombra del lomo es tinta y, sin suavizar el perfil, marca como
sospechosa casi cualquier página; por eso el perfil va suavizado. Y a la inversa,
una raya de lomo continua puede pasar por texto pegado al borde: el control
decisivo sigue siendo mirar las páginas señaladas, más las de anchura anómala
frente a la mediana.

Uso:
  python3 check_scan_margins.py ./paginas [umbral_px]

Requiere numpy y Pillow.
"""
import glob, os, sys
import numpy as np
from PIL import Image

PAGES = sys.argv[1]
LIMITE = int(sys.argv[2]) if len(sys.argv) > 2 else 30

malas = []
for f in sorted(glob.glob(os.path.join(PAGES, "pdf*.png"))):
    name = os.path.basename(f)
    a = np.array(Image.open(f)) < 128
    h, w = a.shape
    prof = a[int(h * 0.12):int(h * 0.88)].mean(axis=0)
    # suavizado ligero: el moteado que deja el lomo son columnas sueltas con
    # tinta, no texto; sin esto todas las páginas salen falsamente sospechosas
    prof = np.convolve(prof, np.ones(15) / 15, mode="same")
    ink = np.where(prof > 0.03)[0]
    if not len(ink):
        continue
    if name.endswith("L.png"):        # margen interior = derecha
        margen = w - 1 - ink[-1]
        lado = "der"
    elif name.endswith("R.png"):      # margen interior = izquierda
        margen = ink[0]
        lado = "izq"
    else:
        continue
    if margen < LIMITE:
        malas.append((name, lado, int(margen), w))

for name, lado, m, w in malas:
    print(f"SOSPECHOSA {name}  margen interior ({lado}) = {m}px  ancho={w}")
print(f"\n{len(malas)} páginas con margen interior < {LIMITE}px")
