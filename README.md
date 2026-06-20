# 🛠️ Herramientas varias · PDF & EPUB → Markdown

> Una pequeña suite de utilidades para **rebanar libros largos** (PDF, EPUB, RTF)
> en *markdown limpio por capítulo*, listo para NotebookLM, lectura dirigida,
> fuentes de RAG o traducción.

Convertir un libro entero de PDF a texto da un mazacote ilegible: encabezados
repetidos, números de página incrustados, notas al pie sueltas, guiones de corte
de línea, dos páginas escaneadas en una. Estas herramientas deshacen ese ruido y
entregan **un `.md` por capítulo**, autocontenido, con sus notas resueltas como
`[^N]`.

No es un conversor universal de un clic: es un juego de bisturíes, cada uno
afinado a un tipo de fuente real. Se eligen según el documento.

---

## ✨ Qué resuelve

| Problema del documento | Herramienta |
|---|---|
| Un PDF largo que hay que partir por capítulos | `split_pdf.py` + `detect_chapters.py` |
| Escaneo con **dos páginas por hoja** (spreads) | `split_pdf_spreads.py` |
| PDF digital limpio → markdown por secciones | `pdf_sections_to_markdown.py` |
| Carpeta de **un PDF por capítulo** con notas a pie | `pdf_chapters_to_markdown.py` |
| Libro escaneado (post-OCR) con citas Harvard | `pdf_book_to_markdown.py` |
| **Cualquier EPUB** → markdown por capítulo | `build_plan.py` + `epub_to_markdown.py` |
| EPUB **ilustrado** (figuras, glifos musicales) | `epub_illustrated_to_markdown.py` |
| RTF de ePubLibre/Titivillus con notas agrupadas | `rtf_to_markdown.py` |

---

## 🚀 Inicio rápido

### EPUB → markdown (lo más automático)

```bash
# 1. Genera el plan automáticamente (lee spine + índice del propio EPUB)
python3 tools/build_plan.py "libro.epub" > plan.json

# 2. Revisa el plan a ojo (quita front-matter que no quieras, ajusta títulos)

# 3. Convierte: un .md por capítulo en ./markdown/
python3 tools/epub_to_markdown.py plan.json --dry-run   # previsualiza
python3 tools/epub_to_markdown.py plan.json             # ejecuta
```

`build_plan.py` es **genérico**: funciona con EPUB2 (`.ncx`) y EPUB3 (`nav`),
fusiona archivos de continuación, salta portada/créditos/índice (ES + EN) y
autodetecta el pool de notas. Probado en 38 EPUBs reales sin un solo crash.

### PDF → markdown por capítulos

```bash
# Si es un escaneo 2-up, primero descolócalo a 1-up:
python3 tools/split_pdf_spreads.py "libro.pdf"          # -> libro_1up.pdf

# Localiza los cortes de capítulo y escribe un plan.json (ver tools/README.md)
python3 tools/detect_chapters.py "libro.pdf"

# Convierte (PDF digital limpio):
python3 tools/pdf_sections_to_markdown.py plan.json
```

---

## 🗂️ El taller de un vistazo

```
tools/
├── split_pdf.py                  PDF → PDFs por capítulo (poppler)
├── split_pdf_spreads.py          escaneo 2-up → 1-up (mutool)
├── detect_chapters.py            detecta marcadores de capítulo en un PDF
│
├── pdf_sections_to_markdown.py   PDF digital limpio   → markdown por sección
├── pdf_chapters_to_markdown.py   PDFs pre-partidos    → markdown + notas a pie
├── pdf_book_to_markdown.py       PDF escaneado (OCR)  → markdown saneado
│
├── build_plan.py                 EPUB → plan.json (genérico, spine + índice)
├── epub_to_markdown.py           EPUB → markdown por capítulo (notas → [^N])
├── epub_illustrated_to_markdown.py  EPUB con figuras → markdown + imágenes
│
├── rtf_to_markdown.py            RTF (notas agrupadas) → markdown por sección
├── attach_notes_by_chapter.py    adjunta notas agrupadas a cada capítulo
└── README.md                     📖 manual detallado (formatos, plan.json, flujos)
```

> El **manual detallado** —esquema de `plan.json`, heurísticas de cada script,
> flujos paso a paso y solución de problemas— está en
> [`tools/README.md`](tools/README.md).

---

## 🔍 Lo que cuidan estas herramientas

- **Notas al pie resueltas** como `[^N]` markdown, en sus dos codificaciones
  habituales: *pool* (un fichero de notas) y *ancla local* (la nota en el mismo
  archivo, patrón Calibre/InDesign).
- **Prosa recompuesta**: deshace guiones de corte, vuelve a unir párrafos
  partidos por salto de línea o de página, quita encabezados y folios.
- **Estructura preservada**: títulos, listas, tablas, citas en bloque y
  separadores se trasladan a markdown; las imágenes decorativas se descartan.
- **Granularidad por capítulo**: cada `.md` es autocontenido, ideal para aislar
  *embeddings* en NotebookLM en vez de subir el libro entero.

### Límites honestos

- A **granularidad de archivo**: un EPUB que empaqueta el libro entero en un
  solo `.xhtml` (típico de algunos *rips*) da una sección gruesa — el piso es un
  `.md` por archivo de origen.
- Las notas en estructuras exóticas (ni pool ni ancla local) pasan como
  superíndices crudos.
- Los PDF escaneados necesitan OCR previo (`ocrmypdf`) antes del saneado.

---

## 📦 Requisitos

```bash
# Manipulación de PDF (cortar, unir, extraer texto):
sudo apt-get install poppler-utils      # pdfinfo, pdftotext, pdfseparate, pdfunite

# Descolocar escaneos 2-up → 1-up:
sudo apt-get install mupdf-tools         # mutool

# Conversión de EPUB / utilidades Python:
pip install --user beautifulsoup4

# RTF:
pip install --user striprtf

# (Opcional) reparar OCR de escaneos antiguos antes de pdf_book_to_markdown.py:
sudo apt-get install ocrmypdf tesseract-ocr-spa
```

Todos los scripts son Python 3 + utilidades de línea de comandos; sin servicios
en la nube ni claves de API.

---

## 💡 Filosofía

Una herramienta entra a esta suite por **ganancia neta**, no por coleccionismo.
Antes que añadir un conversor «universal» que produzca markdown mediocre, se
prefieren bisturíes específicos que produzcan markdown *de calidad editorial* —
porque el destino es leer, estudiar y traducir, no solo indexar.
