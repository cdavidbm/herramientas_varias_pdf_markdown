---
name: forja-flujo
description: Orquestación AUTOMÁTICA del flujo de libros de La Forja. Detecta la intención del usuario y encadena solo las skills necesarias (convertir, indexar, explorar, traducir, QA, prosa, citas) sin que el usuario invoque nada. Activa con intención de trabajo con libros/documentos de principio a fin ("procesa este libro", "prepáralo para estudio", "traduce y revisa esta carpeta").
---

# La Forja — Orquestación automática del flujo

El usuario **no invoca skills**: describe un resultado y **tú detectas qué pasos
hacen falta y los encadenas solos**, corriendo lo determinista en scripts e
interviniendo solo donde hay criterio. Objetivo: máxima calidad con el mínimo de
tokens (leer solo lo necesario).

## Principio de ahorro (sin tocar calidad)

- **Deja que las herramientas lean/localicen; tú ingieres solo lo que exige
  juicio.** Nunca resumas ni comprimas el texto fuente que debes traducir o
  analizar de cerca — eso sí dañaría la calidad.
- **Oriéntate barato antes de leer:** `tools/book_map.py` (estructura) y
  `tools/book_index.py` (búsqueda) evitan cargar libros enteros al contexto.
- **Previsualiza** (`--dry-run`) y **verifica con scripts** en vez de releer.

## Detección → qué encadenar (automático)

| Lo que pide el usuario (intención) | Cadena automática |
|---|---|
| "convierte/pasa este libro/carpeta a markdown" | [[forja]] (auto-diagnóstico) → `book_map.py` para confirmar el resultado |
| "mira este libro/carpeta y dime qué hay sobre X" | [[explorar-libro]]: carpeta → `book_index.py`; archivo → `book_explore.py` → leo solo lo top y sintetizo con citas |
| "traduce este libro/capítulo/carpeta" | (si es PDF/EPUB) [[forja]] → [[traducir-md]] → [[qa-traduccion]] → (a criterio) [[revisar-prosa]] |
| "revisa/corrige este texto" | [[revisar-prosa]] (script `proofread.py` + criterio) |
| "verifica esta traducción" | [[qa-traduccion]] (`check_translation.py` + criterio) |
| "gestiona/añade la bibliografía" | [[citas]] (`check_citations.py` + `pandoc --citeproc`) |
| "arma/compila el libro final" | `pandoc` de los `.md` → EPUB/DOCX/PDF (cierre del ciclo) |

## Reglas de orquestación

1. **Anuncia el plan en una línea** antes de una cadena larga ("Convierto →
   verifico estructura → traduzco → QA"), y ejecuta sin pedir permiso paso a paso.
2. **Solo pregunta lo no inferible:** idioma destino, qué front-matter descartar,
   o si conservar salidas voluminosas. Todo lo demás, decídelo por sondeo.
3. **Corre lo determinista en scripts** (conversión, índice, QA, mapa, citas) y
   reserva tu lectura para lo que requiere juicio (traducir, interpretar, sintetizar).
4. **Encadena de verdad:** al terminar un paso, sigue con el siguiente de la
   cadena sin esperar a que te lo pidan, salvo que aparezca una bifurcación real.
5. **Cita ubicaciones** (archivo › encabezado / página) en toda síntesis.

## Herramientas del repo (fuente de verdad)

`tools/`: conversión (build_plan, epub_to_markdown, pdf_*_to_markdown, split_*,
detect_chapters), **`book_index.py`** (búsqueda FTS5), **`book_map.py`** (mapa).
`skills/`: forja, traducir-md, qa-traduccion, revisar-prosa, citas, explorar-libro,
forja-flujo. Se instalan con `install-skills.sh`. Ver `CLAUDE.md` del repo.
