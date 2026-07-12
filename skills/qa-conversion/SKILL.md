---
name: qa-conversion
description: Control de calidad de una conversión PDF→markdown ANTES de traducir o publicar. Verifica que NO se perdió texto (alinea contra pdftotext -layout) y detecta corrupciones típicas de PDF académicos (ligaduras fi→W, diacríticos rotos, portadillas, running-heads). Activa con "/qa-conversion" o intención como "verifica que la conversión quedó completa", "revisa que no se perdió texto del PDF", "controla la calidad del markdown convertido".
---

# QA de Conversión (suite La Forja)

Verifica que un markdown recién convertido **refleja íntegra y fielmente su PDF**.
Es la puerta de calidad ENTRE convertir ([[forja]]) y traducir ([[traducir-md]]):
traducir desde una fuente incompleta propaga el defecto a todo el idioma destino.

## Por qué existe (lección aprendida)

Los bisturíes (`pdf_chapters_to_markdown.py` y afines) pueden **dejar caer texto
sin avisar** —años, cláusulas enteras— según el layout (heurística de zona de
notas, unión de párrafos). Y los PDF de editoriales académicas (OUP/Distiller)
llegan con **ligaduras convertidas en mayúsculas** (conWrmation) y **diacríticos
rotos** (Wolfenb€ uttel, Martı´n) que parecen erratas pero son texto corrupto.
Nada de esto se ve a simple vista: hay que **medirlo**.

## Cuándo se activa

- Explícito: `/qa-conversion`
- Intención: "verifica que la conversión quedó completa", "no se perdió texto",
  "revisa el markdown convertido antes de traducir".

## Entradas

- El/los `.md` convertidos y su **PDF fuente** (de capítulo, o el libro grande con
  el rango de páginas de cada sección).

`T = tools/` del repo (o `/mnt/c/ideas/_La_Forja/tools`).

## Chequeo 1 — COMPLETITUD (lo más importante)

Alinea cada markdown contra una referencia completa (`pdftotext -layout`) y lista
el texto perdido:

```bash
# PDF de capítulo:
python3 $T/check_completeness.py cap.pdf ./markdown/cap.md
# sección extraída de un rango del libro grande:
python3 $T/check_completeness.py libro.pdf ./markdown/11_Notes.md --pages 304-365
```

- Sale con código 1 y lista los tramos si falta texto.
- **Reparar** (revisa el reporte primero): añade `--repair`. Reinserta los tramos
  con mayúsculas/puntuación correctas.
- **Falsos positivos:** front-matter que quitaste a propósito, u órdenes de lectura
  revueltos alrededor de imágenes → exclúyelos con `--exclude "trozo del texto"`.
- Mejor señal en **prosa a una columna** (bisturí). En back-matter reordenado por
  Docling (notas/índice a columnas) el conteo es orientativo, no exacto.

## Chequeo 2 — CORRUPCIÓN de caracteres

```bash
python3 $T/fix_ligatures.py ./markdown/*.md --report     # fi→W, ff→V… (no escribe)
python3 $T/fix_diacritics.py ./markdown/*.md --report    # ı/€/acentos
python3 $T/ocr_corruption.py ./markdown/*.md             # basura OCR genérica
```

Si hay correcciones que aplicar, limpia todo de una vez:

```bash
python3 $T/limpiar_academico.py ./markdown          # ligaduras+diacríticos+aperturas
python3 $T/limpiar_academico.py ./markdown --no-openings   # para notas/índice
```

⚠️ El corrector de ligaduras protege nombres propios CamelCase (LaVey, RavenWolf),
pero **verifica a ojo** los nombres poco comunes tras limpiar.

## Chequeo 3 — Higiene de markdown (a ojo)

- ¿Cada archivo empieza con un `# H1` correcto? ¿Sin portadillas revueltas
  ("APTER ONE / CH") ni capitulares partidas ("T he")? → `clean_openings.py`.
- ¿Running-heads de página coladas como texto o encabezados? ¿Notas `[^N]` bien
  reconstruidas por capítulo (no en índices/bibliografía)?

## Salida

Informe breve por sección: 🔴 texto perdido / corrupción sin resolver · 🟡 dudas
(nombres, falsos positivos) · 🟢 completo y limpio. **No des una conversión por
buena —ni la pases a traducir— hasta que el chequeo 1 dé 0 lagunas** (salvo falsos
positivos justificados).
