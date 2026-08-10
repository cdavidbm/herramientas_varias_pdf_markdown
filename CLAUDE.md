# CLAUDE.md — Manual de operación de La Forja (para el agente)

Este repo es un **taller de conversión de libros a markdown por capítulo**,
pensado para que **lo opere Claude**, no la persona usuaria. El usuario pide un
resultado ("pasa este libro a markdown", "prepáralo para NotebookLM") y **tú
diagnosticas el documento y eliges la herramienta correcta tú mismo**.

> También existe la skill global **`/forja`** con este mismo algoritmo. Este
> archivo lo replica para que el repo sea autoexplicativo aunque se use en otra
> máquina o sin la skill cargada.

> **¿Qué herramientas hay? → [`tools/CATALOG.md`](tools/CATALOG.md).** Es el índice
> ÚNICO de las 67 tools, agrupadas y con su propósito, **autogenerado desde los
> docstrings** (`python3 tools/catalog.py --write`), así que no se desincroniza.
> Ante un libro difícil, consúltalo para no reinventar lo que ya existe. Este
> CLAUDE.md da la RECETA (qué usar y en qué orden); el catálogo da el INVENTARIO.

## Principio rector

1. **Sondea, no preguntes lo inferible.** Formato, escaneo vs digital, columnas,
   tablas… se detectan con comandos. Pregunta SOLO lo que no se puede inferir:
   idioma destino (al traducir) o qué front-matter descartar.
2. **Previsualiza siempre** (`--dry-run`, o Docling sobre 1 capítulo) antes del
   run completo. **Anuncia en una línea la ruta elegida y por qué.**
3. **Calidad editorial:** el destino es leer/estudiar/traducir, no solo indexar.
   Si un bisturí deja markdown sucio, escala a Docling.

## Algoritmo de diagnóstico

Define `T=tools` (o la ruta absoluta del repo).

> **El núcleo está en `forja/`, no en `tools/`.** `forja.comun` (primitivas: slugify,
> pdftext, plan.json, diccionario), `forja.aparato` (el aparato de notas de principio a
> fin), `forja.paginas` (folio, titulillo, unión de renglones) y `forja.pdfxml` (la puerta
> a `pdftohtml -xml`). Las herramientas de `tools/` son CLI encima. Cada guarda medida
> vive ahí con su test en `tests/`, así que **actúa sola**: no depende de que alguien
> recuerde haber leído este archivo. `tools/forja_common.py` sigue existiendo solo como
> reexportación, porque 21 scripts lo importan.
>
> **Dónde está cada cosa.** Este archivo tiene ya solo tres clases de contenido: el
> **procedimiento de decisión** (qué usar y en qué orden), un **índice de herramientas**
> que remite a su docstring, y las **lecciones que todavía no son código** — esas van
> completas, porque son lo único que sabemos de defectos que ningún control automático ve.
> Lo que ya vive en `forja/` con su test no se repite aquí: se nombra y punto.
> El inventario de esta limpieza está en `_INVENTARIO_CLAUDE_MD.md`.

### 1. Enrutar por formato

- `.epub` → §EPUB.  `.rtf` → `rtf_to_markdown.py x.rtf --dry-run`.
- `.docx .pptx .xlsx .html .png .jpg` → `markitdown x` (no es trabajo de los scripts).
- `.pdf` → §2.  `.djvu` → `djvu_to_markdown.py`.  `.tex` → `latex_to_markdown.py`.

### 2. Diagnóstico PDF

```bash
pdfinfo x.pdf
chars=$(pdftotext -f 1 -l 5 x.pdf - 2>/dev/null | wc -c); echo "chars/5pp=$chars"
```

- **Encrypted: yes** → `qpdf --decrypt x.pdf x_dec.pdf` → re-diagnostica.
- **chars/5pp < ~500** → escaneo sin texto → `ocrmypdf --skip-text`, o la skill `/ocr`.
  Para escaneos largos o si hay que pausar, `ocr_incremental.py` (lotes con checkpoint).
- **Capa de texto MALA** (OCR corrupto: griego perdido, cursivas rotas) pero escaneo
  nítido → re-OCR en modo `redo`, que sustituye la capa conservando la imagen.
- **Escaneo largo, o equipo que se puede cerrar** → `docling_incremental.py` (lotes con
  checkpoint y resume; `--no-ocr` si ya trae capa de texto). Y para el OCR geométrico,
  cuando el problema es de LAYOUT y no de reconocimiento, `ocr_geometry.py`.
- **Páginas apaisadas** (ancho/alto > ~1.3) → escaneo 2-up → `split_pdf_spreads.py` antes
  de nada. Si vas a TRANSCRIBIR POR VISIÓN, `split_scan_spreads.py`, que corta por el
  lomo y no por el centro.

Las trampas de cada uno —rotación horneada, capa en blanco, cuadernillo girado 90°,
verificación del corte— están en el docstring de su herramienta.

### 3. ¿Bisturí o Docling?

Mira el layout en una página de cuerpo:

```bash
pdftotext -layout -f 20 -l 20 x.pdf - | sed -n '1,40p'
pdfimages -list x.pdf | wc -l
```

**Docling** si hay multicolumna real, tablas, fórmulas, muy ilustrado o extracción rota.
**Bisturí** si es prosa limpia a una columna (§3b elige cuál). Ante la duda: un capítulo
con bisturí, mira el `.md`, y si quedó sucio repite con Docling.

> **Dos excepciones a «multicolumna → Docling»:** si las columnas son PARALELAS
> (original/traducción) o si la CURSIVA es significativa, va `pdf_rich_to_markdown.py`.
> Docling y `pdftotext` recuperan **cero** cursivas, y `pdffonts x.pdf | grep -i italic`
> lo confirma en un segundo. En un texto académico la cursiva es información, no adorno.

> **Lo que hay que pulir DESPUÉS** (medido en Partridge, *Al-Kindi's Theory of the Magical
> Arts*): el PDF corta la cursiva en cada salto de renglón (`*The Philosophical Works of
> Al-*` `*Kindi*`), así que hay que fusionarla — pero la fusión **no puede cruzar el salto
> de línea** (con `\s*`, que incluye `\n`, se encadenan las marcas de párrafos distintos y
> el frente del libro entero acaba en una cursiva) y hay que **apartar las negritas antes**
> (`**` son dos asteriscos adyacentes: la fusión los colapsa y deja los títulos como texto
> corrido). El folio suelto se convierte en `<!-- p. N -->`; las definiciones de nota salen
> CONCATENADAS en una línea por página y sin los dos puntos; y las leyendas de figura
> maquetadas AL LADO del texto se cuelan a media frase, a veces partidas en dos trozos.
>

> **Y ojo con el aparato de DOS CAPAS** (notas del traductor + notas largas del editor, como
> en Project Hindsight): si las notas del editor tienen VARIOS PÁRRAFOS, un separador que
> cierre la definición en el primer renglón en blanco deja los párrafos siguientes sueltos en
> el cuerpo, y al consolidar se acumulan al final del libro —impresos como prosa **después
> del colofón**—. Se detectan buscando líneas sangradas ANTES de la primera `[^N]:` del
> archivo. Además: **si un título de capítulo lleva llamada de nota**, y el título es el
> delimitador del troceo, esa nota se queda sin definición.

### 3b. Elegir bisturí PDF

| Situación | Script |
|---|---|
| **Cursiva significativa** o **2 columnas paralelas** | `pdf_rich_to_markdown.py` |
| **Acrobat ClearScan** (`pdfinfo` dice «Paper Capture … ClearScan») | `clearscan_to_markdown.py` |
| **Capa de texto INCOMPLETA**: se pierden llamadas, puntos suscritos o dígitos | `pdfxml_to_markdown.py` |
| Carpeta de **un PDF por capítulo**, notas a pie | `pdf_chapters_to_markdown.py` |
| **PDF digital limpio** con outline (Calibre) | `detect_chapters.py` → `pdf_sections_to_markdown.py` |
| Escaneado **ya OCR-eado** con citas Harvard | `pdf_book_to_markdown.py` |
| `pdftotext` no extrae nada pero hay sidecar `.txt` | `ocr_text_to_markdown.py` |
| Solo **partir** el PDF en capítulos | `detect_chapters.py` → `split_pdf.py` |

Cada uno documenta en su docstring la patología que ataca y sus trampas medidas.

**Sondas de tipografía** (no convierten; te dicen qué hay antes de elegir):
`pdf_headings.py x.pdf` lista los tamaños de fuente y qué líneas serían encabezado;
`pdf_blocks.py x.pdf` vuelca los bloques con su fuente, tamaño y posición. Úsalas cuando
dudes de si un título es título o de dónde cae el corte de columna.

Lo que sigue son las lecciones que **no** pertenecen a un solo bisturí.

> **LA APERTURA DE CAPÍTULO NO LLEVA TITULILLO: esa es la señal.** Al fijar los límites
> de troceo es fácil tomar por arranque una página INTERIOR cuyo titulillo diga
> «152 CHAPTER FOUR» —el número es el de esa página, no el del comienzo—. La apertura
> real trae el rótulo SOLO, sin cifra. Buscando `^(CHAPTER \w+|APPENDIX \w+|BIBLIOGRAPHY)$`
> como primera línea salen todos los límites de una vez y verificados. Medido en Lehrich:
> el cap. 4 empieza en la p. 161, no en la 166, y el error se delató por las

