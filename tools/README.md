# Document Toolbox — PDF & EPUB

Reusable scripts for slicing book-length documents into per-chapter pieces that
are easier to work with (NotebookLM ingestion, targeted reading, RAG sources).

This folder lives inside the `[ALQUIMIA] The Alchemical Virgin Mary` book folder
but is intended as a **shared toolbox**: run the scripts from any book folder by
pointing at them directly, or copy the folder next to a new book.

## Scripts

### PDF → per-chapter PDFs

- `split_pdf.py` — reads `plan.json` (chapter page ranges) and writes one PDF
  per section using poppler's `pdfseparate` + `pdfunite`.
- `detect_chapters.py` — scans a PDF and lists pages whose text looks like a
  chapter marker (`INTRODUCTION`, `CHAPTER X`, `PART I`, `CONCLUSION`,
  `BIBLIOGRAPHY`, …). Use its output when hand-crafting a `plan.json`.

### PDF 2-up → 1-up (decollate book scans)

- `split_pdf_spreads.py` — for books scanned with pages open so every physical
  page contains two book pages side by side. Auto-detects landscape pages via
  aspect ratio and splits each vertically; portrait pages (cover, inserts)
  pass through untouched. Uses `mutool poster` + poppler. Run this **before**
  `split_pdf.py` if the scan is 2-up.

### EPUB → per-chapter Markdown

- `epub_to_markdown.py` — reads `plan.json` (file groupings per logical
  section) and writes one `.md` per section. Handles continuation files,
  resolves pooled footnotes into per-file `[^N]: ...` definitions, preserves
  Arabic/diacritical typography, and skips decorative/page-break markup.
