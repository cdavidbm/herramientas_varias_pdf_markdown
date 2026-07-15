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

## 🖥️ Instalar en una máquina nueva (setup)

Clonar **no** deja todo listo por sí solo: trae el código y el `CLAUDE.md`, pero
las skills, las herramientas del sistema, los modelos de OCR y los MCP no viven en
git. Para dejarlo todo funcionando, un solo comando (idempotente):

```bash
git clone git@github.com:cdavidbm/herramientas_varias_pdf_markdown.git ~/… # o C:\ideas\_La_Forja
cd _La_Forja
bash setup.sh          # instala skills, docling/markitdown, modelos OCR, venv y MCP
```

> **Clona en la misma ruta que la otra máquina** (`C:\ideas\_La_Forja` →
> `/mnt/c/ideas/_La_Forja`): las skills referencian `tools/` por esa ruta.

`setup.sh` reporta lo que necesita **root** (deps base: `poppler-utils`, `pandoc`,
`ocrmypdf`, `tesseract`…) para que las instales tú, y hace el resto sin root.
Al terminar: **reinicia Claude Code** (carga skills y MCP) y abre Claude dentro de
la carpeta (su `CLAUDE.md` se carga solo). NotebookLM es un paso opcional aparte.

**¿Prefieres pedírselo a Claude?** Abre Claude en la carpeta clonada y dile:
*"lee el README y deja este repo instalado y funcionando en esta máquina"* —
correrá `setup.sh` y te guiará con lo que requiera root o login.

---

## 🤖 Cómo se opera (lo maneja Claude, no tú)

Estas herramientas están pensadas para que **las use Claude por ti**. No tienes
que saber cuál aplicar a cada documento: le pides un resultado —"pasa este libro
a markdown", "prepáralo para NotebookLM"— y **Claude diagnostica la fuente y
elige la herramienta solo** (incluido decidir entre un bisturí, OCR o Docling).

El "cerebro" de esa decisión ya está listo en dos sitios:

- **Skill `/forja`** — algoritmo de auto-diagnóstico y enrutado, disponible en
  cualquier carpeta.
- **[`CLAUDE.md`](CLAUDE.md)** — el mismo manual de operación, que Claude Code
  carga automáticamente al trabajar **dentro de este repo**.

Y para el paso siguiente del flujo:

- **Skill `/traducir-md`** — traduce el markdown por capítulo preservando las
  notas `[^N]`, los encabezados y el formato, con glosario de términos para
  mantener consistencia en todo el libro.
- **Skill `/youtube`** — convierte un video de YouTube en markdown de estudio a
  partir de sus subtítulos (incluidos los **auto-generados**): sin marcas de
  tiempo, con puntuación, párrafos y ortografía restaurados por el agente, sin
  resumir nada. Si el video **no tiene subtítulos**, transcribe el audio con ASR
  local (faster-whisper). También descarga audio, video y subtítulos con `yt-dlp`,
  y accede a videos privados/con login vía cookies.

Tú solo decides lo que Claude no puede inferir (idioma de traducción, qué
front-matter descartar). Lo demás se detecta.

---

## ✨ Qué resuelve

