# Inventario del «Algoritmo de diagnóstico» (869 líneas)

Clasificación bloque a bloque de la sección más grande del `CLAUDE.md`, hecha antes de
reescribir nada. **Ninguna lección se borra sin que conste dónde queda alojada**: ese es el
único criterio de este documento.

Método: se segmentó la sección en 79 bloques de ≥3 líneas (una viñeta o una cita = una
lección) y se contrastó cada uno con el docstring de la herramienta que nombra y con los
tests de `forja/`. El solape con el docstring se midió por vocabulario común (umbral 45 %),
así que las fronteras entre B y C son aproximadas y hay que revisarlas a mano; los recuentos
de líneas sí son exactos.

## Resumen

| | bloques | líneas | qué se hace |
|---|---:|---:|---|
| **A** — ya vive en un test de `forja/` | 13 | 141 | se sustituye por un puntero de 1-2 líneas |
| **B** — duplicado con el docstring de su tool | 23 | 227 | se sustituye por un puntero de 1 línea |
| **C** — pertenece a una tool pero solo está aquí | 7 | 116 | **se mueve al docstring** y luego puntero |
| **D** — sin herramienta: criterio o lección sin hogar | 36 | 328 | se decide una a una (ver abajo) |
| | **79** | **812** | |

Las 57 líneas restantes hasta 869 son encabezados, comandos sueltos y aire.

**Proyección honesta:** A+B+C son 43 bloques y **484 líneas que hoy están escritas dos
veces**. Convertidas en punteros quedan en unas 60. El grueso de lo que hay que pensar es D.

---

## A — Ya vive en un test (13 bloques, 141 líneas)

Estas lecciones ya **actúan solas**: si alguien rompe la guarda, el test lo caza. En el
`CLAUDE.md` basta un puntero al módulo.

| líneas | lección | dónde vive ahora |
|---:|---|---|
| 22 | Hebreo compuesto con fuente ASCII | `hebreo_sp_a_unicode.py` (docstring) |
| 18 | Volados aplanados por un reprocesador | `forja.aparato` · `test_aparato.VoladosAplanados` |
| 17 | Titulillos fundidos al cuerpo | `forja.paginas` · `test_paginas.Titulillos` |
| 13 | PDF de Acrobat ClearScan | `clearscan_to_markdown.py` · `test_pdfxml` |
| 11 | Separar notas por cadena ascendente: 4 trampas | `forja.aparato` · `test_aparato.Cadena` |
| 10 | Aparato pegado sin sangría fiable | `forja.aparato.separar_por_cadena` |
| 10 | El conversor se come la primera línea de la página | `forja.paginas.es_titulillo` |
| 9 | PDF digital donde la cursiva importa | `forja.pdfxml` · `test_pdfxml.CursivaAbreviada` |
| 7 | Una nota sin llamada no se imprime | `forja.aparato.auditar` |
| 7 | Pool de notas al final del libro | `forja.aparato.repartir` · `test_aparato.Reparto` |
| 6 | Los `fontspec` son globales (ClearScan) | `forja.pdfxml.fontspecs` |
| 6 | Los `fontspec` son globales (pdfxml) | `forja.pdfxml.fontspecs` |
| 5 | Nunca contar llamadas con «no seguido de dos puntos» | `forja.aparato.llamadas` · guarda 1 |

**Ojo con dos de ellas.** Los `fontspec` aparecen DOS VECES en la sección, en §3b, con
palabras distintas: es la misma lección escrita dos veces porque cada conversor la aprendió
por su cuenta. Ya está unificada en el código; en el documento debe quedar una sola.

## B — Duplicado con el docstring de su herramienta (23 bloques, 227 líneas)

El texto del `CLAUDE.md` y el del docstring dicen lo mismo. Como `tools/CATALOG.md` se
autogenera desde los docstrings, la copia del manual es la que sobra.

`cose_parrafos` (23) · `citas_en_bloque` (17) · `forja_limpiar` (16) · `pdf_restore_digits`
(16) · `rescata_capitulos` (12) · `audit_conversion` (12) · `index_rebuild` (11) ·
`ocr_spellfix` (11) · `flag_ocr_artifacts` (10) · `limpia_dudas` (10) · `pdfxml_to_markdown`
(10) · `embed_figures_from_captions` (9) · `coteja_aparato` (9) · `verse_paragraphs` (8) ·
`fix_roman_numerals` (8) · `normaliza_autores` (7) · `chapter_bounds` (7) ·
`pdf_rich_to_markdown` (7) · `reflow_columns` (6) · `fix_markup` (5) · `fix_ordinals` (5) ·
`fix_ligatures` (5) · `check_completeness` (3)

## C — Pertenece a una tool pero SOLO está aquí (7 bloques, 116 líneas)