> **definiciones 1-6 DUPLICADAS** en el capítulo anterior (el segundo juego era del
> capítulo siguiente). Un aparato con la secuencia ROTA es la señal de que el límite
> está mal, mucho antes que cualquier ratio.

> **CIFRAS DEL CUERPO TOMADAS POR LLAMADAS DE NOTA.** `--footnotes` separa el pie por
> CUERPO DE LETRA, así que cualquier cifra compuesta en otro tamaño se convierte en un
> `[^N]` falso: las de un **cuadrado mágico**, las páginas de una **referencia
> bibliográfica** («*Opera*, 2:1089-1101»). Medido en Lehrich: el cap. 3 —el de los
> cuadrados mágicos— tiene 89 notas y salían llamadas hasta la **947**, y la bibliografía
> daba 73 llamadas con CERO definiciones. **La regla que lo ataja es la CADENA
> ASCENDENTE**: las llamadas van en orden y **nunca retroceden**, así que un número que
> va hacia atrás —o que no tiene definición— es una cifra del cuerpo y se devuelve a
> texto plano (era contenido; no se borra). **Pero la cadena sí puede SALTAR**: exigir
> que avance de uno en uno rompe el capítulo entero al primer hueco —medido en Lehrich,
> la nota 25 no tiene llamada en el original y esa regla estricta invalidó 120 llamadas
> buenas en cascada—. Y en las secciones que NO tienen notas —bibliografía, apéndices—
> sencillamente no uses `--footnotes`.

> **Y el ORDEN de la receta importa:** bisturí → promover el título de capítulo →
> `pdf_blocks` → quitar titulillos. Si se quitan los titulillos antes, el emparejamiento
> contra el PDF falla; si no se promueve el título antes, el epígrafe se detecta como
> cita y **se traga el encabezado del capítulo**.

> **Cómo se resuelve:** `pdftohtml -xml` da posición + familia + tamaño por palabra en
> 0,4 s (pdfminer tarda MINUTOS por página con fuentes Type 3). La familia dice qué lleva
> punto suscrito; el volado se reconoce por la **LÍNEA BASE ALZADA** —no por el tamaño,
> porque los dígitos elzevirianos también son bajos (260 glifos pequeños frente a 77
> volados reales)— y se CUENTA, como en un escaneo. Los glifos PUA de los dígitos se
> deducen comparando UNA tabla con su imagen y se pasan con `--charmap "U+F63A=2,…"`;
> entonces la llamada además se puede LEER, lo que da un **cotejo de dos señales
> independientes** (contada vs. impresa) que destapa cualquier desfase.

> **Límite honesto:** las tablas SIMPLES salen bien (`--tables`), las de encabezado
> apilado quedan aproximadas; y cada fuente de versalitas tiene SU propio mapeo corrupto,
> así que un `--charmap` global de una sola letra puede estropear otra fuente: mapea
> cadenas enteras (`Å±ÆÁÂ=TABLE`) y verifica contra la imagen.
>

> **PDF HECHO CON CALIBRE DESDE UN EPUB: la llamada de nota se LEE, no se cuenta.** Es el
> mismo bisturí, pero la señal es otra y confundirlas sale caro. Aquí el volado no es un
> glifo mudo: es el número ENTERO y legible dentro de un `<a href>` que apunta al aparato
> del final, en cuerpo menor y en azul (`size 17` sobre 23, `#0000ee`). `pdftotext` lo tira
> igual —el aparato entero desaparece sin que nada avise—, pero **contar es peor que leer**:
> si el original deja algún número sin anclar, el conteo se desfasa desde ese hueco y todas
> las etiquetas siguientes apuntan a OTRA nota. Medido en *Physicians of the Heart* (530 pp):
> 310 llamadas legibles sobre la serie 1..311, con la **32** ausente del cuerpo. El
> discriminante para no tomar un exponente por llamada es el ENLACE, no solo el tamaño.

> **Cuatro artefactos más de esta maqueta, todos invisibles en el markdown:** la CAPITULAR
> queda suelta (`*B*` y luego «ecause…», a veces en bloque aparte y a veces en la misma
> línea); la CURSIVA sale partida en dos tramos (`*siraat-ul* *mustaqeem*`) y al fusionarla
> no va espacio si el corte cayó en un guion (`*Al-* *hamdu*` = «Al-hamdu»); el ENCABEZADO
> viene íntegro en cursiva; y el punto suscrito se emite como glifo aparte, con lo que el
> hueco entre cajas mete un espacio ANTES de la marca combinante (`rah ̣-MAAN` por
> `raḥ-MAAN`, 191 casos) — y un espacio nunca precede legítimamente a una combinante.

### 3c. Limpieza post-conversión

**Empieza por las dos puertas únicas, no por los fixers sueltos:**

- `forja_limpiar.py ./markdown [--apply]` — orquestador: aplica en orden el núcleo
  determinista y termina con el informe de artefactos. Toggles según el libro
  (`--verses`, `--notas`, `--openings`, `--docling`, `--spell`). Dry-run por defecto.
- `fix_ocr.py <sub> FILE... [--apply]` — correcciones OCR puntuales bajo un comando:
  `ordinals·romans·ligatures·diacritics·spell·all`.

**Índice de arregladores** (el porqué y las guardas, en su docstring):

| herramienta | para qué |
|---|---|
| `clean_markdown.py` | titulillos de página, guion suave, imágenes base64, espacios |
| `fix_markup.py` | artefactos de maqueta: negrita partida, `****`, `§` en negrita |
| `reflow_columns.py` | prosa cortada en fragmentos por una maqueta a dos columnas |
| `cose_parrafos.py` | párrafo partido a media frase por el salto de página |
| `citas_en_bloque.py` | la cita entera que salió como prosa entrecomillada |
| `verse_paragraphs.py` | texto versificado que quedó como un párrafo gigante |
| `split_chapters.py` | trocear en capítulos (`--plan` o `--by-heading`) |
| `chapter_bounds.py` | límites reales cuando no te puedes fiar de los encabezados |
| `index_rebuild.py` | rehacer el índice analítico contra el PDF nuevo |
| `embed_figures_from_captions.py` | recortar del PDF las figuras que solo dejaron leyenda |
| `hebreo_sp_a_unicode.py` | hebreo compuesto con una fuente ASCII |
| `glifos_janus_a_unicode.py` | glifos astrológicos de una fuente Janus con `ToUnicode` roto |
| `astro_glyphs.py` | glifos astrológicos corruptos (marca, no corrige) |
| `flag_ocr_artifacts.py` | DETECTOR de ruido camuflado, para corregir a mano |
| `ocr_spellfix.py` | erratas de OCR usando el propio libro como modelo |
| `normaliza_autores.py` | atribuciones de autoría destrozadas en compendios |
| `limpia_dudas.py` | las marcas `[?: …]` del traductor, clasificadas |
| `rescata_capitulos.py` | capítulos que viven dentro del aparato de notas |
| `quita_titulillos_fundidos.py` | titulillos que el OCR pegó a la primera línea |
| `pdf_restore_digits.py` | dígitos que el bisturí perdió (mídelo contra el PDF) |
| `fix_ligatures.py` · `fix_diacritics.py` | corrupción OUP/Distiller (fi→W, acentos rotos) |
| `fix_ordinals.py` · `fix_roman_numerals.py` | ordinales volados y numerales romanos del OCR |
| `clean_openings.py` | portadillas y capitulares (estilo OUP) |
| `docling_clean.py` | limpieza específica de la salida de Docling |
| `crop_figure.py` · `check_scan_margins.py` | recortar una región del PDF · verificar el corte de un 2-up |

**El aparato de notas es un módulo, no un puñado de scripts:** `forja.aparato` separa,
ancla (con varias estrategias), reparte y audita, y sus guardas tienen test en
`tests/test_aparato.py`. Las CLI son `footnote_chain.py`, `footnotes_rebuild.py`,
`footnotes_from_pdf.py`, `footnotes_redistribute.py`, `coteja_aparato.py` y
`aparato_volados_aplanados.py`.

---

**Lo que sigue son lecciones que TODAVÍA NO SON CÓDIGO.** Van completas a propósito: son
defectos que el balance de notas, el ratio de palabras y la lectura del markdown NO ven.
Cada una es trabajo pendiente del núcleo, no relleno.

- **SUBTÍTULOS DE SECCIÓN PEGADOS AL PÁRRAFO.** Si el libro marca sus apartados con una
  línea en CURSIVA (no con cuerpo mayor), el bisturí no los ve como encabezado y quedan
  fundidos al párrafo que abren: `*Planetary Characters* The construction of…`. En el
  markdown pasa desapercibido, y al maquetar el libro entero se queda **sin estructura
  interna** y el índice solo lista capítulos. Medido en Lehrich: **86 por idioma**.
  Se promueven a `##`, pero **verifícalo contra el PDF antes**: un subtítulo real aparece
  como LÍNEA SUELTA en `pdftotext` (86/86 confirmados, 0 falsos positivos), mientras que
  un párrafo que empieza por un título de obra en cursiva NO. Dos avisos: el patrón se
  escapa cuando el párrafo arranca con OTRA cursiva (`*Character and Hieroglyph* *DOP*
  does not…`), y una regla de «bloque entero en cursiva» **promueve las LEYENDAS DE
  FIGURA a encabezado** —5 por idioma— si no las excluyes.

