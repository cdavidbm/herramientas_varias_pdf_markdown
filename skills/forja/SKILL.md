---
name: forja
description: Convierte cualquier libro/documento (PDF, EPUB, RTF, Office) a markdown limpio por capítulo. Diagnostica el documento AUTOMÁTICAMENTE y elige la herramienta correcta (scripts de La Forja, OCR o Docling) sin que el usuario tenga que saber cuál. Activa con "/forja" o intención como "convierte este PDF a markdown", "pasa este libro a markdown", "prepáralo para NotebookLM".
---

# La Forja — Conversión automática a Markdown

Suite para rebanar libros largos en **markdown limpio por capítulo** (notas al
pie resueltas `[^N]`), listo para NotebookLM, RAG, lectura dirigida o traducción
([[traducir-md]]).

## PRINCIPIO RECTOR — estas herramientas son para el agente

El usuario **no las ejecuta ni sabe cuál usar**: te pide un resultado ("pasa este
libro a markdown") y **tú diagnosticas y decides solo**. Por tanto:

- **Sondea el documento tú mismo** con los comandos de abajo. No le preguntes al
  usuario detalles que puedes inferir (formato, si es escaneo, si tiene columnas).
- **Solo pregunta** cuando la elección cambie el resultado y NO sea inferible:
  idioma destino al traducir, o qué secciones de front-matter descartar.
- **Siempre previsualiza** (`--dry-run` / Docling sobre 1 capítulo) antes de
  procesar el libro entero, y **anuncia la ruta elegida y por qué** en una línea.

**Toolbox:** `/mnt/c/ideas/_La_Forja/tools/` (Windows: `C:\ideas\_La_Forja\tools\`).
Define `T=/mnt/c/ideas/_La_Forja/tools` al empezar.

---

## ALGORITMO DE DIAGNÓSTICO (ejecútalo en orden)

### Paso 1 · Enrutar por formato (extensión)

| Extensión | Ruta |
|---|---|
| `.epub` | → **Paso 4 (EPUB)** |
| `.rtf` | `python3 $T/rtf_to_markdown.py archivo.rtf` |
| `.docx .pptx .xlsx .html .png .jpg` | `markitdown archivo` (o el MCP `markitdown`) — NO son trabajo de los scripts |
| `.pdf` | → **Paso 2 (diagnóstico PDF)** |

### Paso 2 · Diagnóstico del PDF (sondeos automáticos)

Ejecuta y lee la salida:

```bash
pdfinfo archivo.pdf                       # páginas, tamaño, ¿Encrypted?
# Densidad de capa de texto (muestra de 5 páginas):
chars=$(pdftotext -f 1 -l 5 archivo.pdf - 2>/dev/null | wc -c); echo "chars/5pp=$chars"
```

Decide en este orden:

1. **¿Encriptado?** (pdfinfo `Encrypted: yes`) → `qpdf --decrypt in.pdf out.pdf`
   primero (si falta qpdf, avísalo). Luego re-diagnostica.
2. **¿Sin capa de texto?** Si `chars/5pp` es muy bajo (≈ < 500, o sea < ~100 por
   página) → es **escaneo de imágenes** → OCR:
   `ocrmypdf --skip-text archivo.pdf archivo_ocr.pdf` y sigue con `archivo_ocr.pdf`.
3. **¿Escaneo 2-up?** (dos páginas por hoja). Señal: en `pdfinfo` el tamaño es
   **apaisado** (ancho/alto > ~1.3) en la mayoría de páginas → 
   `python3 $T/split_pdf_spreads.py archivo.pdf` (deja `_1up.pdf`; las páginas
   verticales como portada pasan intactas). Hazlo **antes** de OCR/troceo.
4. Con capa de texto OK → **Paso 3 (¿bisturí o Docling?)**.

### Paso 3 · ¿Script bisturí o Docling? (la decisión que el usuario no sabría tomar)

Sondea la **complejidad de layout** sobre 2-3 páginas de contenido (no portada):

```bash
N=20   # una página con cuerpo real
pdftotext -layout -f $N -l $N archivo.pdf - | sed -n '1,40p'    # ¿columnas/tablas?
pdfimages -list archivo.pdf | wc -l                            # nº de imágenes
```

Usa **Docling** (`docling archivo.pdf --to md --output ./markdown/`) si detectas
**cualquiera** de estas (los bisturíes las destrozan):

- **Multicolumna:** líneas con un hueco grande de espacios en medio (dos bloques
  de texto por línea) en el volcado `-layout`.
- **Tablas:** filas con varias columnas separadas por espacios, repetidas.
- **Fórmulas/matemáticas** densas, o muchos glifos raros.
- **Muy ilustrado:** imágenes ≫ páginas (figuras en casi cada página).
- **Extracción rota:** el texto sale con palabras pegadas/partidas de forma
  generalizada pese a tener capa de texto.

Si el texto sale **limpio, una columna, prosa corrida** → usa un **bisturí**
(Paso 3b). Ante la duda, convierte **un capítulo** con un bisturí y mira el `.md`;
si quedó sucio, repite con Docling. Anuncia qué elegiste.

### Paso 3b · Elegir el bisturí PDF correcto

| Situación | Script |
|---|---|
| Carpeta con **un PDF por capítulo** (típico de compartidos académicos), notas a pie de página | `pdf_chapters_to_markdown.py plan.json` |
| **Un solo PDF digital limpio** (p. ej. de Calibre), con índice/outline | `detect_chapters.py` → arma `plan.json` → `pdf_sections_to_markdown.py plan.json` |
| **Libro escaneado ya OCR-eado** con citas Harvard | `pdf_book_to_markdown.py` |
| Solo necesito **partir el PDF** en PDFs por capítulo | `detect_chapters.py` → `plan.json` → `split_pdf.py` |

`detect_chapters.py` **no escribe** el plan: lista páginas candidatas; con eso
**tú redactas el `plan.json`** (esquema abajo) y luego corres el conversor con
`--dry-run` antes del run real.

### Paso 4 · EPUB

```bash
python3 $T/build_plan.py "libro.epub" > plan.json   # genérico: spine + TOC
# revisa plan.json a ojo (front-matter, títulos)
python3 $T/epub_to_markdown.py plan.json --dry-run
python3 $T/epub_to_markdown.py plan.json
```

Si el EPUB es **muy ilustrado** (figuras, glifos musicales) usa
`epub_illustrated_to_markdown.py` en lugar de `epub_to_markdown.py`.

---

## Esquema de `plan.json` (lo que esperan los conversores PDF)

```json
{
  "source": "libro.pdf",            // o pásalo con --pdf
  "output_dir": "markdown",         // por defecto ./markdown
  "sections": [
    { "slug": "01_Prefacio",  "title": "Prefacio",  "pages": [9, 10] },
    { "slug": "02_Intro",     "title": "Introducción", "pages": [11, null] },
    { "slug": "03_Cap2",      "title": "Capítulo 2", "pdf": "2 Chapter 2.pdf" }
  ]
}
```
`pages`: `[inicio, fin]` 1-based; `null` = hasta el final. `pdf` (en vez de
`pages`) = un PDF entero como sección (modo un-PDF-por-capítulo).

## Cierre del ciclo (salida)

Markdown limpio → se puede entregar en otro formato con **pandoc**:
`pandoc cap.md -o cap.epub` (o `.docx`, `.pdf`). Útil tras traducir con
[[traducir-md]]. El `.md` también va directo a NotebookLM ([[notebooklm-setup]]).

## Referencia detallada

El repo trae un **manual de operación** (`CLAUDE.md`) y `README.md` /
`tools/README.md` con los límites finos de cada script (sobre todo el manejo de
notas al pie por formato). Si trabajas dentro del repo, `CLAUDE.md` se carga solo.
