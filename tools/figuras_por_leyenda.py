#!/usr/bin/env python3
"""figuras_por_leyenda.py — recorta del PDF las figuras que solo dejaron LEYENDA.

Cuándo se usa
-------------
El bisturí conserva la línea «Figure 6.2. …» pero tira el dibujo, así que el
markdown cita figuras que no existen. En un libro cuyas cartas astrológicas son
argumento —no adorno— eso es contenido ausente, y no lo ve ningún control: el
balance de notas cuadra y el ratio de palabras ni se entera.

Cómo encuentra el dibujo
------------------------
La leyenda da el borde INFERIOR. El superior sale de las cajas de texto de la
propia página (`pdftotext -bbox-layout`, que agrupa en RENGLONES; `-bbox` a secas
devuelve palabras sueltas y con ellas no hay hueco que medir): entre el último renglón de prosa y la leyenda
hay un hueco, y el dibujo es ese hueco. Se toma el hueco MÁS GRANDE por encima de
la leyenda, en vez de un umbral fijo en píxeles, porque el interlineado cambia de
página a página y un umbral fijo devuelve recortes de dos centímetros.

Solo cuenta la mención que ABRE RENGLÓN, que es la leyenda: una remisión dentro
de una nota («see below, Figure 5.1») manda a recortar una página sin figura.

Y descarta la página del ÍNDICE de ilustraciones: es la que nombra muchas figuras
a la vez, así que si en una página aparecen más de tres leyendas, no es el cuerpo.

Uso
---
    python3 figuras_por_leyenda.py libro.pdf --md-dir en --figures-dir figuras \
        [--dpi 200] [--apply]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
from xml.etree import ElementTree

CAP = re.compile(r"(Figure|Illustration|Table)\s+(\d+\.\d+)")


def paginas_con_leyenda(pdf: str) -> dict[str, int]:
    """{'6.2': pagina} — la página del CUERPO, no la del índice."""
    txt = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                         capture_output=True, text=True).stdout
    salida: dict[str, int] = {}
    for i, pag in enumerate(txt.split("\f"), start=1):
        marcas = CAP.findall(pag)
        if len(marcas) > 3:          # índice de ilustraciones
            continue
        # Solo cuenta la LEYENDA, que abre renglón (va centrada). Una mención
        # dentro de una nota -«see below, Figure 5.1»- es una remisión, y tomarla
        # por leyenda manda a recortar una página sin figura.
        for linea in pag.split("\n"):
            m = CAP.match(linea.strip())
            if m and len(linea.strip()) > len(m.group(0)) + 3:
                salida.setdefault(f"{m.group(1)[0]}{m.group(2)}", i)
    return salida


def cajas(pdf: str, pagina: int) -> tuple[list[tuple[float, float, str]], float, float]:
    """[(y0, y1, texto)] de cada línea, más el alto y ancho de la página."""
    xml = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(pagina), "-l", str(pagina), pdf, "-"],
                         capture_output=True, text=True).stdout
    raiz = ElementTree.fromstring(xml)
    ns = {"x": raiz.tag.split("}")[0].strip("{")}
    pag = raiz.find(".//x:page", ns)
    alto, ancho = float(pag.get("height")), float(pag.get("width"))
    lineas = []
    for ln in pag.findall(".//x:line", ns):
        texto = " ".join(w.text or "" for w in ln.findall("x:word", ns))
        lineas.append((float(ln.get("yMin")), float(ln.get("yMax")), texto))
    return sorted(lineas), alto, ancho


def region(lineas, clave: str) -> tuple[float, float] | None:
    """(y_arriba, y_abajo) del dibujo, en coordenadas de la página."""
    num = clave[1:]
    # La leyenda ABRE renglón; la mención dentro del párrafo («Figure 7.9 shows…»)
    # no. Tomar la primera aparición manda a recortar el hueco equivocado.
    idx = next((i for i, (_, _, t) in enumerate(lineas)
                if (m := CAP.match(t.strip())) and m.group(2) == num), None)
    if idx is None:
        idx = next((i for i, (_, _, t) in enumerate(lineas) if num in t and CAP.search(t)), None)
    if idx is None:
        return None
    y_leyenda = lineas[idx][0]
    if idx == 0:                     # la figura ABRE la página: no hay texto encima
        return (40.0, y_leyenda) if y_leyenda > 120 else None
    # el hueco más grande por encima de la leyenda
    huecos = [(lineas[i + 1][0] - lineas[i][1], lineas[i][1]) for i in range(idx)]
    mejor, y0 = max(huecos, default=(0.0, None))
    # El umbral no puede ser fijo: el interlineado cambia de página a página, y 40
    # puntos descarta figuras reales en las páginas de renglón apretado. Se compara
    # con el interlineado MEDIANO de la propia página, como manda la lección.
    # El interlineado se mide SIN el hueco de la figura: si se incluye, en una
    # página con dos o tres renglones la mediana ES ese hueco y la figura se
    # descarta a sí misma.
    normal = sorted(h for h, _ in huecos)[:-1] or [12.0]
    interlineado = normal[len(normal) // 2]
    if y0 is None or mejor < 25 or mejor < 2 * interlineado:
        # La figura que ABRE PÁGINA no tiene texto encima, así que no hay hueco
        # que medir: ahí el borde superior es el margen de la caja de texto.
        if idx <= 1 and y_leyenda > 120:
            return 40.0, y_leyenda
        return None
    return y0, y_leyenda


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--md-dir", default="en")
    ap.add_argument("--figures-dir", default="figuras")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    dir_fig = pathlib.Path(a.figures_dir)
    dir_fig.mkdir(exist_ok=True)
    paginas = paginas_con_leyenda(a.pdf)
    hechas, fallos = [], []
    for clave, pagina in sorted(paginas.items()):
        if clave.startswith("T"):            # las tablas no son dibujo
            continue
        lineas, alto, ancho = cajas(a.pdf, pagina)
        r = region(lineas, clave)
        if not r:
            fallos.append(f"  {clave} (p.{pagina}): no encuentro el hueco del dibujo")
            continue
        y0, y1 = r
        destino = dir_fig / f"fig{clave[1:].replace('.', '_')}.png"
        if a.apply:
            esc = a.dpi / 72.0
            subprocess.run(["pdftoppm", "-r", str(a.dpi), "-png", "-f", str(pagina),
                            "-l", str(pagina), "-x", "0", "-y", str(int(y0 * esc)),
                            "-W", str(int(ancho * esc)), "-H", str(int((y1 - y0) * esc)),
                            a.pdf, str(destino.with_suffix(""))], check=True)
        hechas.append((clave, pagina, destino))
    print(f"{len(hechas)} figuras localizadas, {len(fallos)} sin hueco claro")
    for c, p, d in hechas:
        print(f"  {c} · p.{p} -> {d.name}")
    for f in fallos:
        print(f)
    if not a.apply:
        print("  (dry-run: nada escrito; usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
