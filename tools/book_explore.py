#!/usr/bin/env python3
"""
book_explore.py — Busca términos dentro de un PDF o EPUB y devuelve los pasajes
con su UBICACIÓN (página en PDF, capítulo/archivo en EPUB) y contexto alrededor.

Pensado para "mira tal libro y dime qué hay sobre X": el script localiza dónde
mirar (exhaustivo y barato); el agente lee solo esos pasajes y sintetiza.

Búsqueda insensible a mayúsculas y a acentos (para español). NO modifica nada.

Uso:
    python3 book_explore.py LIBRO.pdf  --terms "saturno, melancolía, bilis negra"
    python3 book_explore.py LIBRO.epub --terms "prime matter" --context 3
    python3 book_explore.py LIBRO.pdf  --regex "Saturn[oi]" --max 40

Opciones:
    --terms "a, b, c"   términos separados por coma (cualquiera que aparezca)
    --regex PATRÓN      en vez de --terms, una expresión regular
    --context N         líneas de contexto a cada lado (def. 2)
    --max N             máximo de coincidencias a mostrar (def. 60)
"""
from __future__ import annotations
import argparse
import re
import sys
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


def deaccent(s: str) -> str:
    """minúsculas + sin tildes, para comparar."""
    nfkd = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# ----------------------------- extracción -----------------------------------

def pdf_units(path: Path) -> list[tuple[str, str]]:
    """Devuelve [(etiqueta, texto)] por página usando pdftotext."""
    import subprocess
    try:
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                             capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        sys.exit("error: falta 'pdftotext' (instala poppler-utils).")
    pages = out.stdout.split('\f')
    units = [(f"pág. {i}", txt) for i, txt in enumerate(pages, 1) if txt.strip()]
    if not units:
        sys.exit("aviso: el PDF no tiene capa de texto (¿escaneo?). "
                 "Pásalo antes por OCR: ocrmypdf in.pdf out.pdf")
    return units


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False
    def handle_starttag(self, tag, attrs):  # noqa: ARG002 (firma de HTMLParser)
        if tag in ("script", "style"):
            self._skip = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    p = _Stripper()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\n{2,}', '\n', "".join(p.parts))


def epub_units(path: Path) -> list[tuple[str, str]]:
    """Devuelve [(etiqueta, texto)] por documento del spine (orden de lectura)."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        opf = next((n for n in names if n.endswith('.opf')), None)
        order: list[str] = []
        if opf:
            try:
                root = ET.fromstring(z.read(opf))
                ns = {'o': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
                base = opf.rsplit('/', 1)[0] + '/' if '/' in opf else ''
                manifest = {}
                m_el = root.find('o:manifest', ns) if ns else root.find('manifest')
                s_el = root.find('o:spine', ns) if ns else root.find('spine')
                if m_el is not None:
                    for it in m_el:
                        manifest[it.get('id')] = it.get('href')
                if s_el is not None:
                    for ref in s_el:
                        href = manifest.get(ref.get('idref'))
                        if href:
                            order.append((base + href).lstrip('/'))
            except Exception:
                order = []
        if not order:
            order = sorted(n for n in names if n.lower().endswith(('.xhtml', '.html', '.htm')))

        units: list[tuple[str, str]] = []
        for href in order:
            real = href if href in names else next((n for n in names if n.endswith(href)), None)
            if not real:
                continue
            try:
                html = z.read(real).decode('utf-8', errors='replace')
            except KeyError:
                continue
            text = _html_to_text(html)
            if text.strip():
                label = real.rsplit('/', 1)[-1]
                units.append((label, text))
    if not units:
        sys.exit("aviso: no pude extraer texto del EPUB.")
    return units


# ------------------------------ búsqueda ------------------------------------

def search(units: list[tuple[str, str]], pattern: re.Pattern, ctx: int, mx: int):
    hits = 0
    per_unit: dict[str, int] = {}
    shown = 0
    for label, text in units:
        norm_lines = [deaccent(l) for l in text.splitlines()]
        lines = text.splitlines()
        for i, nl in enumerate(norm_lines):
            if pattern.search(nl):
                hits += 1
                per_unit[label] = per_unit.get(label, 0) + 1
                if shown < mx:
                    lo, hi = max(0, i - ctx), min(len(lines), i + ctx + 1)
                    snippet = "\n".join(f"      {lines[j].rstrip()}" for j in range(lo, hi))
                    print(f"\n[{label}]")
                    print(snippet)
                    shown += 1
    return hits, per_unit, shown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("libro", type=Path)
    ap.add_argument("--terms", help="términos separados por coma")
    ap.add_argument("--regex", help="patrón regex (alternativa a --terms)")
    ap.add_argument("--context", type=int, default=2)
    ap.add_argument("--max", type=int, default=60)
    args = ap.parse_args()

    if not args.libro.is_file():
        sys.exit(f"error: no existe {args.libro}")
    if not args.terms and not args.regex:
        sys.exit("error: da --terms \"a, b\" o --regex PATRÓN")

    if args.regex:
        pattern = re.compile(deaccent(args.regex))
        descr = f"regex /{args.regex}/"
    else:
        terms = [deaccent(t.strip()) for t in args.terms.split(',') if t.strip()]
        pattern = re.compile('|'.join(re.escape(t) for t in terms))
        descr = "términos: " + ", ".join(terms)

    ext = args.libro.suffix.lower()
    if ext == '.pdf':
        units = pdf_units(args.libro)
    elif ext == '.epub':
        units = epub_units(args.libro)
    else:
        sys.exit(f"error: formato no soportado ({ext}). Usa .pdf o .epub")

    print(f"== Explorando {args.libro.name} ({len(units)} secciones) · {descr} ==")
    hits, per_unit, shown = search(units, pattern, args.context, args.max)

    print(f"\n── Resumen: {hits} coincidencia(s) en {len(per_unit)} sección(es) ──")
    for label, n in sorted(per_unit.items(), key=lambda kv: -kv[1]):
        print(f"   {n:>3}  {label}")
    if shown < hits:
        print(f"\n(mostradas {shown} de {hits}; sube --max para ver más)")
    if hits == 0:
        print("   sin coincidencias — prueba sinónimos o --regex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