- **LAS LLAMADAS DE NOTA SE COMEN CIFRAS** cuando el escaneo tiene el margen recortado.
  Es el defecto MÁS CARO de detectar de todos los de esta sección, porque **el balance de
  notas cuadra perfectamente** y aun así el texto ha perdido un dato. Pasa cuando el
  colocador de llamadas busca «el siguiente número N» por el cuerpo: si el volado real
  está fuera de la imagen, ancla sobre la PRIMERA cifra que encuentra —un grado, un punto
  de dignidad, un número de capítulo—. Medido en *The Search of the Heart* (50 casos):
  `7.5°`→`7.[^95]°`, `Decano 1`→`Decano [^19]`, `*Skilled* I.5.2`→`*Skilled* I.[^50].2`,
  `2 1/2`→`[^3]/2`, `Libros I-V`→`Libros [^1]-V`.
  **Cómo detectarlo:** busca `[^N]` en HUECO NUMÉRICO — pegado a `°`/`′`, dentro de una
  numeración con puntos (`I.[^50].2`), o entre dos cifras de una serie.
  **Cómo repararlo:** casi siempre por LÓGICA, sin abrir el PDF —una serie descendente
  5-4-3-2-1, unos doceavos que van de 2,5° en 2,5°, la numeración de capítulos del propio
  libro— y solo el resto contra la imagen. Al restaurar la cifra la llamada DESAPARECE
  (estaba mal puesta): esa definición pasa a «sin anclar», que es lo honesto.
  **El mismo patrón vale en el ORIGINAL y en la TRADUCCIÓN**: el contexto numérico
  sobrevive intacto, así que el reparador se aplica igual a `en/` y a `es/`.

- **ESCANEO GRANDE: EXTRAE LA IMAGEN, NO RASTERICES.** Si el PDF es un escaneo con UNA
  imagen embebida por página (compruébalo: `pdfimages -list x.pdf | tail -n+3 | awk
  '{c[$1]++} END{for(p in c) if(c[p]!=1) print p}'`), `pdftoppm -r 300` es un despilfarro:
  tiene que buscar dentro del archivo y rasterizar. Medido en un PDF de 736 pp / 243 MB:
  **3,94 s/página con `pdftoppm` frente a 0,19 s con `pdfimages`**. Con eso, más llamar a
  tesseract UNA vez para los dos formatos (`-c tessedit_create_txt=1 -c
  tessedit_create_tsv=1`; llamarlo dos veces duplica el coste) y **`OMP_THREAD_LIMIT=1`**
  (varios tesseract en paralelo se estorban: 60 s/pág sin el límite, 1,4 con él), el libro
  pasó de **8 horas a 23 minutos**, con salida idéntica carácter por carácter.
  **REESCALA a 300 ppi** las páginas que vengan por debajo o el OCR se degrada
  (`Illness`→`[lness`).
  **OJO con `TESSDATA_PREFIX`:** si lo apuntas a una carpeta de modelos alternativa (los
  `best`), tesseract ya NO encuentra los ficheros de configuración `txt`/`tsv`, que viven
  ahí dentro, y **genera solo el texto EN SILENCIO** — 736 `.txt` y 0 `.tsv`, y la
  conversión sale vacía. Por eso hay que usar los `-c tessedit_create_*`, que no dependen
  de dónde estén los modelos.

- **CURSIVAS DE UN ESCANEO PURO: mide la INCLINACIÓN DEL TRAZO.** Cuando no hay capa de
  texto, el truco de ClearScan (medir las fuentes embebidas) no aplica, y tesseract no
  marca la cursiva: su hOCR solo emite `x_fsize`. La señal está en los píxeles: se cizalla
  el recorte de cada palabra en un abanico de ángulos y se elige el que hace más PICUDO el
  histograma de la proyección vertical (los trazos verticales se alinean). Imprescindible
  **recortar a la banda de ALTURA-X antes de medir**: si no, la `y`, la `g` y la `p` fingen
  una inclinación que no está en el trazo. Medido: **8 de 8 aciertos y 0,2 % de falsos**;
  en el cuerpo la separación es de 16° (cursiva −16°, redonda 0°) pero **en el pie baja a
  3°**, así que ahí se sub-detecta: es un límite, no un fallo. Y la imagen medida tiene que
  ser EXACTAMENTE la que vio tesseract, o las coordenadas del TSV no encajan y la cursiva
  sale desplazada una palabra. Vectoriza el barrido con numpy (bincount por ángulo): de 6 a
  2,3 s/página.

- **FIGURAS DENTRO DEL ESCANEO DE PÁGINA** (no como objetos aparte): se recortan por
  región. La leyenda («Figure 12: …») da el borde inferior; el superior se busca hacia
  arriba hasta la primera racha en blanco MÁS LARGA QUE EL INTERLINEADO de esa página
  —calculado de la propia página, que varía—. **Dos trampas:** (1) un umbral fijo de ~28
  filas coincide con el hueco normal entre renglones y devuelve recortes de 30-50 px;
  (2) entre la figura y su leyenda YA hay un hueco grande, así que hay que **saltar el
  blanco inicial** y llegar a la tinta antes de buscar el hueco de arriba (una carta pasó
  de 99 a 1.585 px al corregirlo). Al incrustar, NO ancles la leyenda en `^`: al recomponer
  párrafos muchas quedan dentro del texto (medido: 35 de 70 colocadas frente a 61).

- **APARATO DE NOTAS DE UN ESCANEO: el número NO se lee, se CUENTA.** Los volados van
  diminutos y tesseract no los reconoce: los pega a la palabra anterior como basura
  (`money,!!`, `it.'3`, `of]'©`) y ninguna combinación de `--psm` lo arregla. Pero la
  POSICIÓN sí es medible: el marcador de nota tiene la **línea base ALZADA** respecto a la
  de su renglón. Así que se cuentan marcadores y se deduce el número, usando el dígito que
  sobreviva solo para COMPROBAR.
  **ANTES DE NADA, AVERIGUA DÓNDE REINICIA LA NUMERACIÓN.** Es la suposición que lo decide
  todo. En *The Book of the Nine Judges* no reinicia por sección `§N` sino por **SUBGRUPO
  TEMÁTICO**, y el **titulillo de recto** los anuncia (MARRIAGE & RELATIONSHIPS, THEFT,
  WAR…): con esa corrección la cadena da 191/191 y 157/157 contra el impreso; sin ella,
  1018 donde el libro va por 195. Verifícalo leyendo los números del pie en varias páginas
  ANTES de construir nada.
  **Reglas que hacen falta, todas medidas:** (a) un dígito suelto que discrepa se descarta,
  pero DOS seguidos con el mismo desfase mandan; (b) la cadena **nunca retrocede por debajo
  de donde empezó la página**, o dos cifras del texto de una nota la hunden; (c) el
  titulillo de VERSO lleva el título del libro y alterna con el de recto — descártalo
  mirando la línea ENTERA, porque extrayendo primero te queda una cola que ya no se parece
  al título (184 reinicios falsos donde hay 9); (d) el OCR TRUNCA los titulillos, así que
  al comparar subgrupos acepta que uno esté contenido en el otro.
  **Para las LLAMADAS del cuerpo:** geometría (cola con tinta solo en la banda alzada) MÁS
  firma de basura. Cada señal por su cuenta da decenas de falsos por página; juntas,
  ninguno. Y **ancla solo cuando dos señales independientes coincidan** (posición y cifra
  superviviente): sale ~25 % de cobertura, pero un anclaje falso mueve la nota a otra frase
  y al leer NO se nota. Ojo: si marcas las cursivas con `*`, EXCLUYE el asterisco del
  repertorio de basura o el titulillo en cursiva se cuela como llamada y corre la página +1.
  **Si los números se repiten dentro del archivo** (varios subgrupos con su nota 1), usa
  etiquetas `[^grupo-numero]`: `md_to_pdf` renumera al maquetar.
  **Y AUDITA LA COMPLETITUD DESPUÉS DE CADA CAMBIO.** Reconstruir el aparato produce
  pérdidas de texto silenciosas: indexar definiciones por número las sobrescribe cuando la
  numeración se repite, y una página sin marcador detectable pierde su pie ENTERO si el
  código hace `zip` con una lista vacía. Tres pérdidas distintas (20 %, 8/9 y 16 %) en un
  solo libro, ninguna con error y ninguna visible en el markdown.

- **EL APARATO CRÍTICO LATINO NUMERA LAS LÍNEAS: eso es un control de completitud GRATIS
  y exacto.** En una edición crítica bilingüe, la columna del original suele llevar el número
  de línea cada cinco renglones. Si el archivo convertido empieza con el marcador «30» en vez
  de «5», faltan 29 líneas y no hay que discutirlo. Medido en Ficino: el rango de páginas del
  *Apologia* arrancaba dos páginas tarde y se había perdido la apertura entera —encabezamiento,
  salutación a los tres Pedros y el párrafo con los tres reproches, 449 palabras y tres notas—.
  **Ningún control de los de §3d lo habría visto**: no hay con qué comparar el ratio porque el
  archivo entero está desplazado, el balance de notas cuadra (las llamadas perdidas se fueron
  con su texto) y el markdown se lee sin sobresaltos, solo que empieza por «Responde primero…».
  Comprueba SIEMPRE que el primer marcador de línea del original sea el primero de la sección.

