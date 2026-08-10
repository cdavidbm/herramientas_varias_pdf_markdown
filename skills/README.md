# Skills de La Forja (para Claude Code)

Se instalan en `~/.claude/skills/` (scope *user* = disponibles en cualquier carpeta)
y Claude las **activa solas** al detectar la intención.

## Instalación en un equipo nuevo

```bash
bash install-skills.sh      # copia skills/* -> ~/.claude/skills/ y PODA lo retirado
```
Reabre Claude Code y estarán disponibles. **Pero** las skills usan herramientas
externas que este repo NO contiene; instálalas (abajo).

El instalador lleva **manifiesto** (`.forja-skills` en el destino): registra qué
instaló, de modo que al retirar una skill del repo también desaparece del equipo.
Antes solo copiaba, y una skill retirada se quedaba instalada para siempre,
desfasada y compitiendo por la misma intención. La poda **solo toca lo que vino de
este repo**: las skills ajenas no se rozan aunque estén en la misma carpeta.

## Las skills

| Skill | Para qué |
|---|---|
| `forja` | **Todo el trabajo con libros y documentos**: convertir, OCR, aparato de notas, traducir, verificar, prosa, citas, explorar y maquetar |
| `youtube` | Vídeo de YouTube → markdown de estudio (subs manuales o automáticos, o ASR local si no hay) |

## Por qué son dos y no once

Hasta ahora había **diez skills de La Forja**, una por fase. Sobre el papel era
ordenado; en la práctica el usuario **nunca elige skill** —describe un resultado y el
agente decide—, así que los diez nombres no le servían a nadie: eran diez descripciones
compitiendo por la misma intención, y su único efecto era que el agente tuviera que
acertar cuál cargar. El fallo que importa no es elegir mal, es no cargar ninguna e
improvisar un script suelto teniendo la herramienta hecha.

`forja` es ahora un **enrutador delgado**: identifica la fase y lee solo el archivo de
`referencias/` que necesita. Así el criterio detallado sigue disponible, pero no se carga
entero para arreglar una cita. Y el orden del flujo —reconstruir el aparato ANTES de
traducir, verificar ANTES de traducir— queda en un solo sitio en vez de repetido en
cada skill.

`youtube` sigue aparte porque su intención no se confunde con nada y está en producción.

Patrón, que no cambia: **lo mecánico → script determinista**; **lo de criterio → la skill**.

## Herramientas de ahorro de tokens (en `tools/`, sin instalar nada)

- **`book_index.py`** — índice de búsqueda **FTS5** (SQLite, insensible a acentos)
  sobre una carpeta de markdown: `build` / `query "términos"` / `status`. El
  índice `.forja_index.db` se guarda junto a los libros (git-ignored). Recupera
  solo los pasajes relevantes → se lee mucho menos. Puro beneficio, no toca calidad.
- **`book_map.py`** — mapa estructural (archivos, títulos, palabras, notas) para
  orientarse sin leer el contenido.

## OCR de alta calidad (fase de OCR de `/forja`)

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
# La mayoría de los scripts .py usan solo la stdlib, pero algunos necesitan
# librerías ligeras de PyPI (EPUB, RTF, estructura por fuente). Instálalas con:
#   python3 -m pip install --user beautifulsoup4 striprtf pdfminer.six
# (o `bash setup.sh`, que lo hace por ti). Ver requirements.txt en la raíz del
# repo para el inventario completo — opencv/faster-whisper van en venvs aparte.
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
for s in forja youtube; do
  test -f ~/.claude/skills/$s/SKILL.md && echo "✅ $s" || echo "❌ $s"
done
ls ~/.claude/skills/forja/referencias/ | wc -l    # 10 archivos de referencia
```
