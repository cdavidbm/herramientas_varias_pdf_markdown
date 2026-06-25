# CLAUDE.md — Manual de operación de La Forja (para el agente)

Este repo es un **taller de conversión de libros a markdown por capítulo**,
pensado para que **lo opere Claude**, no la persona usuaria. El usuario pide un
resultado ("pasa este libro a markdown", "prepáralo para NotebookLM") y **tú
diagnosticas el documento y eliges la herramienta correcta tú mismo**.

> También existe la skill global **`/forja`** con este mismo algoritmo. Este
> archivo lo replica para que el repo sea autoexplicativo aunque se use en otra
> máquina o sin la skill cargada.

## Principio rector

1. **Sondea, no preguntes lo inferible.** Formato, escaneo vs digital, columnas,
   tablas… se detectan con comandos. Pregunta SOLO lo que no se puede inferir:
   idioma destino (al traducir) o qué front-matter descartar.
2. **Previsualiza siempre** (`--dry-run`, o Docling sobre 1 capítulo) antes del
   run completo. **Anuncia en una línea la ruta elegida y por qué.**
3. **Calidad editorial:** el destino es leer/estudiar/traducir, no solo indexar.
   Si un bisturí deja markdown sucio, escala a Docling.

## Algoritmo de diagnóstico

Define `T=tools` (o ruta absoluta `/mnt/c/ideas/_La_Forja/tools`).

### 1. Enrutar por formato
- `.epub` → §EPUB.  `.rtf` → `python3 $T/rtf_to_markdown.py x.rtf`.
- `.docx .pptx .xlsx .html .png .jpg` → `markitdown x` (NO es trabajo de los scripts).
- `.pdf` → §PDF.

### 2. Diagnóstico PDF
```bash
pdfinfo x.pdf
chars=$(pdftotext -f 1 -l 5 x.pdf - 2>/dev/null | wc -c); echo "chars/5pp=$chars"
```
- **Encrypted: yes** → `qpdf --decrypt x.pdf x_dec.pdf` → re-diagnostica.
- **chars/5pp muy bajo (< ~500)** → escaneo sin texto → `ocrmypdf --skip-text x.pdf x_ocr.pdf`.
- **Páginas apaisadas (ancho/alto > ~1.3)** → escaneo 2-up → `python3 $T/split_pdf_spreads.py x.pdf` (deja `x_1up.pdf`) ANTES de OCR/troceo.

### 3. ¿Bisturí o Docling?
Mira layout en una página de cuerpo:
```bash
pdftotext -layout -f 20 -l 20 x.pdf - | sed -n '1,40p'
pdfimages -list x.pdf | wc -l
```
**Docling** (`docling x.pdf --to md --output ./markdown/`) si hay: multicolumna,
tablas, fórmulas, muy ilustrado (imágenes ≫ páginas) o extracción rota.
Si es **prosa limpia a una columna** → bisturí (§3b). Ante la duda: 1 capítulo
con bisturí, revisa el `.md`; si quedó sucio, repite con Docling.

### 3b. Elegir bisturí PDF
| Situación | Script |
|---|---|
| Carpeta de **un PDF por capítulo**, notas a pie | `pdf_chapters_to_markdown.py plan.json` |
| **Un PDF digital limpio** (Calibre, con outline) | `detect_chapters.py` → `plan.json` → `pdf_sections_to_markdown.py plan.json` |
| Libro **escaneado ya OCR-eado** con citas Harvard | `pdf_book_to_markdown.py` |
| Solo **partir** el PDF en PDFs por capítulo | `detect_chapters.py` → `plan.json` → `split_pdf.py` |

`detect_chapters.py` lista páginas candidatas (no escribe el plan); con eso
**redactas el `plan.json`** y corres el conversor con `--dry-run` primero.

### EPUB
```bash
python3 $T/build_plan.py "libro.epub" > plan.json   # spine + TOC (genérico)
python3 $T/epub_to_markdown.py plan.json --dry-run && python3 $T/epub_to_markdown.py plan.json
```
EPUB muy ilustrado → `epub_illustrated_to_markdown.py`.

## Esquema de `plan.json`
```json
{
  "source": "libro.pdf",
  "output_dir": "markdown",
  "sections": [
    { "slug": "01_Prefacio", "title": "Prefacio", "pages": [9, 10] },
    { "slug": "02_Intro",    "title": "Introducción", "pages": [11, null] },
    { "slug": "03_Cap2",     "title": "Capítulo 2", "pdf": "2 Chapter 2.pdf" }
  ]
}
```
`pages: [ini, fin]` 1-based, `null` = hasta el final. `pdf:` en vez de `pages:` =
un PDF entero como sección.

## Salida / siguiente paso
- Markdown → NotebookLM (fuente) o traducción con la skill **`/traducir-md`**
  (preserva `[^N]`, encabezados, glosario).
- Entregar en otro formato: `pandoc cap.md -o cap.epub|.docx|.pdf`.

## Herramientas disponibles en el equipo
Scripts del repo · `pandoc` · `ocrmypdf` · `tesseract` · poppler (`pdfinfo`,
`pdftotext`, `pdfimages`) · `mutool` · **`docling`** (PDF complejos) ·
**`markitdown`** (Office/html/imágenes). Sin claves de API.

Detalles finos de cada script (manejo de notas por formato, límites): ver
`README.md` y `tools/README.md`.