- **UN ENCABEZADO EN EL SITIO EQUIVOCADO ESCONDE UNA LAGUNA DE TRADUCCIÓN, y el ratio
  GLOBAL no la ve.** Si el título va centrado en dos renglones y el bisturí promueve solo el
  SEGUNDO, la primera mitad queda de párrafo suelto al final del capítulo anterior —y el
  encabezado puede acabar **mil palabras más abajo de donde empieza el capítulo**. Entonces
  el traductor cierra el capítulo donde dice el encabezado y **el tramo intermedio no se
  traduce nunca**. Medido en Ficino, *De vita* III: cinco títulos partidos (caps. 3, 12, 15,
  22 y 25) y el del 12 desplazado, con **1.484 palabras perdidas** —el capítulo entero sobre
  el bezoar, la peonía y la triaca—. Ratio global 0,98; **ratio de ESE capítulo 0,62**.
  **Por eso el control de completitud de una traducción se mide POR CAPÍTULO, no por
  archivo**; y un título que empieza en MINÚSCULA es la señal barata de que está partido.

- **UNA NOTA QUE FALTA CON SU LLAMADA NO ROMPE NINGÚN BALANCE: cuéntalas contra la FUENTE.**
  El control anterior compara llamadas con definiciones DENTRO del markdown, así que no ve
  las notas que se perdieron ENTERAS —definición y volado a la vez— cuando el partidor por
  cadena falló: el aparato queda internamente coherente y el ratio de palabras del cuerpo ni
  se entera, porque lo perdido es el pie, no la prosa. Medido en Ficino, Libro I: el markdown
  tenía **53 notas donde el impreso lleva 90**, y las 37 ausentes —1.700 palabras de
  comentario— habían pasado la auditoría entera, la traducción y el PDF. **Lo que sí lo ve
  es contar por sección contra el texto crudo del comentario**: si la sección 1.23 numera
  hasta la 6 y el markdown tiene una, faltan cinco. La numeración SUPERVIVIENTE lo delata
  gratis: un capítulo cuyas notas van `1, 2, 3, 8` tiene un agujero, no una numeración rara.
  **Para reanclarlas no hace falta adivinar:** el volado perdido casi siempre sigue en el
  cuerpo como basura de OCR pegada a la palabra (`Politics*`, `also,.5`, `Quintilian6`,
  `scholars7`, `clear.'`, `it..3`, `i)14`), y cada residuo cae exactamente donde iba la
  llamada. **La señal barata de que hay que mirar** es una definición TRUNCADA que acaba en
  «…p.» o «…n.»: el partidor cortó en el número de una referencia de página (`p. 10.`) y
  ese mismo fallo se llevó por delante las notas siguientes. Ojo también con la fusión en
  sentido contrario: la última nota de una sección puede haberse tragado la primera de la
  siguiente (aquí `1.6-7` contenía entera la `1.7-1`).

- **ENCABEZADOS PARTIDOS EN DOS RENGLONES**: si un título va centrado en dos líneas, el
  bisturí promueve solo la primera y deja la segunda como párrafo suelto que empieza en
  minúscula. Se cose al título (sin coma si es continuación genitiva, «…del significador»
  + «del consultante»; con coma si es cláusula nueva). Si la continuación YA está en el
  encabezado porque se recompuso antes contra el índice impreso, se BORRA el huérfano en
  vez de duplicarlo.

- **El ÍNDICE IMPRESO es el mejor contraste para los encabezados destrozados** (no solo
  para renumerar): conserva los títulos reales, así que con él se hace una lista curada
  de correcciones y, sobre todo, se descubre **qué capítulos FALTAN** en el markdown
  porque su título se quedó tragado dentro del cuerpo (10 de ellos en *Search*).

- **VERIFICA los límites de sección/Libro contra el PDF antes de dar el troceo por
  bueno.** Los números de página de un `plan.json` armado a ojo pueden estar MUY mal
  (medido: 25-32 páginas de desfase en los Libros I-IV de Persian Nativities IV, con
  el «Libro I» arrastrando el arranque del II). Localiza cada límite por un marcador
  robusto en el texto OCR: el preámbulo de apertura del Libro (p. ej. «…is in N
  chapters») y el primer capítulo real («Chapter N.1») en página >front-matter. Un
  archivo que contiene capítulos de OTRO Libro (numeración que salta) es la señal.

- **Límite honesto del escaneo MUY degradado:** cuando el OCR pierde los
  **delimitadores estructurales** (superíndices de nota, saltos de línea, tamaños de
  fuente), encabezados + notas + cuerpo quedan fundidos SIN frontera fiable. Un reflow
  posterior (unir fragmentos, párrafos por verso, quitar basura MAYÚS, promover
  «Chapter N.M:») mejora mucho la lectura, pero **la separación de notas y de parte de
  los encabezados NO es automatizable**: eso pide corrección manual contra la imagen.
  No lo vendas como perfecto.

> **convertir → RECONSTRUIR NOTAS → traducir → PDF**. Si traduces antes, hay que rehacer
> el aparato en los dos idiomas a la vez. Comprueba SIEMPRE `grep -c "\[\^" markdown/*.md`
> antes de lanzar traducciones: sin `[^N]`, las citas se imprimen como párrafos sueltos
> en mitad del texto.

### 3d. VERIFICACIÓN de completitud (obligatorio antes de traducir o publicar)

Los bisturíes pueden **perder texto sin avisar** según el layout, y es invisible salvo que
se mida. No des una conversión por buena hasta verificar:

- `check_completeness.py cap.pdf cap.md` — alinea contra `pdftotext -layout` y lista o
  repara lo perdido. También como bandera: `pdf_chapters_to_markdown.py plan.json --verify`.
- `audit_conversion.py spec.json --out INFORME.md` — auditoría de un LIBRO entero en 4
  capas, separando lo demostrable de lo estimable.
- `auditar_biblioteca.py` — pasa por TODOS los libros ya convertidos y dice cuáles tienen
  defectos detectables sin abrir el original. Responde a «¿cuántos más estarán mal?»,
  que es una pregunta que ninguna auditoría por libro contesta.
- `limpiar_academico.py ./markdown` — corrupción OUP/Distiller (ligaduras y diacríticos que
  parecen erratas pero son texto roto).
- Skills: **`/qa-conversion`** antes de traducir, **`/qa-traduccion`** después.

**Leer el ratio es criterio humano, y estas tres lecturas hay que saberlas:**

- **El ratio global md/PDF ENGAÑA si el libro tiene figuras.** En libros con cartas o
  diagramas, `pdftotext` extrae las etiquetas del gráfico como basura (`02' 05 21* Q 48'`)
  que Docling —con razón— descarta al recortar la figura. Eso baja el ratio sin que falte
  prosa (p. ej. 0.961 global). **Mide en un tramo SIN figuras** (glosario, un capítulo de
  prosa densa): si ahí sale ~0.98-0.99, no hay pérdida. Un ratio bajo en un tramo de prosa
  pura sí es alarma real.

- **El ratio se DERRUMBA (0.6-0.8) en libros BILINGÜES con notas en otro alfabeto**
  (p. ej. ediciones de Dykes con el árabe original al pie): tesseract con modelo
  inglés convierte ese árabe en torrentes de basura que `pdftotext` sí extrae pero el
  conversor descarta → el **denominador** se dobla sin faltar prosa (medido: ~25 % de
  los tokens del PDF eran basura en Persian Nativities IV, con la prosa íntegra).
  NO te fíes del ratio de cuerpo aquí; ni siquiera la «cobertura de tipos» sirve (la
  hunden la flexión y los cortes de palabra del OCR). Lo que PRUEBA la completitud es:
  (1) el **control de prosa** —una sección moderna sin notas ajenas, típ. la
  introducción del traductor, que debe dar ~0.97; (2) el **muestreo visual** de 4-5
  páginas de cuerpo de capítulos distintos leídas contra la imagen. Las **tablas y
  cartas** OCR-eadas se CONSERVAN (son contenido real, no se borran), pero son
  aproximadas: la imagen/PDF buscable es la fuente autoritativa de sus cifras.

- **PDF buscable de tesseract enorme (GB):** la salida cruda embebe las imágenes a
  300 dpi RGB sin comprimir (2 GB para ~700 pp). Recomprime antes de entregar:
  `gs -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook -dColorImageResolution=150
  -dGrayImageResolution=150 -dNOPAUSE -dBATCH x.pdf` → ~65 MB, conserva la capa de
  texto (verifícalo con `pdftotext` en 1 página). Córrelo bajo `systemd-run --user
  -p MemoryMax=4G` (el input de 2 GB es pesado).

### EPUB

```bash
python3 $T/build_plan.py "libro.epub" > plan.json   # spine + TOC
python3 $T/epub_to_markdown.py plan.json --dry-run && python3 $T/epub_to_markdown.py plan.json
```

- **Pool de notas al final → `footnotes_redistribute.py libro.md --apply` ANTES de
  trocear.** Si no, al partir por capítulos las definiciones se van enteras al último
  archivo y los demás quedan con llamadas huérfanas, que pandoc descarta en silencio.
- Muy ilustrado → `epub_illustrated_to_markdown.py`.
- La cursiva de los EPUB de Calibre va en una CLASE CSS y no en `<i>`: está resuelto en
  `epub_to_markdown.py` y explicado en su docstring.

**Lecciones de maquetas concretas que aún no son código:**

