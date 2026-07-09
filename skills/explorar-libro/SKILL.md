---
name: explorar-libro
description: Explora un PDF o EPUB en una ruta y encuentra qué hay sobre un tema, sin leer el libro entero. Localiza los pasajes relevantes con su página/capítulo y los sintetiza con citas. Activa con "/explorar-libro" o intención como "mira tal libro en tal ruta y busca qué hay sobre X", "escanea este pdf/epub sobre tal tema", "qué dice este libro acerca de…".
---

# Explorar Libro — búsqueda temática localizada en PDF/EPUB

Para la petición recurrente *"mira tal libro en tal ruta y dime qué hay
interesante sobre X"*. En vez de leer el libro entero (caro y no escala), una
herramienta **localiza** los pasajes y tú **lees solo esos** y sintetizas.

## Cuándo se activa

- Explícito: `/explorar-libro`
- Intención: "mira este libro y busca sobre X", "escanea este PDF/EPUB sobre…",
  "qué dice este libro acerca de…".

## Elige la herramienta según el objetivo (automático)

- **Carpeta de markdown / corpus** (varios libros ya convertidos, p. ej. una
  serie) → usa el **índice FTS5** `tools/book_index.py`. Es lo mejor para ahorrar
  tokens: indexa una vez y consulta al instante, con ranking bm25.
- **Un solo PDF o EPUB** (aún sin convertir) → usa `book_explore.py`
  (`~/.claude/skills/explorar-libro/book_explore.py`), que extrae y localiza por
  página (PDF) o capítulo (EPUB).

En ambos: **tú (criterio)** expandes el tema en términos, eliges los pasajes
relevantes, los lees y sintetizas con citas.

## Procedimiento — corpus / carpeta (índice FTS5)

```bash
T=/mnt/c/ideas/_La_Forja/tools
python3 $T/book_index.py query "RUTA/markdown" "reed flute, nay, longing" --top 8
```
- Construye el índice solo si falta o cambió (se guarda como `.forja_index.db`
  DENTRO de la carpeta; git lo ignora). `build` y `status` son subcomandos.
- Devuelve pasajes rankeados con `archivo › encabezado` + fragmento. **Lee solo
  los archivos citados** (Read) y sintetiza. Insensible a acentos.
- Para orientarte primero, `python3 $T/book_map.py "RUTA/markdown"` da el mapa
  (archivos, títulos, palabras, notas) sin leer el contenido.

## Procedimiento — un solo archivo (PDF/EPUB)

1. **Expande el tema en términos** (paso de juicio). Para "melancolía saturnina"
   → `saturno, melancolía, bilis negra, Krónos, humor, abatimiento`. Incluye
   sinónimos y variantes (latín, griego) del campo.
2. **Corre la herramienta:**
   ```bash
   python3 ~/.claude/skills/explorar-libro/book_explore.py "RUTA/libro.pdf" \
       --terms "saturno, melancolía, bilis negra, Krónos" --context 2
   ```
   Opciones: `--regex PATRÓN`; `--context N`; `--max N`.
3. **Mira el ranking de secciones**: las páginas/capítulos con más coincidencias
   son donde el tema se concentra. **Lee esos**.
4. **Sintetiza** citando página/capítulo (p. ej. "en pág. 91–93 desarrolla…").
   Distingue lo que el texto afirma de tu interpretación.

## Casos y límites

- **PDF escaneado sin texto:** la herramienta avisa y sugiere
  `ocrmypdf in.pdf out.pdf` (→ skill [[forja]]); córrelo y reintenta.
- **Cobertura:** es búsqueda por términos, no semántica. Si el primer barrido da
  poco, **amplía los términos** (otra ronda) antes de concluir que "no hay nada".
  Di qué términos probaste.
- **Para Q&A semántico profundo** sobre todo el libro (no solo localizar
  términos), la opción más potente es subirlo a **NotebookLM** ([[notebooklm-setup]])
  y preguntar; ofrécelo si el usuario quiere ir más allá de la exploración local.
- Si tras explorar el usuario quiere el libro completo en markdown, encadena con
  la skill [[forja]].
