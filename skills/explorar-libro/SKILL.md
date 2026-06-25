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

## Reparto del trabajo

- **Herramienta (determinista):** `book_explore.py` extrae el texto del PDF/EPUB
  y busca términos, devolviendo pasajes con **ubicación** (página en PDF,
  capítulo/archivo en EPUB) + contexto, y un **ranking de secciones por densidad**
  de coincidencias. Insensible a mayúsculas y acentos (español).
- **Tú (criterio):** expandes el tema en términos de búsqueda, eliges qué pasajes
  importan, los lees y sintetizas con citas.

## Procedimiento

1. **Expande el tema en términos** (este es el paso de juicio). Para "qué hay
   sobre la melancolía saturnina" → `saturno, melancolía, bilis negra, Krónos,
   humor, abatimiento`. Incluye sinónimos, términos técnicos y variantes (latín,
   griego) propios del campo (astrología, alquimia, filosofía).
2. **Corre la herramienta:**
   ```bash
   python3 ~/.claude/skills/explorar-libro/book_explore.py "RUTA/libro.pdf" \
       --terms "saturno, melancolía, bilis negra, Krónos" --context 2
   ```
   Opciones: `--regex PATRÓN` para patrones; `--context N` líneas alrededor;
   `--max N` tope de coincidencias.
3. **Mira el ranking de secciones** del resumen: las páginas/capítulos con más
   coincidencias son donde el tema se concentra. **Lee esos** (con la herramienta
   Read sobre el `.md` si ya está convertido, o pidiendo más contexto/`--max`).
4. **Sintetiza** lo encontrado: qué dice el libro sobre el tema, **citando
   página/capítulo** (p. ej. "en pág. 91–93 desarrolla…"), para que el usuario
   pueda ir directo. Distingue lo que el texto afirma de tu interpretación.

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