> **Dos trampas:** las marcas van FUERA del espacio (`*De Imaginibus *ahora` no lo
> renderiza pandoc), y un selector DESCENDIENTE (`.a .b`) no debe aportar clases o
> sobre-aplica.
>

> **Pool de notas PLANO (todas dentro de UN `<p>`, separadas por `<br/>`):**
> `footnote_format: "by_a_id_split"`. Los parsers por párrafo no ven ninguna nota
> aquí, porque no hay un elemento por nota: **la frontera es el ancla vacía**
> `<a id="filepos…"></a>`, así que se parte el HTML crudo por ella. El `[return]`
> del final se quita con sus corchetes. (Los otros dos formatos —`by_a_id_any` para
> un `<p>` por nota, `by_p_id`— siguen igual.)
>

> **Otros tres defectos medidos en el mismo libro, todos invisibles en el markdown:**
> (1) el título del capítulo sale DOS veces, porque el libro lo maqueta como `<p>` en
> negrita y la deduplicación solo miraba `<h1>`-`<h6>` → ahora se suprime todo párrafo
> cuyo texto ÍNTEGRO sea el título de la sección; (2) un **salto de línea del FUENTE**
> dentro del párrafo es un espacio en HTML, pero conservarlo tal cual deja la llamada de
> nota **sola en su renglón**, y pandoc la convierte en párrafo aparte (una llamada
> `[^N]` NUNCA abre párrafo: si lo hace, es este defecto); (3) las **imágenes se
> descartaban en silencio** — en un libro de talismanes son las cartas astrológicas, es
> decir contenido, y el texto las cita («the chart shown above»). Usa
> `--images imagenes --image-skip calibre_cover.jpg`: copia solo las que el markdown
> referencia de verdad.
>

> **Subtítulos maquetados como `<p>` en negrita** (aquí «Version I:», «Version J:»,
> «Agrippa Bk II», «Commentary on Chapter N»): promuévelos con la clave de plan
> `"heading_paragraphs": {"clase": 2}` — el conocimiento del libro va en el PLAN, no en
> el conversor. Ojo: dos `<span>` en negrita adyacentes dejan un `**` EN MEDIO del
> título, así que hay que quitar todas las negritas del encabezado (las cursivas no:
> en un título son significativas).
>

> **EPUB DE EDITORIAL (InDesign/Inner Traditions), cuatro trampas más.** Medido en
> *Three Books of Occult Philosophy* (Agripa, trad. Eric Purdue): 214 capítulos,
> 3.026 notas, 194 imágenes.
> (1) El pool se llama **`_ftn.xhtml`** y `build_plan` no reconocía esa abreviatura:
> daba «no footnote pool detected» y se habrían perdido las 3.026 notas enteras. Ya
> está en `FOOTNOTE_NAME`; ante un «no pool detected», **mira tú los nombres de
> archivo antes de creértelo**.
> (2) El `<sup>` de la llamada lleva **DOS `<a>`**: primero el ancla VACÍA de destino
> (`<a id="nr36"></a>`) y luego el enlace al pool. Quedarse con el primero deja la
> nota sin resolver y el genérico de `<sup>` escupe un **circunflejo suelto** delante
> del marcador (`superior,^[^1]`) — 3.026 veces.
> (3) En `by_p_id` la definición **ABRE con su número enlazado**
> (`<a href="…#nr36"><b>1</b></a>.`), que quedaba como `**1**.` al principio de cada nota.
> (4) El **título del capítulo viene PARTIDO en dos párrafos** (`chn` = «Chapter 1»,
> `cht` = el título) y el plan los une en el H1, así que cada trozo se imprimía otra
> vez debajo del encabezado.

> **Y la guarda que faltaba desde siempre:** la deduplicación por título EXACTO no
> miraba la POSICIÓN, así que un párrafo del cuerpo que coincidiera con el título se
> borraba en silencio a mitad de capítulo. Eso es pérdida de texto, no deduplicación.
>

> **Verificar la conversión de un EPUB es fácil y hay que hacerlo:** el texto fuente se
> saca con BeautifulSoup y se compara token a token con el markdown. El déficit debe
> quedar EXPLICADO, no solo ser pequeño: en *Astral High Magic*, 195 tokens = 68
> «return» (los enlaces de vuelta) + 14×9 del `<title>` repetido en cada documento + 1
> «Footnotes». Ratio 0.9921 y **cero prosa perdida**.

## Esquema de `plan.json`
```json
{
  "source": "libro.pdf",
  "output_dir": "markdown",
  "sections": [
    { "slug": "01_Prefacio", "title": "Prefacio", "pages": [9, 10] },
    { "slug": "02_Intro",    "title": "Introducción", "pages": [11, null] },
    { "slug": "03_Cap2",     "title": "Capítulo 2", "pdf": "2 Chapter 2.pdf" }
  ]
}
```
`pages: [ini, fin]` 1-based, `null` = hasta el final. `pdf:` en vez de `pages:` =
un PDF entero como sección.

> **Nota de compatibilidad:** algunos scripts (`split_pdf.py`,
> `pdf_sections_to_markdown.py`) nacieron con la forma escalar
> `{"title": …, "start": 11, "end": 20}`. **Ambos aceptan ya también
> `pages: [ini, fin]`** (con `fin: null` = hasta el final), así que puedes usar
> SIEMPRE la forma `pages` de arriba con cualquier conversor. La forma escalar
> `start`/`end` sigue funcionando en esos dos por retrocompatibilidad.

## Salida / siguiente paso
- **Explorar/buscar un libro ya convertido** (antes de traducir o para orientarte):
  `book_map.py ./markdown` da el **mapa estructural** (capítulos, tamaños, encabezados)
  y `book_index.py ./markdown` monta un **índice full-text LOCAL** para buscar términos
  sin releer todo. Útiles para diagnosticar troceos raros o localizar un pasaje.
- Markdown → NotebookLM (fuente) o traducción con la skill **`/traducir-md`**
  (preserva `[^N]`, encabezados, glosario).