- `build_plan.py` — **generic** plan generator: inspects ANY EPUB and emits a
  `plan.json` automatically. Reads the package document (`.opf`) for the spine
  (canonical reading order) and the table of contents (EPUB3 `nav` or EPUB2
  `.ncx`) for chapter titles, then writes one section per TOC-named chapter,
  merging untitled continuation files (e.g. `Chapter_2a.xhtml`) into the
  preceding chapter and skipping cover/title/copyright/TOC/index cruft
  (English + Spanish). Auto-detects the footnote-pool file and its format.
  Tested on 38 mixed EPUBs (EPUB2/EPUB3, flat and `text/`-rooted, ISBN-prefixed
  filenames, Spanish and English). No per-book editing needed — just eyeball
  the output.
    - `--footnotes auto|none|<file>` — pool detection (default auto).
    - `--keep-frontmatter` — don't drop front-matter cruft.
  **Limits (inherent to file-granularity):** an EPUB that packs many chapters
  into a single `.xhtml` (common in Anna's-Archive rips) yields one coarse
  section per file — the floor is one `.md` per source file. Footnotes only
  resolve when the book uses a pooled notes file referenced by
  `<sup><a href="pool#anchor">` (or `<a href><sup>`); other note structures
  pass through as raw superscripts.

### PDF → per-section Markdown (single PDF, plan-driven)

- `pdf_sections_to_markdown.py` — reads `plan.json` (page ranges per section,
  same shape as `split_pdf.py`) and writes one `.md` per section. Best for
  Calibre-produced PDFs (clean text layer + detailed outline). Undoes soft
  hyphenation, rejoins wrapped lines into paragraphs, strips echoed title.

### PDF → per-chapter Markdown (pre-split chapter files, page-bottom footnotes)

- `pdf_chapters_to_markdown.py` — for books delivered as one PDF per chapter
  (common in academic shares) where each page has classic page-bottom
  footnotes (`^N text...` at the foot). Reads a `plan.json` listing each
  section's slug, title, source PDF, and 1-based page range. Pipeline:
    - drops running heads (configurable patterns), page numbers (arabic +
      lowercase roman + bullet-prefixed `•7`), lone Roman numerals
    - locates per-page footnote zone ("last blank line followed by `^\d+\s+`
      marker"), extracts notes into `## Notes` per chapter
    - splits body paragraphs on indent transitions (`-layout` mode lacks
      blank-line separators between paragraphs)
    - undoes soft hyphens (U+00AD) and end-of-line `-`+lowercase at line
      breaks AND across paragraph joins
    - cross-page sentence join when a paragraph ends without terminal
      punctuation (handles "Hipparchus. Ancient" → next page → "Egypt made…")
    - drops body paragraphs shaped like `^N word...` (multi-page footnote leaks)
    - rewrites inline `wordN` → `[^N]` using same-page footnote nums; second
      pass splits concatenated digit runs (`written1718two` → `[^17][^18]`)

### PDF → per-section Markdown (single PDF, post-OCR, no footnotes)

- `pdf_book_to_markdown.py` — for single-PDF books that use Harvard-style
  in-text citations (`(Author year, page)`) and an end-of-book bibliography
  rather than page-bottom numbered footnotes. Designed for re-OCR'd scans
  (e.g. ocrmypdf + tesseract) where residual OCR artifacts need scrubbing.
  Reads a `plan.json` with `source` PDF, `output_dir`, regex `running_heads`,
  optional `ocr_fixes` (regex/replacement pairs applied to each paragraph),
  and `sections` (slug + title + 1-based `pages: [start, end]`).
  Pipeline:
    - drops running heads, page numbers, lone Roman numerals, lines/paragraphs
      classified as garbage (figure-caption OCR noise, mixed-case mid-word,
      bracket/digit-letter mix, no Spanish stopwords)
    - splits body paragraphs on indent transitions, joins soft-hyphens and
      end-of-line hyphens across both line and paragraph breaks
    - cross-page sentence merge when a paragraph ends without `.!?"”')»`
    - strips leading page numbers stuck to first word (`54facilitó` → `facilitó`)
      and leading non-alpha junk
    - applies `ocr_fixes` regex pairs (case-insensitive supported via `(?i)`)
  Pair with `ocrmypdf --redo-ocr -l spa` to clean up old FineReader/ABBYY OCR
  before running. See `playbook_pdf_book_with_ocr_repair.md`.

### RTF → per-section Markdown (ePubLibre/Titivillus-style)

- `rtf_to_markdown.py` — for RTF books exported from ePubLibre/Titivillus
  where notes live in a pool at the end of the file. Reads a `plan.json`
  with section ranges (line numbers in the rtf-to-text output) + which note
  pool group each section uses. Requires `striprtf`:
  `pip install --user --break-system-packages striprtf`.
  RTF layout heuristics:
    - `' \t...'` = paragraph body (any leading whitespace then a tab)
    - `' Sub-Heading'` (single-space indent, no tab) = sub-section heading
    - `' DIGIT'` + `' ALL_CAPS_TITLE'` = chapter num+title (drop both)
    - `BIBLIOGRAFÍA`/`ANEXO N`/`PRESENTACIÓN` etc. recognized as headings
  Notes pool: starts at the line that equals `notes_header` (default
  `"Notas"`); each note is `[N]\n<body lines>` with trailing `<<` back-link
  stripped; numbering resets at `[1]` to mark group boundaries.

## System requirements

```bash
# for PDF splitting:
sudo apt-get install poppler-utils     # pdfinfo, pdftotext, pdfseparate, pdfunite

# for 2-up → 1-up splitting:
sudo apt-get install mupdf-tools       # mutool

# for EPUB conversion:
# python3 stdlib + beautifulsoup4 (usually already installed)
```

---

## Workflow: PDF 2-up → 1-up (decollate a scanned spread)

Signs the source PDF is 2-up:
- Pages are landscape (width > height).
- Rendering a page shows two book pages side by side.
- NotebookLM reads lines across both halves.

```bash
# quick sanity probe
pdfinfo -f 1 -l 10 "book.pdf" | grep 'size:'
mutool draw -F png -o /tmp/p%d.png -r 60 "book.pdf" 10
```

Run the splitter:
```bash
python3 path/to/tools/split_pdf_spreads.py "book.pdf" --dry-run
python3 path/to/tools/split_pdf_spreads.py "book.pdf"            # writes book_1up.pdf
python3 path/to/tools/split_pdf_spreads.py "book.pdf" out.pdf    # custom output
```

Useful flags:
- `--threshold 1.1` — aspect ratio at which a page is treated as 2-up (default 1.05; raise it if some genuinely landscape-but-single pages are getting split by mistake).
- `--order rl` — right-half first (Arabic, Hebrew, manga).
- `--split-all` — force-split every page, ignore aspect ratio.
- `--split-none-below N` — never split pages before number N (useful when the first few pages are cover/title spreads you want left whole).

The output is a new PDF. **Run the chapter splitter against the 1-up PDF, not the original**.

---

## Workflow: PDF → chapter PDFs

### 1. Identify chapter boundaries

Three reliable ways, in order of preference:

**(a) Read the book's TOC**
```bash
pdftotext -layout -f 1 -l 15 book.pdf -
```
Note each section's **printed** page number from the contents list.

**(b) Find the printed → PDF page offset**
```bash
pdftotext -f 21 -l 21 book.pdf -       # probe candidate PDF pages
```
The first PDF page whose content matches "Chapter 1" (or wherever) gives you
the offset to add to every printed page number in the TOC.

**(c) Let the detector scan it**
```bash
python3 path/to/tools/detect_chapters.py book.pdf
```
Prints all pages whose text opens with a known marker pattern. Combine with
(a) or (b) to settle on correct ranges.

### 2. Write `plan.json` next to the PDF

```jsonc
{
  "source": "book.pdf",
  "output_dir": "chapters",
  "sections": [
    {"title": "Introduction",                     "start": 11, "end": 20},
    {"title": "Chapter 1 - First Chapter Title",  "start": 21, "end": 36},
    {"title": "Chapter 2 - Second Chapter Title", "start": 37, "end": 46}
  ]
}
```

Rules:
- `start`/`end` are **1-based PDF page numbers** (not printed page numbers), inclusive.
- Ranges may skip pages (e.g. drop frontmatter) and are allowed to overlap.
- Paths in the plan are resolved relative to the plan file itself.
- `title` becomes part of the filename (slugified).

### 3. Run the splitter

```bash
python3 path/to/tools/split_pdf.py plan.json --dry-run   # preview
python3 path/to/tools/split_pdf.py plan.json             # execute
```

Filenames come out as `NN_slugified-title.pdf` so they sort in reading order.

---

## Workflow: EPUB → chapter Markdown

### 1. Generate a plan from the EPUB

```bash
python3 path/to/tools/build_plan.py "book.epub" > plan.json
```

The generator reads the EPUB's spine (`.opf`) for reading order and its TOC
(`nav.xhtml` or `toc.ncx`) for chapter titles, merges continuation files
(e.g. `Chapter_2.xhtml` + `Chapter_2a.xhtml`), skips front/back-matter cruft,
auto-detects the footnote pool, and emits a `plan.json` with one entry per
logical section. It is **book-agnostic** — no editing required. Diagnostics
(TOC source, footnote pool, what was skipped) print to stderr.

Always eyeball the result before converting: drop any front/back-matter
sections you don't want, fix a title, or merge two sections by hand.

### 2. Preview and convert

```bash
python3 path/to/tools/epub_to_markdown.py plan.json --dry-run
python3 path/to/tools/epub_to_markdown.py plan.json

# convert a single section by substring match
python3 path/to/tools/epub_to_markdown.py plan.json --only "The Opening"
```

Output is one `.md` per section in `markdown/` (or whatever `output_dir` is set
to). Each file is self-contained: H1 title, body content, then a `## Notes`
section with resolved footnotes if the source had them.

### `plan.json` schema (EPUB)

```jsonc
{
  "epub": "book.epub",
  "output_dir": "markdown",
  "footnote_file": "9780062227621_Footnote.xhtml",   // optional; shared footnote source

  "sections": [
    {
      "title": "1 The Opening, al-Fātiḥah",
      "files": ["9780062227621_Chapter_1.xhtml"],
      "slug": "001_al_Fatihah"                       // optional; autogenerated from title
    },
    {
      "title": "2 The Cow, al-Baqarah",
      "files": ["9780062227621_Chapter_2.xhtml",
                "9780062227621_Chapter_2a.xhtml",
                "9780062227621_Chapter_2b.xhtml"],
      "slug": "002_al_Baqarah"
    }
  ]
}
```

---

## Adapting the EPUB converter to a new book

`build_plan.py` is now generic, and `epub_to_markdown.py` de-duplicates a
heading that merely repeats the plan title (so most books need no tweaking).
Two things may still need attention on an unusual book:

1. **Header-suppression classes.** Beyond the generic title-dedup, the
   converter also hides headings whose CSS class is in `SKIP_HEADER_CLASSES`
   (legacy lists for *The Study Quran* / Davies). Rarely needed now; add a
   class only if a book emits duplicate non-title headers.

2. **Footnote reference pattern.** The converter recognises footnote refs as
   `<sup><a href="*pool#anchor">N</a></sup>` (or `<a href><sup>`) pointing into
   a pooled footnote file, in two body formats (`by_a_id`, `by_p_id`; set
   `footnote_format` in the plan). If a book keeps notes in another structure,
   either point `--footnotes` at the right file or accept raw superscripts.

---

## Files at a glance

| File | Role | Language |
|---|---|---|
| `split_pdf.py`                 | PDF slicer (PDFs out), reads `plan.json` | Python stdlib + poppler CLI |
| `split_pdf_spreads.py`         | 2-up scan → 1-up PDF                     | Python stdlib + poppler + mupdf |
| `detect_chapters.py`           | PDF chapter-marker scanner               | Python stdlib + poppler CLI |
| `pdf_sections_to_markdown.py`  | Single-PDF → per-section markdown        | Python stdlib + poppler CLI |
| `pdf_chapters_to_markdown.py`  | Multi-PDF (pre-split) → markdown w/ page-bottom footnotes | Python stdlib + poppler CLI |
| `rtf_to_markdown.py`           | RTF → per-section markdown w/ pooled notes | Python + striprtf |
| `epub_to_markdown.py`          | EPUB → per-chapter markdown              | Python + beautifulsoup4 |
| `build_plan.py`                | Generates `plan.json` from ANY EPUB (spine+TOC, generic) | Python + beautifulsoup4 |
| `attach_notes_by_chapter.py`   | Post-process to attach pooled notes per chapter | Python + beautifulsoup4 |
| `README.md`                    | This file | — |

## Troubleshooting

- **`pdfseparate not installed`** — install `poppler-utils`.
- **PDF split has wrong content** — off-by-one in `start`/`end`; re-check with
  `pdftotext -f N -l N book.pdf -` for that exact PDF page.
- **EPUB markdown has repeated-title H2 at top** — add the repeating header's
  CSS class to `SKIP_HEADER_CLASSES` in `epub_to_markdown.py`.
- **Missing footnote bodies in markdown** — check that the essay's `<sup><a>`
  refs actually point to the file named in `plan.json → footnote_file`, and
  that the pooled `.xhtml` contains matching `<p class="footnote"><a id="...">`
  paragraphs.
- **EPUB converter warns "missing files for X"** — the plan references files
  that don't exist in the EPUB; remove them or fix the name.
