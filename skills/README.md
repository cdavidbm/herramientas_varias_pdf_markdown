# Skills de La Forja (para Claude Code)

Skills que operan esta suite y el flujo de libros (convertir, traducir, revisar,
explorar). Se instalan en `~/.claude/skills/` (scope *user* = disponibles en
cualquier carpeta). Claude las **activa solas** al detectar la intención, o se
invocan con `/<nombre>`.

## Instalación en un equipo nuevo

```bash
bash install-skills.sh      # copia skills/* -> ~/.claude/skills/
```
Reabre Claude Code y estarán disponibles. **Pero** las skills usan herramientas
externas que este repo NO contiene; instálalas (abajo).

## Las skills

| Skill | Para qué | Script mecánico |
|---|---|---|
| `/forja` | Convierte PDF/EPUB/RTF/Office a markdown por capítulo; **auto-diagnostica** qué herramienta usar | usa los scripts de `tools/` |
| `/traducir-md` | Traduce markdown por capítulo preservando `[^N]`, encabezados y glosario | — |
| `/qa-traduccion` | Verifica que la traducción preservó la estructura | `check_translation.py` |
| `/revisar-prosa` | Corrector editorial (consistencia, tipografía) | `proofread.py` |
| `/citas` | Bibliografía y citas con `pandoc --citeproc` | `check_citations.py` |
| `/explorar-libro` | "Mira tal libro y busca qué hay sobre X": localiza pasajes con su página/capítulo (o índice FTS5 en carpetas) | `book_explore.py`, `tools/book_index.py` |
| `/forja-flujo` | **Orquestación automática**: detecta la intención y encadena las skills solo (sin invocar nada) | — |
| `/ocr` | OCR de máxima calidad para escaneos malos y OCRs corruptos: preprocesado, modelos best multilingües, RapidOCR, detección de corrupción | `tools/ocr_*.py` |

Patrón: **lo mecánico → script determinista**; **lo de criterio → la skill**.

## Herramientas de ahorro de tokens (en `tools/`, sin instalar nada)

- **`book_index.py`** — índice de búsqueda **FTS5** (SQLite, insensible a acentos)
  sobre una carpeta de markdown: `build` / `query "términos"` / `status`. El
  índice `.forja_index.db` se guarda junto a los libros (git-ignored). Recupera
  solo los pasajes relevantes → se lee mucho menos. Puro beneficio, no toca calidad.
- **`book_map.py`** — mapa estructural (archivos, títulos, palabras, notas) para
  orientarse sin leer el contenido.

## OCR de alta calidad (skill `/ocr`)

Ejecuta una vez por equipo:
```bash
bash tools/ocr_setup.sh
```
Descarga modelos **tessdata_best** (eng spa lat grc ell ara fas deu fra ita osd)
a `~/.local/share/forja-tessdata` y crea un venv `~/.local/share/forja-ocr-venv`
con OpenCV + RapidOCR. Nada de esto va en git (son binarios grandes); el script
lo reproduce en cualquier máquina. Tools: `ocr_preprocess.py` (limpieza de
imagen con OpenCV), `ocr_corruption.py` (detecta texto corrupto, stdlib).
Requiere `uv` y red a GitHub.

## Herramientas externas requeridas (NO vienen en git)

**Base (casi todas las skills):**
```bash
sudo apt-get install poppler-utils mupdf-tools pandoc ocrmypdf tesseract-ocr qpdf
# Python 3 con su stdlib basta para los scripts .py (sin dependencias extra).
```

**Conversores de alta fidelidad (para `/forja` con PDF complejos / Office):**
```bash
# requiere uv (https://astral.sh/uv)
uv tool install docling                 # PDFs complejos (tablas, fórmulas)
uv tool install 'markitdown[all]'       # docx/pptx/xlsx/html/imágenes -> md
```

**MCP opcionales (herramientas nativas en el chat; se cargan al reiniciar):**
```bash
claude mcp add -s user markitdown -- uvx markitdown-mcp
claude mcp add -s user youtube     -- npx -y @anaisbetts/mcp-youtube   # transcripciones
```

**NotebookLM** (flujo aparte, opcional): ver `notebooklm-py` —
`uv tool install "notebooklm-py[browser]"`, descargar Chromium del propio
playwright, `notebooklm skill install`, `notebooklm login`.

## Comprobación

```bash
for s in forja traducir-md qa-traduccion revisar-prosa citas explorar-libro; do
  test -f ~/.claude/skills/$s/SKILL.md && echo "✅ $s" || echo "❌ $s"
done
```