- **Libro completo a PDF bonito → `md_to_pdf.py`, NO `pandoc`.** Es la herramienta
  con la que se maquetaron Valens, Doroteo y Hephaistio:
  ```bash
  python3 $T/md_to_pdf.py libro.pdf ./markdown-es/*.md \
      --title "Título" --author "Trad. ..." --toc --footnotes chapter
  ```
  Da `memoir` + **starfont** (glifos astrológicos ☉♄♃ de verdad), portada, índice y
  `--footnotes page|chapter|book` para elegir la numeración de notas. `pandoc` no da
  nada de eso. Requiere **lualatex + memoir + starfont** (`setup.sh` NO lo comprueba;
  si falta, instala TeX Live). **Compila bajo `systemd-run --user -p MemoryMax=4G`**:
  un bucle de lualatex puede congelar el equipo.
  - **CARACTERES PERDIDOS: MÍDELOS, no leas el log.** Más fiable que buscar «Missing
    character»: extrae el texto del PDF y compara el conjunto de caracteres **no ASCII** del
    markdown con el del PDF; lo que esté en el md y no en el PDF se perdió EN SILENCIO.
    Medido: **Latin Modern no tiene** varios signos de transliteración corrientes en este
    fondo —`ḳ` U+1E33, `ẖ` U+1E96, `ʻ` U+02BB, `ʼ` U+02BC— ni el árabe. Se arreglan con
    `--font-fallback "Charis SIL"` (fuente SIL, hecha para transliteración: cubre los cuatro)
    y `--arabic-font "Noto Naskh Arabic"`.
  - **EL HEBREO SE PIERDE EN SILENCIO sin `--hebrew-font`.** Latin Modern no lo tiene y
    el log no avisa, igual que con el árabe. `--hebrew-font "Noto Serif Hebrew"` declara
    el locale de babel (`import=he` + `Script=Hebrew`); el `bidi=basic` del preámbulo ya
    reordena de derecha a izquierda. Imprescindible en el fondo cabalístico: los nombres
    divinos y las Escalas de Agripa salen como huecos. Convive con `--arabic-font`.
  - **UN JPEG CON DENSIDAD 1 dpi DESAPARECE DEL PDF EN SILENCIO.** Si el JFIF declara
    `density 1x1` (o unidades = 0), una imagen de 653 px de ancho mide 653 **PULGADAS**:
    eso desborda la aritmética de dimensiones de TeX (`arithmetic number too big` en el
    log de lualatex), `adjustbox` no puede calcular la escala y **la imagen se descarta
    dejando su leyenda impresa**. El PDF se genera sin error, el recuento de figuras del
    markdown cuadra y el resumen del script no dice nada. **Solo se ve contando las
    imágenes del PDF (`pdfimages -list x.pdf | tail -n+3 | wc -l`) o mirando la página.**
    Medido en *Astral High Magic*: 3 de 4 cartas astrológicas se perdieron así, y el
    origen era el propio EPUB. `md_to_pdf.py` **ya lo corrige solo** antes de compilar
    (parchea 5 bytes del APP0, sin recomprimir); `--no-fix-density` solo avisa.
    Comprobación rápida a mano: `file -b img.jpg | grep -o "density [0-9]*x[0-9]*"`.
  - **`--font-fallback` ES REPETIBLE, y un libro suele necesitar DOS.** Latin Modern no
    tiene ni el griego ni los signos de transliteración; con una sola fuente de reserva
    se arregla la mitad y **la otra mitad desaparece en silencio** (medido en Lehrich:
    con `Charis SIL` sola se perdieron `κνοςό`). Pasa `--font-fallback "Charis SIL"
    --font-fallback "GFS Artemisia"`; y a veces hacen falta TRES —el `ϙ` (koppa) de
    Agripa no está ni en Charis SIL ni en Artemisia, sino en `GFS Didot`, y la nota que
    lo perdía trataba justamente de ese símbolo—. **`md_to_pdf` ya lo comprueba solo al
    terminar** (compara el repertorio no ASCII del markdown con el del PDF extraído y
    avisa de lo que falte): documentarlo no bastó, porque el mismo libro perdió el griego
    DOS veces. No busques «Missing character» en el log —no siempre se emite— ni te fíes
    del aviso viejo, que solo salta cuando NO hay ninguna fuente de reserva.
  - **GUARDA LA RECETA DE COMPILACIÓN JUNTO AL LIBRO** (`_BUILD_PDF.sh` en su carpeta), no
    en el scratch de la sesión. La segunda pérdida de griego de Agripa fue exactamente
    eso: el guion bueno se había borrado y se recompiló con una versión temprana a la que
    le faltaba la segunda `--font-fallback`.
  - **`--figure-captions` + una leyenda propia = la leyenda IMPRESA DOS VECES** (una del
    texto alternativo de la imagen y otra tuya). Si tus leyendas ya llevan el número de
    figura y la referencia, no pases la bandera.
  - **`\chapter*` NO reinicia el contador de notas**, así que con `--footnotes chapter`
    un apéndice —o el libro entero si usaste `--front-matter N`, que manda TODOS los
    archivos a esa rama— sale con la numeración CORRIDA: nota «222» donde el original
    dice 14. Ya está corregido en `make_unnumbered` (emite `\setcounter{footnote}{0}`),
    pero comprueba siempre el primer número de nota de un capítulo intermedio.
  - **`*x*.*` no se renderiza:** un `*` seguido de PUNTO no abre cursiva en pandoc, así
    que los asteriscos salen IMPRESOS (`Hismael*.*`). Y la maqueta corta la cursiva en el
    salto de renglón, con lo que el bisturí deja la primera letra en cursiva propia
    (`In*R* *eason, Experiment*`). Ambos se cazan de una: extrae el texto del PDF y busca
    `\S\*\S`; si hay alguno, el markdown tiene énfasis mal colocado.
  - **UNA NOTA SIN LLAMADA NO SE IMPRIME.** pandoc solo saca una nota si existe la LLAMADA
    `[^etiqueta]` en el cuerpo; la definición huérfana se descarta **EN SILENCIO**. Es
    demoledor en libros cuyo aparato se reconstruyó contando marcadores en un escaneo, donde
    solo se ancla una minoría: medido en *Nine Judges*, **1.463 notas de 1.995 no salieron**
    en el PDF —el log limpio, el balance refs↔defs cuadrando y el ratio de palabras del
    markdown intacto, porque el texto está: es la maquetación la que lo tira—.
    **Cómo se ve:** extrae el texto del PDF y busca en él el arranque de CADA definición del
    markdown (normalizando la partición de palabras a final de línea, o salen ~50 falsos
    positivos). **Cómo se arregla:** `imprime_sin_anclar.py ./es --apply` convierte las
    definiciones sin llamada en texto corriente al final de su archivo, con su número, bajo
    un epígrafe. Así se imprimen todas sin fingir un anclaje no verificado. En *Nine Judges*
    el libro pasó de 614 a 753 páginas.
  - **Y una llamada DENTRO DE UN ENCABEZADO también se descarta.** `## §10.1: Título—Sahl[^2]`
    pierde la nota (y ensucia el índice). Sácala al primer párrafo del capítulo: 28 casos en
    *Nine Judges*, 28 notas recuperadas.
  - **EL TITULILLO LARGO SE PEGA AL CUERPO, y memoir REGENERA la marca.** Con títulos
    de capítulo largos, el titulillo desborda el encabezado y se confunde con el párrafo.
    Poner un `\markboth` propio NO basta: memoir vuelve a componer la marca al maquetar
    la página y pisa el que hayas añadido antes. **Hay que SUSTITUIR el `\markboth` que
    el propio conversor emite, no añadir otro.** El texto corto va explícito en el
    markdown, `<!-- titulillo: Libro I · capítulo 50 -->` tras el H1, porque ni memoir ni
    el título saben a qué Libro pertenece el capítulo. Medido en Agripa (214 capítulos).
  - **`--own-section-numbers` NO bastaba: memoir seguía numerando.** El conversor quitaba
    el «Capítulo N.» del título para no duplicar, pero dejaba que memoir pusiera el suyo
    —y su contador es CORRIDO sobre todos los archivos—, así que en un libro cuyos
    capítulos reinician por Libro salía «184» donde el original dice 50, **pegado al
    título** en el índice. Ahora con esa bandera el título conserva su número y el
    capítulo va sin numerar. Y `--chapter-size large` encoge el título de APERTURA:
    un título largo pasó de 9 renglones a 5, y el libro de 822 a 808 páginas.
  - **DEMASIADA HIFENACIÓN: `--less-hyphenation`.** En castellano justificado a medida
    estrecha, LaTeX llega a partir el **10 % de los renglones**, y cientos de esos cortes
    dejan fragmentos de una o dos letras. La bandera sube `\lefthyphenmin`/`righthyphenmin`
    a 3, penaliza el guion y da `emergencystretch`, para que TeX estire los espacios antes
    de partir la palabra. Medido en Agripa: **del 8,3 % al 2,3 %** de renglones partidos,
    al coste de 1 página de cada 57.
  - **RENDERIZA UNA PÁGINA Y MÍRALA: es el único control que ve esto.** En un muestreo salió
    un **titulillo de página impreso a media prosa** («*§§7.60-71: MERCANCÍAS ¢” PRECIOS 279*»,
    con el `&` destrozado y el folio dentro). Iba en CURSIVA, así que el limpiador que solo
    miraba texto normal no lo veía, y ninguna medición de texto lo delata.
  - **Los marcadores `<!-- p. N -->` en línea propia PARTEN el párrafo al maquetar**: un
    comentario HTML aislado es un BLOQUE para pandoc, así que sale punto y aparte donde el
    libro sólo cambiaba de página. **En el markdown no se ve; en el PDF sí.** Pásalos inline,
    al final de la línea anterior, cuando la frase continúa (la siguiente arranca en
    minúscula). Al detectarlos, busca la línea anterior **HACIA ATRÁS**: entre el texto y el
    marcador hay un renglón EN BLANCO y comparar con la inmediata no detecta ni un caso. No
    los unas tras una leyenda de figura. Medido: 95 párrafos partidos en el clúster «de radiis».
- Entregar un capítulo suelto en otro formato: `pandoc cap.md -o cap.epub|.docx`.
- **Libro fuente en LaTeX** (ediciones tipo janegca de Valens y clásicos helenísticos)
  → `python3 $T/latex_to_markdown.py maestro.tex --root ./src --out libro.md`.
  Expande los `\input`, mapea starfont/wasysym a Unicode (`\Saturn`→♄) y pasa por pandoc.

## Traducir un LIBRO ENTERO a otro idioma → PDF (PARADIGMA de calidad)

> Cuando el usuario pide algo como **«convierte X, trocéalo, tradúcelo [y hazme el PDF]»**,
> este es el flujo de referencia. Es **genérico** (cualquier libro, cualquier idioma destino),
> no temático. Paradigma probado de punta a punta en las **Natividades Persas I-IV** (Dykes,
> 4 tomos, ~2.100 pp de PDF español, ~5.700 notas reconstruidas). Objetivo: **altísima calidad
> con el mínimo de tokens tuyos** — orquestas subagentes, no traduces tú a mano.

1. **Diagnostica y convierte** (§ de arriba): a markdown por capítulo, en `en/` (o el idioma
   fuente). Si hay notas dañadas, **reconstruye el aparato ANTES de traducir** (§3c / `/reconstruir-notas`).
2. **Fija la terminología UNA vez:** crea `glosario.md` en la carpeta del libro (hereda del
   tomo/obra hermana si existe). Todas las decisiones (términos técnicos, transliteraciones a
   conservar en cursiva, nombres propios) viven ahí; los subagentes lo leen y NO lo editan
   (reportan términos nuevos y tú los consolidas).
3. **TRADUCIR-COMO-QA (el corazón del método):** lanza **un subagente por obra/capítulo** que
   (a) **corrige el inglés EN SITIO** contra la fuente y (b) **escribe el español**, con los
   MISMOS anclajes `[^N]`. Traducir frase a frase es el MEJOR control de calidad: destapa huecos
   que una auditoría por ratio NO ve (en las Natividades aparecieron notas fundidas/mal
   numeradas, capítulos enteros ausentes, y hasta el final de un libro truncado). Cada agente
   reconstruye el aparato de notas y reporta balance.
4. **La IMAGEN es la fuente autoritativa** en escaneos degradados: si la capa OCR es basura pero
   las imágenes del PDF son legibles, el agente **traduce leyendo las imágenes** (`pdftoppm`),
   no el texto OCR. Esto salva libros que la auditoría daría por «mejor esfuerzo». **NUNCA**
   corrijas árabe/latín/griego/nombres/cifras «a ojo»: verifícalo contra la imagen; lo que no
   sea transcribible con certeza se marca honesto, no se inventa.