| Problema del documento | Herramienta |
|---|---|
| Un PDF largo que hay que partir por capítulos | `split_pdf.py` + `detect_chapters.py` |
| Escaneo con **dos páginas por hoja** (spreads) | `split_pdf_spreads.py` |
| Escaneo **sin capa de texto** (solo imágenes) | `ocrmypdf` (OCR) → luego el bisturí que toque |
| PDF digital limpio → markdown por secciones | `pdf_sections_to_markdown.py` |
| Carpeta de **un PDF por capítulo** con notas a pie | `pdf_chapters_to_markdown.py` |
| Libro escaneado (post-OCR) con citas Harvard | `pdf_book_to_markdown.py` |
| PDF **complejo** (tablas, fórmulas, multicolumna) donde la extracción falla | `docling` (conversor ML de alta fidelidad) |
| **Cualquier EPUB** → markdown por capítulo | `build_plan.py` + `epub_to_markdown.py` |
| EPUB **ilustrado** (figuras, glifos musicales) | `epub_illustrated_to_markdown.py` |
| RTF de ePubLibre/Titivillus con notas agrupadas | `rtf_to_markdown.py` |
| **Office** (docx, pptx, xlsx), html o imágenes → markdown | `markitdown` (o su MCP) |
| **Video de YouTube** → markdown de estudio (subtítulos, incl. auto-generados) | `yt_transcript.py` + skill `/youtube` |
| Video de YouTube **sin subtítulos** → transcript por audio (ASR local) | `yt_audio_transcribe.py` (faster-whisper) |
| Bajar **audio/video/subtítulos** de YouTube | `yt_media.py` (yt-dlp) |

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
├── forja_common.py               slugify / plan.json / require_tool comunes
│
│  ── Partir y sondear el PDF ──
├── split_pdf.py                  PDF → PDFs por capítulo (poppler)
├── split_pdf_spreads.py          escaneo 2-up → 1-up (mutool)
├── detect_chapters.py            detecta marcadores de capítulo en un PDF
├── pdf_headings.py               sonda: jerarquía de títulos por tamaño de fuente
├── pdf_blocks.py                 sonda: bloques con fuente/tamaño/posición
│
│  ── PDF → markdown (elige según la señal que necesites) ──
├── pdf_rich_to_markdown.py       ⭐ CURSIVAS + columnas paralelas (académico)
├── pdf_sections_to_markdown.py   PDF digital limpio   → markdown por sección
├── pdf_chapters_to_markdown.py   PDFs pre-partidos    → markdown + notas a pie
├── pdf_book_to_markdown.py       PDF escaneado (OCR)  → markdown saneado
├── ocr_text_to_markdown.py       sidecar .txt de OCR  → markdown
│
│  ── EPUB / RTF / LaTeX ──
├── build_plan.py                 EPUB → plan.json (genérico, spine + índice)
├── epub_to_markdown.py           EPUB → markdown por capítulo (notas → [^N])
├── epub_illustrated_to_markdown.py  EPUB con figuras → markdown + imágenes
├── rtf_to_markdown.py            RTF → markdown (deriva las secciones solo)
├── latex_to_markdown.py          libro en LaTeX → markdown (starfont → Unicode)
│
│  ── OCR ──
├── ocr_setup.sh                  venv + modelos tessdata_best multilingües
├── ocr_incremental.py            OCR por lotes con checkpoint + resume
├── ocr_preprocess.py             deskew / contraste / binarización
├── ocr_corruption.py             señala texto que el OCR dejó corrupto
│
│  ── Docling ──
├── docling_incremental.py        Docling por lotes con checkpoint + resume
├── docling_clean.py              artefactos propios de Docling
│
│  ── Limpieza y estructura ──
├── clean_markdown.py             running-heads, guion suave, base64 → archivo
├── split_chapters.py             trocea un .md en capítulos
├── chapter_bounds.py             límite REAL del capítulo contra el PDF
├── footnotes_rebuild.py          reconstruye las notas [^N] de un escaneo
├── limpiar_academico.py          orquesta los 3 fix_* de abajo
├── fix_ligatures.py              corrupción de ligaduras (fi→W) de OUP/Distiller
├── fix_diacritics.py             diacríticos rotos + NFC
├── fix_ordinals.py               ordinales volados: 4 lh → 4th (casas, siglos)
├── clean_openings.py             portadillas y capitulares
├── astro_glyphs.py               señala celdas de glifos ♄♃♂ rotos por OCR
│
│  ── QA y exploración ──
├── check_completeness.py         ¿se perdió texto? (md vs pdftotext -layout)
├── book_index.py                 índice FTS5 para buscar en una carpeta
├── book_map.py                   mapa de un markdown ya convertido
│
│  ── Salida ──
├── md_to_pdf.py                  ⭐ libro → PDF maquetado (memoir + starfont)
│
│  ── YouTube ──
├── yt_transcript.py              YouTube/local subs → texto limpio sin timestamps
├── yt_audio_transcribe.py        video sin subtítulos → transcript por ASR (Whisper)
├── yt_media.py                   yt-dlp: baja audio/video/subtítulos/metadatos
├── asr_setup.sh                  venv de faster-whisper
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

# YouTube (skill /youtube, yt_transcript.py, yt_media.py):
pip install --user yt-dlp                 # o: uv tool install yt-dlp
sudo apt-get install ffmpeg               # para --audio, --video combinado y ASR

# YouTube sin subtítulos → transcript por audio (yt_audio_transcribe.py):
bash tools/asr_setup.sh                   # venv con faster-whisper (ASR local)
```

Todos los scripts son Python 3 + utilidades de línea de comandos; sin servicios
en la nube ni claves de API.

---

## 💡 Filosofía

Una herramienta entra a esta suite por **ganancia neta**, no por coleccionismo.
Antes que añadir un conversor «universal» que produzca markdown mediocre, se
prefieren bisturíes específicos que produzcan markdown *de calidad editorial* —
porque el destino es leer, estudiar y traducir, no solo indexar.
