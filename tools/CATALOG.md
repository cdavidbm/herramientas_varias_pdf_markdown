# Catálogo de La Forja — todas las tools de un vistazo

> Autogenerado por `catalog.py` desde los docstrings. **No editar a mano**; corre `python3 tools/catalog.py --write`. `⚠` = no mencionada en CLAUDE.md.

## Puertas / orquestadores
- `fix_ocr.py` — puerta ÚNICA a las correcciones de texto OCR de La Forja.
- `forja_limpiar.py` — PUERTA ÚNICA de post-limpieza de un libro convertido.
- `limpiar_academico.py` — Orquestador de POST-LIMPIEZA para markdown de libros

## Conversores (bisturíes)
- `epub_illustrated_to_markdown.py` — convert an image-heavy EPUB (music theory,
- `epub_to_markdown.py` — Convert a complex EPUB into one self-contained markdown
- `latex_to_markdown.py` — Convierte un libro en LaTeX a markdown de estudio (para
- `ocr_text_to_markdown.py` — Slice a plain OCR TEXT dump into per-chapter markdown.
- `pdf_book_to_markdown.py` — Convert a single PDF book (post-OCR or text-layer)
- `pdf_chapters_to_markdown.py` — Convert one or more pre-split chapter PDFs
- `pdf_rich_to_markdown.py` — Extrae un PDF DIGITAL a markdown conservando las
- `pdf_sections_to_markdown.py` — Split a PDF into one markdown file per logical
- `rtf_to_markdown.py` — Convert an RTF book into per-section markdown,

## Sondas / diagnóstico
- `book_index.py` — Índice de búsqueda full-text LOCAL sobre una carpeta de markdown.
- `book_map.py` — Mapa estructural compacto de una carpeta de markdown (o un .md).
- `detect_chapters.py` — Scan a PDF for candidate chapter start pages.
- `ocr_corruption.py` ⚠ — Detecta texto OCR probablemente CORRUPTO (sin diccionario).
- `pdf_blocks.py` — Recover BLOCK QUOTES from a DIGITAL pdf by font size + indentation.
- `pdf_headings.py` — Recover heading HIERARCHY from a DIGITAL pdf by font size.

## Split / manipulación PDF
- `docling_incremental.py` — Run Docling over a PDF in page BATCHES, saving progress
- `ocr_incremental.py` — Run ocrmypdf over a PDF in page BATCHES, saving each batch to
- `split_chapters.py` — Split a single Markdown file into one file per chapter.
- `split_pdf.py` — Split a PDF into multiple PDFs based on a chapters plan.
- `split_pdf_spreads.py` — Turn a 2-up scanned PDF (two book pages per physical

## Limpieza post-conversión
- `astro_glyphs.py` — Astrological-glyph reference + OCR-garble flagger for Markdown
- `clean_markdown.py` — Post-process Docling (or similar) Markdown into clean,
- `clean_openings.py` — Limpia la BASURA DE APERTURA de capítulo que dejan muchos PDF
- `docling_clean.py` — Limpia los ARTEFACTOS SISTEMÁTICOS que introduce Docling al
- `fix_diacritics.py` — Repara la corrupción de DIACRÍTICOS típica de PDF de
- `fix_ligatures.py` — Repara la corrupción de LIGADURAS típica de PDF de editoriales
- `fix_ordinals.py` — Repara los ORDINALES que el OCR destroza en libros escaneados
- `fix_roman_numerals.py` — corrige numerales romanos corrompidos por el OCR.
- `flag_ocr_artifacts.py` — DETECTA (no corrige) ruido de OCR camuflado en markdown.
- `footnotes_rebuild.py` — Rebuild Markdown footnotes `[^N]` from OCR output where
- `ocr_preprocess.py` ⚠ — Limpia una imagen de página ANTES del OCR (escaneos malos).
- `ocr_spellfix.py` — corrección ortográfica CONSERVADORA de erratas de OCR.
- `verse_paragraphs.py` — reformatea texto VERSIFICADO a UN PÁRRAFO POR VERSO.

## Verificación / auditoría
- `audit_conversion.py` — Puerta de auditoría para una conversión PDF→markdown por
- `chapter_bounds.py` — Encuentra el límite REAL de cada capítulo en un markdown de
- `check_completeness.py` — Detecta (y opcionalmente REPARA) el TEXTO PERDIDO durante
- `index_rebuild.py` — Reconstruye el ÍNDICE ANALÍTICO de un libro contra el PDF que

## Salida / build
- `build_plan.py` — Generate a plan.json for ANY EPUB, ready for epub_to_markdown.py.
- `md_to_pdf.py` — Convierte markdown de estudio (suite La Forja) a un **PDF bello**,

## YouTube
- `yt_audio_transcribe.py` — Transcribe el AUDIO de un video (o un archivo local)
- `yt_media.py` — Front door to yt-dlp for La Forja: probe a video and download its
- `yt_transcript.py` — YouTube subtitles → clean, de-duplicated, timestamp-free text.

## Librería compartida
- `catalog.py` — genera el CATÁLOGO ÚNICO de todas las tools de La Forja.
- `forja_common.py` — Lo que TODOS los conversores de La Forja hacían por su cuenta.

## Otros
- `agy_consolidate.py` ⚠ — Cose las transcripciones POR PÁGINA de agy/Gemini (o de
- `agy_transcribe.py` ⚠ — Orquesta la TRANSCRIPCIÓN VISUAL de un rango de páginas de un
- `crop_figure.py` ⚠ — Recorta una FIGURA (carta astral, diagrama, rueda zodiacal…)
- `ocr_geometry.py` — separa CUERPO / NOTAS AL PIE / running-head y reconstruye