5. **GIGANTES → trocear + consolidar (ahorro de tokens y a prueba de cortes):** un archivo
   grande se parte por rango de capítulos/páginas; **un subagente por tramo escribe a PARCIALES
   en `/tmp/`** (nunca al archivo final, para no colisionar) con notas numeradas 1-based locales;
   **tú consolidas** concatenando los tramos y **renumerando las notas por offset** (script
   Python de ~10 líneas: `re.sub(r'\[\^(\d+)\]', +offset)` + separar cuerpo/definiciones).
5a-bis. **POLÍTICA FIRME DEL USUARIO (2026-07-30): todo archivo de más de ~4.000 palabras
   se traduce YA de entrada con `agy_retranslate_chunks.py`, no con `agy_translate.py`.**
   No es una optimización: es la respuesta al patrón que el usuario lleva viendo en MUCHAS
   sesiones —«agy siempre es igual»— y que un agente, que solo recuerda la suya, no puede
   ver. Los fallos de agy se concentran SIEMPRE en los archivos largos: cuanto más larga es
   la entrada, más tiende a RESUMIR en vez de traducir. `agy_translate.py` verifica el
   archivo ENTERO al final, así que cuando detecta el problema la única salida es relanzarlo
   completo… y vuelve a fallar, porque el trozo grande sigue siendo grande (medido en el
   Picatrix 3.11: dos pasadas, ratio 0.68 y 0.86). `agy_retranslate_chunks.py` verifica
   CADA TROZO al vuelo (ratio + sus `[^N]`), reintenta solo el que falla y, si insiste, lo
   parte en dos: ataja el fallo donde ocurre. Para archivos cortos `agy_translate.py` sigue
   valiendo (41 de 42 limpios a la primera en ese mismo libro).
   **Y al informar, di SIEMPRE cuántos pasaron limpios, no solo cuántos fallaron:** contar
   solo los fallos da la impresión de que agy falla siempre, y es un sesgo del informe, no
   un dato del motor.

   **CORRECCIÓN MEDIDA (2026-07-31, Astral High Magic): el umbral de 4.000 palabras NO
   protege.** Un archivo de **1.942 palabras** —menos de la mitad del umbral— salió con
   **ratio 0.14**: agy devolvió 273 palabras, solo el ÚLTIMO párrafo del cuerpo, con el
   bloque de notas entero y correcto detrás (así que el aparato cuadraba y solo el ratio lo
   delataba). Relanzado con `agy_retranslate_chunks.py --chunk-words 500` dio 1.04 a la
   primera. **Conclusión: el tamaño del archivo no es el discriminante fiable; lo que
   protege es VERIFICAR POR TROZO.** Usa `agy_retranslate_chunks.py` por defecto en
   cualquier archivo que no sea trivialmente corto, y reserva `agy_translate.py` para
   capítulos de pocos cientos de palabras. El umbral de 4.000 sigue siendo el mínimo
   OBLIGATORIO, no el criterio suficiente.

5b-bis. **EL RATIO NO VE UN TROZO SIN TRADUCIR: mide VOLUMEN, no IDIOMA.** Un trozo que
   vuelve en el idioma origen ocupa aproximadamente lo mismo que ocuparía traducido, así
   que el ratio sale perfecto. Medido en Lehrich: **13 párrafos seguidos —1.260 palabras—
   en inglés** dentro de un archivo con ratio 1.073 que había pasado TODOS los demás
   controles (notas, tablas, encabezados, figuras). Lo detectó el usuario leyendo, no la
   verificación. `parrafos_sin_traducir()` lo decide por **palabras funcionales** —los
   nombres propios, los títulos y el latín coinciden en ambos idiomas, pero «the/of/and»
   frente a «el/de/y» no— e ignora las definiciones de nota y los bloques cortos.
   **Falsos positivos legítimos que hay que saber leer:** las entradas de bibliografía y
   las listas de abreviaturas son títulos en inglés con solo un par de palabras
   traducibles; ahí la señal salta con razón y no hay nada que arreglar.

5b. **Si traduces con `agy_translate.py`, VERIFICA Y REINTENTA — no es determinista.** Tres
   modos de fallo, todos silenciosos y caros: (a) **reemite un trozo entero** (se ve
   como ENCABEZADOS REPETIDOS, no por el ratio: medido en un Libro que salió con 13
   encabezados en vez de 7); (b) **pierde algún anclaje `[^N]`**; (c) **SE SALTA PÁRRAFOS
   ENTEROS DE PROSA SIN TOCAR EL APARATO DE NOTAS** — el balance `[^N]` cuadra 21/21 y aun
   así faltan 1.200 palabras (Picatrix 3.11). El control natural (balance de notas) NO lo
   ve: **solo el ratio lo delata**. Para localizar el hueco, compara el volumen de texto
   ENTRE llamadas consecutivas: las `[^N]` son idénticas en ambos idiomas, así que parten
   los dos textos por los mismos puntos y el tramo con déficit salta a la vista. Envuelve la llamada en
   un lanzador que compruebe encabezados repetidos, encabezados EN=ES, figuras idénticas,
   definiciones completas y ratio, y **reintente con `--chunk-words` menor**.
   **Calibra el criterio:** el umbral NO debe ser «cero pérdidas». Relanzar 20.000
   palabras por 1 llamada de 257 cuesta una pasada entera y puede salir PEOR, porque el
   reintento SOBRESCRIBE y no se comparan los dos resultados; tolera ≤2 llamadas o ≤2 %
   y arregla el fleco a mano. En sentido contrario, **añadir** llamadas suele ser MEJORA
   (agy ancla notas que el OCR dejó sueltas, y en un aparato con lemas latinos acierta):
   lístalas para verificarlas una a una contra su definición, pero no las rechaces.

5c. **LIBRO GRANDE → `traducir_libro.py`, POR FASES Y REANUDABLE.** Un libro de 200.000+
   palabras no cabe en una sesión (*Three Books of Occult Philosophy*: 228.000 palabras,
   214 archivos, ~18 h de motor en serie). No lo orquestes con un `for` de bash que se
   salte lo hecho **mirando si el archivo de salida existe**: un archivo escrito a medias,
   o uno que agy resumió, EXISTE igual y se da por bueno para siempre. Aquí el criterio
   para marcar un archivo como hecho es que **PASE LA VERIFICACIÓN**, y el estado se
   escribe en un JSON **tras CADA archivo**, así que una sesión cortada pierde como mucho
   el que estuviera en curso. `--desde/--hasta` acotan un Libro; `--max N` traduce N y
   para (fases pausables); `--informe` lista lo que falta; `--rehacer` reintenta los que
   quedaron en fallo.
   **NUNCA BORRES el archivo traducido para rehacerlo:** el motor lo SOBRESCRIBE, así
   que borrarlo no aporta nada y quita la red de seguridad si el reintento sale peor.
   Basta con desmarcarlo en el estado. Y no lo desmarques a mano: el estado guarda la
   **huella del ORIGEN**, así que el propio programa detecta qué archivos cambiaron y los
   devuelve a la cola. Medido a base de fallar: una normalización de espacios tocó 78
   archivos cuando de verdad afectaba a 3, y desmarcar «los que cambiaron» a ojo tiró 33
   traducciones buenas.
   **Y verifica que el APARATO se haya TRADUCIDO.** Punto ciego caro: el cuerpo sale
   traducido y el bloque `## Notes` vuelve INTACTO en el idioma origen. No lo ve ningún
   otro control —los `[^N]` cuadran, el ratio EXCLUYE las definiciones por diseño, y la
   comparación de encabezados mira los niveles `#`, no su texto—. Medido en Agripa:
   **32 archivos del Libro III**, todos consecutivos.
   **El discriminante correcto es comparar CADA definición con la SUYA**, no el
   vocabulario: un aparato de referencias es casi todo títulos y nombres propios —muchos
   en inglés con toda legitimidad— y da **88 % de vocabulario común estando perfectamente
   traducido** (medido en Lehrich, que me costó un falso positivo). Una nota traducida
   DIFIERE de su original; una que volvió intacta es idéntica carácter por carácter.
   **Dos guardas necesarias:** solo cuentan las definiciones con ≥6 palabras (una nota
   que es una sola palabra latina, `*Westphaliae.*`, es idéntica con razón) y hacen falta
   al menos 3 de ellas.
   **Esa guarda deja un hueco, y se tapa con el ENCABEZADO**: el conversor siempre
   escribe `## Notes`, así que si ese rótulo sigue ahí en la traducción, el bloque no se
   tocó — y esa señal SÍ vale cuando el aparato es corto y bibliográfico, que es justo
   donde la comparación de vocabulario se abstiene. Los dos controles se complementan:
   el vocabulario para los aparatos largos, el encabezado para los cortos.
   **Y verifica las TABLAS**: si el motor funde dos columnas o se come un renglón, el
   ratio apenas se mueve y el balance de notas ni se entera. En un libro cuyas tablas son
   el CONTENIDO —las Escalas de los números de Agripa— eso es pérdida grave e invisible.

