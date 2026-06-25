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
| `/explorar-libro` | "Mira tal libro y busca qué hay sobre X": localiza pasajes con su página/capítulo | `book_explore.py` |

Patrón: **lo mecánico → script determinista**; **lo de criterio → la skill**.

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