Estas hay que **moverlas primero al docstring** y solo después recortar. Si se borran del
manual sin moverlas, se pierden.

| líneas | lección | destino |
|---:|---|---|
| 62 | Escaneos 2-up: cortar por el lomo, nunca por la caja de texto | `split_pdf_spreads.py` / `split_scan_spreads.py` |
| 14 | `--cell-gap` y `--keep-lines` para índices y tablas | `pdfxml_to_markdown.py` |
| 12 | `chars/5pp` bajo → OCR; capa en blanco → `--tess-pdf` | `ocr_incremental.py` |
| 11 | Los EPUB de Calibre casi nunca usan `<i>`: va en clase CSS | `epub_to_markdown.py` |
| 6 | Escaneo largo → procesar por lotes con checkpoint | `docling_incremental.py` |
| 6 | Dos estilos de OCR en la reconstrucción de notas | `footnotes_rebuild.py` |
| 5 | Nombres de archivo en Unicode descompuesto (NFD) | `forja.comun` (afecta a todo) |

El bloque de 62 líneas de los 2-up es el mayor de toda la sección y **no tiene docstring
donde caer**: cubre dos herramientas y tres patologías distintas (2-up normal, rotación
horneada, cuadernillo girado 90°). Merece decisión aparte.

## D — Sin herramienta (36 bloques, 328 líneas)

Aquí está el trabajo de verdad. Se subdividen en dos cosas muy distintas:

### D1 — Criterio humano y procedimiento: SE QUEDA (~120 líneas)

Es el `CLAUDE.md` legítimo, lo que ningún test puede sustituir:

- el **orden del flujo** (convertir → reconstruir notas → traducir → PDF) y por qué;
- el **enrutado por formato** y el árbol de decisión bisturí/Docling;
- la **interpretación del ratio**: engaña con figuras, se derrumba en bilingües, hay que
  medirlo en un tramo sin notas ajenas. Es lectura de una cifra, no una comprobación
  automatizable;
- los **límites honestos** (escaneo muy degradado, tablas de encabezado apilado);
- «la apertura de capítulo no lleva titulillo», «el índice impreso es el mejor contraste»:
  señales para que decida una persona.

### D2 — Lección sin hogar: CANDIDATA A CÓDIGO (~208 líneas)

Son guardas medidas que hoy no actúan solas. Cada una es una tool o un módulo que falta:

| líneas | lección | a dónde iría |
|---:|---|---|
| 32 | Aparato de un escaneo: el número no se lee, se CUENTA | `forja.aparato`, estrategia nueva |
| 18 | Una nota que falta con su llamada no rompe ningún balance | `forja.aparato.auditar` (contra la fuente) |
| 16 | Las llamadas se comen cifras si el margen está recortado | detector en `forja.aparato` |
| 16 | Escaneo grande: extraer la imagen, no rasterizar | `forja` (o docstring de `ocr_incremental`) |
| 14 | Cifras del cuerpo tomadas por llamadas | ya casi cubierto por `cadena_ascendente` |
| 12 | Cursivas de un escaneo puro por inclinación del trazo | `clearscan_to_markdown` (docstring) |
| 12 | Tres defectos de EPUB de editorial | `epub_to_markdown` (docstring) |
| 11 | Subtítulos de sección pegados al párrafo | tool nueva o `forja.paginas` |
| 10 | El aparato crítico latino numera las líneas | control en `forja.aparato` |
| 10 | Un encabezado mal colocado esconde una laguna | ratio POR CAPÍTULO en la verificación |
| … | (el resto, de 4 a 9 líneas cada uno) | ver listado completo abajo |

---

## Qué propongo hacer, y en qué orden

1. **C primero** (7 bloques): mover al docstring lo que aún no está. Es lo único que puede
   perderse si se recorta antes de tiempo.
2. **B y A después** (36 bloques, 368 líneas): sustituir por punteros. Mecánico y seguro una
   vez hecho el paso 1.
3. **D2 se queda tal cual, íntegro, hasta que tenga código.** No es deuda documental: es la
   lista de trabajo pendiente del núcleo. Recortarlo ahora sería tirar lo único que sabemos
   de esos defectos.
4. **D1 se reescribe** como un procedimiento de decisión corto, que es lo que el archivo
   debía haber sido siempre.

**Resultado esperado: de 869 a unas 330-350 líneas**, sin perder una sola lección. No baja
más porque D2 —las 208 líneas de guardas que aún no son código— tiene que seguir escrita
hasta que se implemente.

## Lo que NO hay que hacer

Recortar por longitud. Los bloques largos de D2 son largos porque describen defectos que
**ningún control automático ve**: el balance cuadra, el ratio sonríe y el markdown se lee
sin sobresaltos. Son justamente los que más caro sale olvidar.