5d. **CUOTA AGOTADA A MEDIO LIBRO → `traducir_cascada.py`.** `agy` no es un modelo, es una
   PASARELA multi-modelo (Gemini Pro/Flash, Claude Sonnet y Opus, GPT-OSS), y cada uno tiene
   su cuota. Cuando el motor en uso se queda sin ella a mitad de un libro, la traducción se
   para y hay que estar delante para relanzarla con otro `--model`. Esto los encadena y sigue
   sin perder nada, porque el estado de `traducir_libro.py` se escribe tras cada archivo:
   `traducir_cascada.py markdown --out es --glosario g.md --prompt P.txt --parallel 2`.
   El orden por defecto es **calidad descendente, no capacidad**: que lo primero en agotarse
   sea lo mejor, para que el grueso salga con el mejor motor y solo la cola caiga en los flojos.
   **Lo que hacía falta para que esto funcione:** `agy()` devolvía sólo `stdout` y tiraba el
   código de salida y el `stderr`, así que **una cuota agotada llegaba como cadena VACÍA,
   indistinguible de un trozo mal traducido** — el trozo se reintentaba, se partía en dos,
   volvía a fallar, y el libro entero se habría marcado «en fallo» archivo a archivo sin que
   nadie supiera que bastaba con cambiar de modelo. Ahora se distingue (`MotorAgotado`, código
   **86**), con un reintento previo para que un blip transitorio no tumbe un modelo entero, y
   **no se escribe el `.md`** al agotarse: media traducción en disco es peor que ninguna,
   porque el archivo existiría y parecería hecho.
   `--solo a.md b.md` procesa archivos concretos EN ESE ORDEN, para gastar la cuota escasa de
   un motor bueno en los capítulos que más la necesitan y no en los que caigan primero por
   orden alfabético. **Medido:** los seis modelos agotados el mismo día, todos con reinicio a
   ~167 h, así que cuenta con que la cascada entera se te acabe y planifica el resto.

6. **RITMO por el límite de sesión:** los agentes que leen imágenes consumen mucho → lanza
   **2 a la vez**, espera, y sigue. **Cada tramo terminado se guarda en disco**, así que una
   sesión que se corte no pierde nada: se reanuda leyendo el estado de `es/` y los parciales de
   `/tmp/`. Para pausas largas, deja un `_RESUME_….md` autónomo en la carpeta.
7. **Convenciones de entrega (firmes, del usuario):** notas `[^N]` ANCLADAS donde la imagen
   muestre el superíndice; **sin encabezado «Notas» vacío** (`md_to_pdf` lo borra solo); **sin
   índice analítico** salvo que lo pida; **portada SIN «(uso privado de estudio)»**; el **glosario
   del libro se PRESENTA en el idioma destino** (lema traducido + original en cursiva,
   re-alfabetizado), no se «traduce del inglés»; **nunca líneas hiperextensas** (prosa→párrafos,
   verso→un párrafo por verso con el nº en negrita); **verifica las FRONTERAS entre archivos**
   (los capítulos se filtran de un archivo a otro).
8. **PDF y verificación:** `md_to_pdf.py … --toc --footnotes chapter` bajo `systemd-run -p
   MemoryMax=4G` (`--font-fallback "Noto Naskh Arabic"` si hay árabe suelto). Verifica: **0
   «Missing character»** en el log, **balance de notas en=es** (inline==defs por archivo), ratio
   de palabras es/en ~1.0 (sin truncar), y **renderiza 2-3 páginas** para leerlas contra la imagen.

### Tablas que vienen como IMAGEN (y cuáles NO transcribir)

Las ediciones modernas de tratados renacentistas meten las tablas del original como
**imágenes**, así que el texto no está: no se puede leer, ni buscar, ni traducir.
Medido en *Three Books of Occult Philosophy* (Purdue), 183 imágenes en 4 familias muy
distintas, y **tratarlas igual es el error**:

- **Tablas de correspondencias con texto** (las 12 «Escalas de los números» de Agripa) →
  **transcribir a tabla markdown**. Son 134 filas y son la obra misma. Markdown no tiene
  celdas combinadas, así que la etiqueta de grupo se deja en blanco en los renglones de
  continuación (lo más parecido al original) y la columna «mundo» va al final.
  **La tabla se pone DEBAJO de la lámina, no en su lugar:** la imagen sigue siendo la
  fuente autoritativa (conserva el hebreo y la maqueta) y la tabla la hace legible.
- **Palabras sueltas en otro alfabeto puestas como imagen** (65 aquí: `img_009.jpg` son
  30×16 px con שדי a media frase) → **devolverlas al texto como Unicode**; si no, el
  capítulo no se puede buscar ni leer entero.
- **Láminas de escritura densa** (tablas *ziruph* de 22×22 = 484 letras hebreas) →
  **NO transcribir**. Copiarlas a mano introduce erratas invisibles donde cada letra
  cuenta; la imagen es la fuente y lo honesto es dejarla, traduciendo solo el título.
- **Sellos, sigilos, caracteres y diagramas** → se quedan como imagen: son glifos.
  Y a veces la imagen ES el contenido: el cap. 52 de Agripa trata DE LAS FORMAS de los
  caracteres y muestra **dos variantes históricas** del de Saturno, ninguna igual al ♄
  moderno. Sustituirlas por Unicode destruiría justo aquello de lo que habla el capítulo.

**El defecto de verdad no era transcribirlas, sino que iban en BLOQUE.** Un glifo de 20 px
emitido como párrafo propio **parte la frase en tantos trozos como glifos** —37 en ese
capítulo—, y el párrafo deja de leerse tanto en el markdown como en el PDF. Las imágenes
por debajo de ~60 px de alto van EN LÍNEA: `epub_to_markdown.py --inline-img-px 60`
(por defecto). Medido en Agripa: 61 glifos, 123 archivos recompuestos.

**Clasifícalas por DIMENSIONES antes de decidir** (`< 80 px` de alto = palabra inline;
`> 600×500` = lámina o tabla), no por el capítulo en el que caen: en el mismo capítulo de
las Escalas conviven una tabla de 850×1127 y cinco palabras hebreas de 30 px.

## YouTube → markdown de estudio (skill `/youtube`)

Otra fuente además de libros: videos de YouTube, vía **`yt-dlp`**.
- `python3 $T/yt_transcript.py "URL" --list` → sondea (subs manuales, auto, capítulos).
- `python3 $T/yt_transcript.py "URL" --lang es` → texto limpio **sin timestamps y
  sin la duplicación de los auto-subtítulos** (fusión de solapes) + `meta.json`.
  Prefiere subs manuales; cae a auto-generados. También limpia un `.vtt/.srt` local.
- Luego **el agente** restaura puntuación, mayúsculas, párrafos y ortografía y
  arma el `.md` (front matter + `##` por capítulo). NUNCA resumir: es transcripción
  editada, íntegra.
- Descargas: `python3 $T/yt_media.py "URL" --audio|--video|--subs|--info`.
- **Sin subtítulos** (ni manuales ni auto): transcribe el audio con ASR local
  (faster-whisper). Prepara una vez `bash $T/asr_setup.sh` y usa
  `~/.local/share/forja-asr-venv/bin/python $T/yt_audio_transcribe.py "URL" --lang es`.
  Prueba un tramo (`--start/--end`) antes de lanzar horas de CPU. Videos ocultos
  no listados bajan solos; para privados/con login usa `--cookies cookies.txt`
  (en WSL, `--cookies-from-browser` NO lee la Vivaldi de Windows: exporta cookies.txt).

## Transcripción con visión (agy/Gemini) y ayudantes de OCR
Cuando la capa OCR es basura pero **la imagen es legible** y ni Docling ni el re-OCR
bastan, transcribe leyendo la IMAGEN con un modelo de visión:
- `agy_transcribe.py x.pdf --out ./paginas` — orquesta la transcripción página a página
  con agy/Gemini (naming de figuras robusto; sanado que escala a Claude; `--no-heal`).
- `agy_consolidate.py ./paginas --out cap.md` — cose esas transcripciones por página en
  un capítulo coherente.
- `agy_translate.py cap.md --out cap-es.md --glosario g.md` — el MOTOR de traducción con
  agy/Gemini troceando + QA estructural (lo que usan `/traducir-md` y el paradigma de
  libro entero); `chunk_defs()` evita truncar el bloque de notas. **Solo para archivos
  CORTOS** (< ~4.000 palabras): verifica al final, no por trozo.
- `agy_retranslate_chunks.py cap.md --out cap-es.md --glosario g.md --prompt P.txt` — el
  mismo trabajo pero **verificando CADA TROZO nada más traducirlo** (ratio + sus `[^N]`),
  reintentando solo el que falla y partiéndolo en dos si insiste. **Es el que se usa POR
  DEFECTO en archivos largos** (política firme del usuario, §5a-bis): ahí es donde agy
  resume en vez de traducir, y `agy_translate` solo se entera cuando ya no hay reparación
  barata.
Ayudantes de OCR (los usa la skill `/ocr`): `ocr_preprocess.py` (deskew/contraste/
binarización antes de tesseract) y `ocr_corruption.py` (detecta texto reconocido corrupto
para corregirlo con criterio). Detalle fino de todos: `tools/CATALOG.md` y `tools/README.md`.

## Herramientas disponibles en el equipo
Scripts del repo · `pandoc` · `ocrmypdf` · `tesseract` · poppler (`pdfinfo`,
`pdftotext`, `pdfimages`) · `mutool` · **`docling`** (PDF complejos) ·
**`markitdown`** (Office/html/imágenes) · **`yt-dlp`** + `ffmpeg` (YouTube) ·
**`faster-whisper`** (ASR local, venv). Sin claves de API.

Detalles finos de cada script (manejo de notas por formato, límites): ver
`README.md` y `tools/README.md`.
