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

Define `T=tools` (o ruta absoluta `/mnt/c/ideas/_La_Forja/tools`).

### 1. Enrutar por formato
- `.epub` → §EPUB.  `.rtf` → `python3 $T/rtf_to_markdown.py x.rtf --dry-run` (deriva
  las secciones del layout; `--emit-plan p.json` si hay que corregirlas a mano).
- `.docx .pptx .xlsx .html .png .jpg` → `markitdown x` (NO es trabajo de los scripts).
- `.pdf` → §PDF.

### 2. Diagnóstico PDF
```bash
pdfinfo x.pdf
chars=$(pdftotext -f 1 -l 5 x.pdf - 2>/dev/null | wc -c); echo "chars/5pp=$chars"
```
- **Encrypted: yes** → `qpdf --decrypt x.pdf x_dec.pdf` → re-diagnostica.
- **chars/5pp muy bajo (< ~500)** → escaneo sin texto → `ocrmypdf --skip-text x.pdf x_ocr.pdf`.
  - **Capa de texto MALA** (OCR corrupto, p. ej. Internet Archive: griego perdido,
    cursivas rotas) pero el escaneo es nítido → **re-OCR** con la skill `/ocr`. Para
    escaneos largos o si hay que **pausar**, usa `python3 $T/ocr_incremental.py x.pdf
    --lang eng` (lotes con checkpoint + resume + modelos best; `ocrmypdf` a secas no
    es reanudable). Modo `redo` sustituye la capa mala conservando la imagen.
  - **`ocrmypdf` deja la capa de texto EN BLANCO** (el PDF buscable resultante da
    `pdftotext` vacío pese a correr sin error): pasa con escaneos partidos/recodificados
    cuya estructura de objetos atasca a Ghostscript, aunque poppler renderice bien. Usa
    `ocr_incremental.py x.pdf --engine tesseract --tess-pdf --out x_ocr.pdf` — renderiza
    con poppler y deja que tesseract ponga la capa de texto (esquiva Ghostscript). Añade
    `--sidecar-out x.txt` si quieres además el texto plano.
- **Páginas apaisadas (ancho/alto > ~1.3)** → escaneo 2-up → `python3 $T/split_pdf_spreads.py x.pdf` (deja `x_1up.pdf`) ANTES de OCR/troceo.
  - **Si el 2-up lo vas a TRANSCRIBIR POR VISIÓN** (no OCR-ear), no uses el de arriba —que
    corta por la mitad geométrica— sino `python3 $T/split_scan_spreads.py x.pdf ./paginas`:
    extrae la imagen embebida con `pdfimages` (mucho más rápido que rasterizar) y corta **por
    el LOMO detectado**, no por el centro. **Nunca ajustes el corte a la caja de texto:** se
    come el arranque de cada línea de la página derecha («I decided to extend…» → «d to
    extend…») y en el markdown final eso es INVISIBLE. Cortar dentro de la franja negra del
    lomo no puede tocar texto; que asomen unas letras de la vecina es inofensivo. Verifica
    siempre con `check_scan_margins.py ./paginas` **y con los anchos anómalos** frente a la
    mediana (una página mucho más estrecha = corte que se comió texto). Otras dos trampas
    medidas: promediar la tinta sobre TODA la altura trunca la caja de las páginas con pocas
    líneas (última de capítulo, portadillas), y el recorte de bordes negros debe alternar
    filas/columnas **recalculando**, porque una banda negra horizontal infla el perfil de todas
    las columnas. El **folio impreso** da el mapeo página↔imagen y hay que validarlo:
    `libro = 2·N − 6 / 2·N − 5` en Travaglia, pero el offset cambia con el front matter.
  - **OJO rotación:** si `pdfinfo` da `Page rot: 90/270`, el ratio ancho/alto que ve
    `split_pdf_spreads` es el del MediaBox SIN rotar y no detecta el 2-up. Hornea la
    rotación primero: `qpdf --flatten-rotation x.pdf x_flat.pdf`.
  - **Cuadernillo de anillas escaneado ABIERTO (spread rotado 90° DENTRO de la
    imagen, `Page rot: 0`):** aquí `qpdf`/`split_pdf_spreads` NO sirven (el MediaBox es
    portrait y la rotación está en el contenido de la imagen, no en `/Rotate`; OSD de
    tesseract da baja confianza). Resuélvelo por imagen: `pdftoppm -r 300` → PIL
    `Image.rotate(-90, expand=True)` (prueba los 4 ángulos y OCR-ea para ver cuál da
    inglés real) → parte en mitad izquierda/derecha (descarta las mitades en blanco por
    densidad de tinta) → tesseract *best* por mitad (texto + `-c tessedit_create_pdf=1`)
    → `pdfunite` para el buscable upright. Orden de lectura: izquierda antes que derecha
    por hoja. Medido en «Project Hindsight Companion» (33 hojas → 65 páginas upright).
    **Si lo vas a TRANSCRIBIR POR VISIÓN, no partas por la mitad ni por el valle de una
    banda fija en torno al centro:** el escaneo lleva un margen de mesa que DESCENTRA el
    spread y el corte cae dentro del texto, dejando la página izquierda sin el final de
    cada línea (invisible después en el markdown). Localiza las **dos cajas de texto** por
    el perfil de tinta suavizado y corta en mitad del hueco que las separa; y recorta cada
    mitad a su caja de tinta, no por «bandas oscuras» (aquí el fondo es CLARO y ese recorte
    actúa distinto en cada hoja, descuadrando el partido). Y `pdfimages` en vez de
    `pdftoppm`: 44 hojas → 88 páginas en 12 s. Medido en *On the Stellar Rays* (Zoller/Hand).
  - **Escaneo MUY degradado donde `pdftotext -layout` REMEZCLA la prosa:** en algunos
    escaneos (bordes curvos de cuadernillo, bleed, columnas mal detectadas) el
    `-layout` dispersa el cuerpo en fragmentos de margen derecho («each», «es», «oth-»,
    «ers» → nativit**ies**, oth**ers**) y unir línea a línea top-to-bottom **descoloca
    el orden de lectura** (versos y frases salen entremezclados). Extrae entonces con
    **`pdftotext` en modo RAW (SIN `-layout`)**: respeta el orden de lectura interno del
    OCR y sale limpio en el grueso de páginas. Medido en Persian Nativities IV: `-layout`
    daba cuerpo remezclado + texto principal disfrazado de nota; raw lo arregló. Con raw,
    el running-head + nº de página quedan como líneas 1-2 (fáciles de quitar) y las notas
    al pie abren con marcador inequívoco (`' " * ®` o dígito+pista «cf./reads»); sepáralas
    de forma CONSERVADORA (mejor nota inline que verso de cuerpo disfrazado de nota). Los
    encabezados de capítulo y el TOC muy garbleados NO se recuperan del todo: su texto
    sigue presente pero algún corte falta → límite honesto, el PDF buscable manda.
  - **Escaneo con NOTAS AL PIE densas donde el OCR las INTERCALA con el cuerpo** (la
    nota cae a media frase) y/o **pierde los párrafos** de la prosa: el texto plano no
    basta porque el problema es de GEOMETRÍA. OCR-ea capturando la caja de cada palabra
    y sepáralo por posición/tamaño: `ocr_incremental.py x.pdf --engine tesseract --psm 6
    --tsv-out x.tsv` (+ `--sidecar-out`/`--tess-pdf` si quieres texto/PDF; resumible por
    lote) y luego **`ocr_geometry.py x.tsv --pages A-B`** separa running-head / cuerpo /
    **notas** (por el HUECO vertical antes del pie, señal robusta aunque la fuente de
    nota no sea claramente menor) y reconstruye **párrafos** por la sangría (mediana de
    márgenes, robusta a los marcadores volados «§ ¥» que cuelgan a la izquierda).
    `--join` para texto en verso (un bloque, luego `verse_paragraphs`). Medido en
    Theophilus of Edessa: quitó el intercalado nota↔cuerpo y cosió la prosa; los títulos
    de capítulo y prosa-vs-verso los pone el converter del libro. Límite: separa LAYOUT,
    no arregla el garble de reconocimiento en bordes de página.

### 3. ¿Bisturí o Docling?
Mira layout en una página de cuerpo:
```bash
pdftotext -layout -f 20 -l 20 x.pdf - | sed -n '1,40p'
pdfimages -list x.pdf | wc -l
```
**Docling** (`docling convert x.pdf --to md --output ./markdown/`) si hay:
multicolumna, tablas, fórmulas, muy ilustrado (imágenes ≫ páginas) o extracción
rota. Si es **prosa limpia a una columna** → bisturí (§3b). Ante la duda: 1
capítulo con bisturí, revisa el `.md`; si quedó sucio, repite con Docling.

> **PDF digital donde la CURSIVA importa** (texto académico: términos técnicos,
> transliteraciones, títulos de obra) → `pdf_rich_to_markdown.py`, NO Docling.
> Docling y `pdftotext` recuperan **0 cursivas**; la señal está en las fuentes
> embebidas (`pdffonts x.pdf | grep -i italic` lo confirma en un segundo). Además
> separa el texto **paralelo a 2 columnas** (original / traducción), que leído
> línea a línea sale en frases mestizas. Es el único bisturí que hace ambas cosas,
> así que «multicolumna → Docling» NO aplica si son columnas paralelas o hay
> cursiva significativa.
>
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
> **NUNCA cuentes llamadas de nota con «no seguido de dos puntos»** (`\[\^(\d+)\](?!:)`):
> hay llamadas legítimas delante de un dos puntos («…la verdadera naturaleza de la
> realidad[^23]:»). Una definición es la que **ABRE RENGLÓN**. Este error aparece siempre
> disfrazado de «nota huérfana» y hace perder tiempo.
>
> **Y ojo con el aparato de DOS CAPAS** (notas del traductor + notas largas del editor, como
> en Project Hindsight): si las notas del editor tienen VARIOS PÁRRAFOS, un separador que
> cierre la definición en el primer renglón en blanco deja los párrafos siguientes sueltos en
> el cuerpo, y al consolidar se acumulan al final del libro —impresos como prosa **después
> del colofón**—. Se detectan buscando líneas sangradas ANTES de la primera `[^N]:` del
> archivo. Además: **si un título de capítulo lleva llamada de nota**, y el título es el
> delimitador del troceo, esa nota se queda sin definición.

> **Escaneo largo o equipo que se puede cerrar:** usa
> `python3 $T/docling_incremental.py x.pdf --out ./markdown` — procesa por lotes
> de páginas con **checkpoint + resume + progreso** (no pierde el trabajo si se
> corta). Si el PDF ya trae capa de texto (ABBYY/nativo digital), añade `--no-ocr`
> (acelera mucho). `--image-export-mode placeholder` evita incrustar imágenes.

### 3c. Limpieza post-conversión (OCR/Docling → estudio)
Tras convertir, dejar el markdown listo para leer/traducir.

> **DOS PUERTAS ÚNICAS (empieza por aquí, no por los fixers sueltos):**
> - **`forja_limpiar.py ./markdown [--apply]`** — orquestador: aplica EN ORDEN el
>   núcleo determinista (ordinales→romanos→ligaduras→diacríticos, todos con guarda,
>   así que componerlos es seguro) y termina con el informe de artefactos a revisar.
>   Toggles según el libro: `--verses` (un párrafo por verso), `--notas` (rehace
>   `[^N]`), `--openings` (portadillas OUP), `--docling`, `--spell`. Dry-run por
>   defecto. Es la receta de esta sección ENCAPSULADA; generaliza a `limpiar_academico.py`.
> - **`fix_ocr.py <sub> FILE... [--apply]`** — correcciones OCR puntuales bajo un
>   comando: `ordinals·romans·ligatures·diacritics·spell·all`. Reúne los cinco
>   arregladores sueltos con una sola convención (dry-run, guardas intactas).
>
> Los scripts de abajo son las PIEZAS que esas dos puertas componen; córrelos sueltos
> solo para un caso muy concreto. La lógica y las guardas viven en ellos (y se testean
> ahí); las primitivas compartidas (diccionario, subproceso, pdftotext) están en
> `forja_common.py`.

- `clean_markdown.py` — quita running-headers de página (sin borrar contenido
  repetido legítimo), guion suave, saca imágenes base64 a archivo, normaliza espacios.
- `fix_markup.py FILE... [--apply]` — artefactos de MARKUP de la maqueta (InDesign/Quark):
  negrita partida por salto de línea (`**…** **…**`→`**… …**`), cursiva partida en
  subtítulos, ordinales con `**` espurios (`2**º`→`2º`), `****` sueltos, y encabezados de
  sección `§` dejados en negrita (`**§N: …**`→`## §N`; `§N.M`→`###`, convención Dykes; si
  el libro no usa `§`, esa regla no dispara). Idempotente. (Medido en Sahl & Māshā'allāh.)
- `reflow_columns.py FILE... [--apply]` — recompone la prosa cortada en fragmentos de
  una línea con comentarios `<!-- col N pág M -->`, que deja un bisturí al mal-leer una
  maqueta a DOS COLUMNAS paralelas (original|traducción, texto|variante). Cose los
  fragmentos abiertos (el texto principal cierra frase y hace de barrera); preserva el
  texto token a token. NO desentrelaza dos columnas de CONTENIDO distinto mezcladas línea
  a línea (eso pide leer la fuente y reconstruir a mano: p. ej. la lista §5.0 de Sahl).
- **FIGURAS de un libro ya convertido** cuyo markdown conserva las leyendas «**Figura N:
  …**» pero no las imágenes: `embed_figures_from_captions.py FUENTE.pdf --md-dir es
  --figures-dir figuras` recorta cada figura del PDF (localiza «Figure N», pide a agy la
  bbox del dibujo) y la incrusta ANTES de su leyenda. `crop_figure.py x.pdf --page N
  --bbox x0,y0,x1,y1` recorta una región suelta. **ATAJO sin agy:** si las figuras son
  imágenes RASTER embebidas (una por página, `pdfimages -list` lo confirma), extráelas
  PIXEL A PIXEL con `pdfimages -png -f N -l N x.pdf fig` — más limpio y sin gastar cuota;
  invierte las que salgan en negativo (brillo bajo) y, si dos comparten página, asígnalas
  por orden arriba→abajo. (Medido en Sahl: 56 figuras raster directas, 0 agy.)
- `cose_parrafos.py ./es/*.md [--apply]` — **el bisturí abre párrafo nuevo en cada
  CAMBIO DE PÁGINA**, así que un párrafo que cruza de página sale roto A MEDIA FRASE
  («…subdividió el abanico. En numerosas ␤␤ ocasiones Idel ha argumentado…»). Se lee,
  pero al maquetar salen dos párrafos con sangría donde el libro tiene uno. Medido en
  Lehrich: **251**; en Agripa, 22. **La señal decisiva es que el párrafo anterior NO
  CIERRA FRASE**, y hay que definir «cerrar» con cuidado: un `)` o un `»` sueltos NO
  cierran nada, así que el cierre exige puntuación TERMINAL de verdad (`. ! ? … : ;`).
  Exigir ADEMÁS que el siguiente abra en minúscula —la primera versión— deja fuera dos
  casos frecuentes y medidos: `…las imágenes (el tipo A)` ␤␤ `en la magia celeste` (el
  paréntesis fingía cierre) y `…para ambos pensadores, aunque` ␤␤ `Ficino, para
  defender…` (continúa en MAYÚSCULA). Por eso se une también tras **coma** —ningún
  párrafo termina en coma— y tras **palabra función abierta** (preposición, conjunción,
  artículo, relativo), que no puede ser la última de un párrafo pase lo que pase detrás.
  **Los ADVERBIOS de enlace NO van en esa lista** («además», «también», *also*): sí
  cierran el renglón que ENTRA en una cita en bloque, y meterlos funde la entradilla con
  la cita. Ese caso —coma + bloque largo en mayúscula— se reporta como `DUDOSO` y no se
  une. Guardas: un **subtítulo en cursiva** o una **leyenda de figura** tampoco cierran
  frase y son bloques completos; hay que excluirlos o son falsos positivos garantizados.
  **Y nunca se cose alrededor de una CITA EN BLOQUE**: ahí la
  frase del autor entra en la cita y sale de ella, y eso es la estructura del ORIGINAL.
  La causa raíz ya está corregida en `pdf_rich_to_markdown.py --indent-paragraphs`, que
  deja decidir a la SANGRÍA en vez de al salto de página; esta tool es para los libros
  ya convertidos.
- **HEBREO (o griego) COMPUESTO CON UNA FUENTE ASCII: se extrae como basura latina y
  NADA lo delata.** Muchas monografías de los 90-2000 no usan Unicode: meten el hebreo
  con una TrueType mapeada sobre ASCII (`SPTiberian`, `SuperHebrew`, `WP-GreekCentury`),
  sin `ToUnicode`. Sale `(K)lmw)` donde el libro imprime `ומלאך`, y el ratio cuadra —los
  caracteres están, uno por letra—, el balance de notas cuadra y el corrector lo toma por
  una sigla. En un libro sobre cábala eso es el objeto del capítulo, no un adorno.
  `hebreo_sp_a_unicode.py libro.pdf ./es/*.md [--apply]` lo restituye **sin adivinar**:
  no detecta «lo que parece hebreo» —`why`, `myth` y `thy` se escriben solo con letras
  del repertorio SP— sino que le PREGUNTA AL PDF qué cadenas van en esa fuente
  (`pdftohtml -xml` da texto + `fontspec`) y sustituye solo esas. **Dos trampas medidas
  en Lehrich:** (1) hay que **INVERTIR** la cadena entera, espacios incluidos, porque el
  PDF guarda los glifos en orden VISUAL y el hebreo se lee al revés —así se arregla de
  paso el orden de las PALABRAS: `hxwd hwhy K)lmw` → `ומלאך יהוה דוחה`—; (2) sin
  **frontera de token** las cadenas de dos o tres letras casan DENTRO de palabras
  corrientes (*t·hy·s*, *w·hy*) y salen **405 «restituciones» donde hay 54**, sembrando
  el texto de hebreo a media palabra. La frontera no puede ser `\b` (aquí `)` y `(` son
  letras): exige que no haya letra ni dígito pegados a los lados. Y sustituye **de más
  largo a más corto**, o el trozo corto parte el largo por la mitad.
  El **griego** de estas fuentes sale FRAGMENTADO (`pdftohtml` emite un carácter suelto y
  el resto en la fuente normal), así que ahí no vale el mismo automatismo: localiza las
  páginas con `pdffonts`/`fontspec`, **renderízalas y lee la palabra** (`[NVD:"6@<]` era
  `φαρμακον`; `*,\<TF4H`, `δείνωσις`).
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
- `citas_en_bloque.py ./markdown/*.md [--apply] [--comillas]` — los párrafos que son
  una **CITA ENTERA** salen del converter como prosa normal entrecomillada, porque la
  maqueta las marcaba con la SANGRÍA y esa señal no sobrevive. El markdown se lee, pero
  una cita de cinco renglones queda **indistinguible de la voz del autor**, que es justo
  lo que hay que ver de un vistazo. Las pasa a `>` y les quita las comillas que las
  envuelven (el bloque ya lo dice; dejar las dos cosas es redundante), respetando las
  interiores. Tres casos que un `sed` no cubre: **citas de VARIOS párrafos** (la comilla
  de cierre está tres párrafos más abajo, y entre dos bloques `>` separados por un
  renglón EN BLANCO pandoc ve DOS citas: el separador tiene que llevar su propio `>`);
  **cita que cierra a media línea** con la frase de transición del autor pegada detrás
  («…living Images."[^45] Agrippa goes on to note…»), que hay que PARTIR; y las
  **llamadas de nota** (`imágenes [^1]` va sin espacio; un punto tras la llamada cuando
  la frase ya cerró con `."` sobra). Medido en *Astral High Magic*: 23 citas, 3
  continuaciones, 1 partida, 40 llamadas pegadas.
  **Trampa cara:** un regex `^(#+ .*?)\s*:\s*$` en multilínea **se come el renglón en
  blanco siguiente** y pega el encabezado al párrafo (`\s` incluye `\n`) — hay que anclar
  con `[ \t]*`. No se ve leyendo el markdown por encima y lo estropea entero.
- `split_chapters.py libro.md --plan plan.json` (o `--by-heading 2`) — trocea en
  capítulos. Exige UNA de las dos banderas; el `.md` va siempre como posicional.
- `verse_paragraphs.py libro/*.md [--apply]` — texto **VERSIFICADO** (Abū Maʿshar,
  Valens, Doroteo…) que quedó como UN párrafo gigante por capítulo con los números
  de verso inline → los pone **un párrafo por verso** con el nº en negrita. Señal de
  verso = número 1..MAX SOLO seguido de MAYÚSCULA (descarta cantidades «30 signs» en
  minúscula; permite el reset por capítulo). No toca `#`/tablas/código/notas; es
  idempotente. Arregla de paso el caso «encabezado que se tragó el capítulo entero y
  renderiza todo en negrita». Dry-run por defecto. (Medido en Persian Nativities IV:
  líneas de 45.719 → ~2.600 chars.)
- `footnotes_rebuild.py cap.md --apply` — reconstruye notas `[^N]` **por capítulo**.
  Detecta 2 estilos de OCR: *pegado* (marcador partido `1 3 8`→`[^138]` + def. `114. …`)
  y *suelto* (marcador ` N ` con espacio + def. `N Texto` sin punto, incluso partida en
  dos líneas; numeración continua en todo el libro; libros AstroArt/Döser). NO en
  índices/bibliografía. Para rehacer un archivo ya convertido: revierte con regex
  (`^\[\^N\]:`→`N `, `\s*\[\^N\]`→` N`) y reaplica.
- **Aparato pegado al cuerpo SIN sangría fiable** (recortaste una columna de un facing
  árabe|inglés y el recorte reinició el margen, o el OCR aplastó la indentación): el
  módulo **`footnote_chain.py`** separa cuerpo/notas por la señal robusta de que los
  **números de nota son CONSECUTIVOS** (n, n+1, n+2…); un número no consecutivo —remisión
  «128 below», «3.3 above», cifra de prosa— se trata como continuación, no como nota nueva,
  y el nº de página del pie tampoco rompe la cadena. Ancla los volados aplastados por
  cursor ascendente. Dos formatos: número+texto en la misma línea (por defecto) o
  `--number-only` (volado solo en su renglón). Es LIBRERÍA (`from footnote_chain import
  process_page`) — la importa el bisturí, que conoce la maqueta; el CLI procesa un bloque
  suelto. (Medido en la Abbreviation de Abū Maʿshar, notas 1-112, y las Flowers, 1-308.)
- **PDF DIGITAL cuyos dígitos se pierden al extraer** (cursos y manuales con fuentes
  de símbolos: el párrafo se lee bien pero `Arc of Direction = RA °'"` ha quedado sin
  cifras). **Ningún control de §3d lo ve**: ni el ratio, ni el balance de notas, ni el
  corrector. Hay que medirlo contra el PDF:
  `pdf_restore_digits.py cap.md --pdf cap.pdf [--apply]` — la línea dañada es EXACTAMENTE
  el texto del PDF sin los dígitos, así que quitándoselos a ambos deben coincidir; solo
  se toca lo verificado y único, y la reinserción va en paralelo para no tocar negritas,
  cursivas ni `[^N]`. `pdftotext -layout` sí extrae esos dígitos: el fallo es del bisturí.
  El mismo fallo se lleva los volados de nota, así que después:
  `footnotes_from_pdf.py cap.md --pdf cap.pdf --apply [--interpolar]` — lee el aparato
  REAL del PDF (el número va en la línea anterior a la definición y sube 1,2,3…, lo que
  descarta los números de página), etiqueta los textos de nota sueltos, inserta los que
  falten y sitúa cada llamada por su contexto. **Ojo al asimetría:** una definición sin
  llamada NO se imprime (la nota se pierde), y un texto de nota sin etiquetar se imprime
  como prosa a mitad de capítulo. Verifica al final `definiciones == llamadas` y 0
  huérfanas. Medido en el Diploma Course de Zoller: 610 cifras y 624/624 notas.
- `index_rebuild.py viejo_indice.md libro.pdf --out nuevo.md --report faltan.txt` —
  el **índice analítico** del original no sirve tras traducir: sus números remiten a
  OTRA edición, y el OCR de un índice a 2 columnas suele entrelazarlas, así que no se
  puede ni renumerar (no sabes qué página es de qué entrada). Da igual: del viejo solo
  se aprovecha QUÉ términos indexar; las páginas se buscan en el PDF nuevo. **No es un
  grep**: un encabezado va invertido (`al-Rijāl, Ah ibn`), agrupa variantes (`África,
  africanos`) o normaliza flexión (`Abasíes` vs. «abasí»), así que se prueban variantes
  (buscar el encabezado tal cual falla en ~43%). Corre el `md_to_pdf` PRIMERO y pon el
  índice AL FINAL: así añadirlo no mueve la paginación medida. Límite honesto: sale
  **plano** (la jerarquía ya venía destruida) y es una concordancia curada, no el
  índice del autor. Lo no encontrado se reporta, no se esconde.
- `astro_glyphs.py --flag cap.md` — señala celdas de glifos astrológicos corruptas
  por OCR (♄♃♂ y signos) para corregirlas a mano contra la imagen; `--reference` = chuleta.
- `fix_ordinals.py ./markdown --apply` — ordinales volados que el OCR destroza en
  **escaneos**: `4 lh`→`4th`, `ll' h`→`11th`, `I 1 '`→`1st`, `12 ,h`→`12th`. Deriva el
  sufijo del NÚMERO (no adivina la corrupción), solo 1-31, y no toca horas/fechas/cifras.
  Crítico en libros de **casas** astrológicas o siglos: cambia el sentido y ningún
  corrector lo ve. (`docling_clean.py` ya cubre el caso LIMPIO `5 th`→`5th`.)
- `fix_roman_numerals.py cap.md [--apply]` — el OCR confunde numerales romanos con
  letras/dígitos y con el pronombre inglés «I»: `Volume IT`→`Volume II`, `Ch. IIL`→
  `Ch. III`, `1V`→`IV`, y el clásico `In Volume IT T will`→`In Volume II I will`.
  DOS reglas CON CONTEXTO: (1) numeral tras palabra-contador (Book/Volume/Chapter/
  Part…); (2) pronombre «I» leído `T/l/|` seguido de verbo de 1ª persona — NO toca
  las **siglas de manuscrito** («T reads», «P reads») porque exige verbo no-3ª-pers.
  Conservador: omite los ambiguos `IIL9`/`IL6` (¿`III` o `II.9`?) y los números
  arábigos («chapter 16»). Dry-run por defecto.
- `ocr_spellfix.py libro/*.md [--apply] [--max-edits 2]` — corrección ortográfica
  CONSERVADORA de erratas de OCR usando **el propio libro como modelo de frecuencia**
  (así protege transliteraciones y términos de dominio: lo que sale muchas veces es
  correcto y es buen destino de corrección — `Bosk`/`boks`→`Book`, `Centuty`→`Century`,
  `tather`→`father`). Pasa TODOS los .md juntos (mejor corpus). Reglas de seguridad:
  solo corrige a un destino MUY común, prioriza distancia 1 (edit-2 opcional y solo en
  minúsculas), protege MAYÚSCULAS/no-ASCII/≤3 letras y exige más frecuencia si el
  original va capitalizado (nombres propios). **Límite honesto:** ni así es perfecto
  —puede errar en latín/árabe sin diacríticos y fragmentos de OCR—, así que va en
  **dry-run por defecto: revisa la lista antes de `--apply`**. Para la corrección fina
  de verdad, una pasada de agente que lee en contexto sigue siendo lo más fiable.
- `flag_ocr_artifacts.py libro/*.md [--only tipo,tipo]` — **DETECTOR** (no corrige) de
  ruido de OCR camuflado que es fácil pasar por alto, para que TÚ lo arregles a mano
  contra la imagen. Marca: `garbage` (basura pura de tabla «010 OQ Fo…»), `glued`
  (entrada de glosario pegada a otra o a basura), `split` (párrafo cortado por salto de
  página sin unir), `dash` (guion espurio al inicio «- such a manner…»), `bracket`/
  `stray` (corchete colgando, cola basura «… . ] Bt»), `pagenum` (nº de página
  incrustado «29 more the sense…»). Estos defectos aparecen SOBRE TODO **debajo de las
  tablas** (restos que sobrevivieron al troceo) y en glosarios (entradas que el filtro
  de basura pegó o borró). Úsalo tras convertir un libro-diccionario para no dejar
  cabos: corre el detector, revisa cada marca contra la imagen y corrige con criterio.
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
- **TITULILLOS QUE SOBREVIVEN FUNDIDOS AL CUERPO**: el bisturí quita el titulillo por
  geometría, pero en las páginas donde el OCR lo pegó a la primera línea del texto ya no
  hay geometría que valga y **sale impreso a media página, en versales, cortando la
  frase**. En el markdown pasa desapercibido; **solo se ve RENDERIZANDO páginas del PDF**
  —renderizar no es un lujo, es el único control que ve esta clase de defecto—. Se borran
  por su TEXTO, y el anclaje NO puede ser el nombre del autor (el OCR lo escribe de tantas
  formas como páginas: `HERMANN`, `HERMAJVN`, `HERMAI\l\'`…) sino la constante: que la
  línea EMPIECE por las primeras letras en VERSALES (sin `re.I`: en la prosa el nombre va
  en caja mixta) y lleve el TÍTULO de la obra detrás. **Guarda obligatoria:** muchos libros
  tienen texto legítimo en versales dentro del cuerpo (rótulos de tabla, portadillas), así
  que borrar «toda línea en mayúsculas» destruye contenido real.
  **Automatizado en `quita_titulillos_fundidos.py`**, que exige las TRES constantes a la vez
  —4+ versales, número de página al final, y ningún fragmento en minúscula en el prefijo— y
  con `--encabezados` borra además los titulillos que el conversor llegó a PROMOVER a
  encabezado («# §A: INTRODUCTORY MATTERS 57»), pero solo si puede probar que están
  duplicados. Medido: 68 casos en *Nine Judges*. Ojo, **el discriminante es el nº de página,
  no las versales**: «VIDA», «AMISTADES», «CARRERAS DE CABALLOS» eran rótulos legítimos.
- **UN CAPÍTULO ENTERO PUEDE VIVIR DENTRO DEL APARATO, y ningún control lo nota.** En §7 de
  *Nine Judges*, 26 «definiciones de nota» eran en realidad el texto de un capítulo con su
  título y su autoridad —y **23 de esos capítulos no estaban en el cuerpo en absoluto**—.
  Se habrían impreso como notas al pie al final de la sección. No lo ve NADA de lo habitual:
  el balance de notas cuadra (son definiciones válidas), el recuento de encabezados cuadra
  (nunca hubo encabezado que perder) y el ratio de palabras cuadra (el texto está, en el
  sitio equivocado). **Solo se ve preguntándose DÓNDE está el texto, no SI está.**
  `rescata_capitulos.py cap.md --apply` los devuelve al cuerpo: la definición que abre por
  `§N.M: Título—Autoridad` arranca el bloque, y las etiquetas siguientes que empiezan en
  MINÚSCULA son su continuación partida por el salto de página. Dos avisos medidos: al
  reubicar, las llamadas de las etiquetas consumidas quedan **huérfanas** (hay que quitarlas)
  y algún bloque trae una nota real empalmada dentro del TÍTULO, que hay que separar a mano.
- **ATRIBUCIONES DE AUTORÍA DESTROZADAS** (compendios que asignan cada capítulo a una
  autoridad tras una raya: «—Sahl», «—ʿUmar»): el OCR escribe nueve nombres de cincuenta
  formas —«Sah», «SahF», «Sahb», «Jitjis», «al-Kindr», «aAristotle»— y al limpiar la basura
  del final algunos quedan TRUNCADOS. Como el repertorio es CERRADO se normaliza sin adivinar:
  `normaliza_autores.py ./es --idioma es --apply`. **Dos guardas que evitaron destrozos:** un
  `[^N]` pegado al nombre es una LLAMADA legítima y hay que preservarla; y el guion de
  «al-Rijāl» NO es separador de autoría —tomarlo por tal se comía el «I.5.1» de un título—.
- **COTEJAR EL APARATO CONTRA EL PIE IMPRESO** cuando las notas se reconstruyeron contando
  marcadores: `coteja_aparato.py cap.md --pdf libro.pdf --paginas 28-67` OCR-ea la franja
  inferior de cada página, lee los números REALES (en el pie sí van en cuerpo normal, al
  contrario que los volados) y compara por el ARRANQUE DEL TEXTO, no por el número, de modo
  que el desfase aparece como patrón. Medido en la Introducción de *Nine Judges*: 5 notas
  corridas +1, 4 corridas +2 y 2 desaparecidas. **La causa raíz era que el conversor PARTÍA
  en dos las notas que cruzan un salto de página** y registraba cada mitad como nota nueva;
  cada partición mete un número de más y desde ahí todo se corre. El balance refs↔defs
  cuadraba y el markdown se leía sin sobresaltos.
- **MARCAS DE DUDA DEL TRADUCTOR** (`[?: …]`, cuando se le prohíbe inventar ante un resto de
  OCR): no todas son iguales y tratarlas igual es el error. `limpia_dudas.py ./es --apply`
  las clasifica en tres: RUIDO (la cola de una llamada de nota que el escaneo se comió → se
  borra), REFERENCIA cruzada donde la marca es lo ÚNICO que hay («Véase `[?: VIL6.]`» → se
  repara normalizando el destrozo `I`↔`J [ L T H U 1`) y lo demás, que se LISTA para mirarlo
  a mano. Medido: de 682 marcas, 469 eran ruido y 33 referencias reparables. **La señal que
  distingue redundante de portante es si lo de DELANTE queda abierto** (palabra función o
  paréntesis sin cerrar): «*Recti* [?: Reefi]» no perdió nada, «asoció a [?: …]» perdió
  «Trismegisto». Y cuidado: una marca puede estar sustituyendo a un conector —`[?: *¢>*]`
  era un `&`, y borrarlo dejaba «Éxito fracaso en la vida»—.
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
- **SEPARAR LAS NOTAS DE UN COMENTARIO POR LA CADENA ASCENDENTE: cuatro trampas medidas.**
  Cuando el aparato vive en un bloque aparte («3.16 / 1. … 2. …»), se trocea buscando el
  número siguiente de la cadena, como en `footnote_chain.py`. Pero: (1) la guarda del número
  tiene que excluir el **guion**, o «Enn 4.4.41.6-8» parte la nota 7 y le roba el cuerpo a la
  8; (2) una nota puede **abrir con un dígito** («32. 4 *ad fin.*, ed. Frette»), así que
  exigir mayúscula detrás corta la cadena a la mitad —hace falta un patrón de reserva
  anclado a principio de renglón—; (3) el OCR escribe la nota 1 como **«l.»** (ele), y sin
  normalizarlo la cadena engancha el «1» de un «10.» de más abajo y **se pierde el capítulo
  entero**; (4) prueba SIEMPRE primero el patrón de principio de renglón. Un partidor sin
  estas guardas junta notas cortas con la anterior y trocea las largas en cinco: en Ficino
  daba claves fantasma («3.17-46», «3.16-41») que **parecían definiciones válidas**.
- **UNA NOTA SIN LLAMADA NO SE IMPRIME, y el escaneo se come los volados.** Al auditar el
  aparato no basta con «toda llamada tiene definición»: hay que comprobar **al revés**, que
  toda definición tenga llamada. En Ficino, 67 de 274 no la tenían —el volado había quedado
  como `Lion5`, `straw 1`, `Ptolemy29`, `crowned 9`, una comilla suelta o nada—, y el balance
  «llamadas ⊆ definiciones» daba limpio. La cadena de cada capítulo debe ser **1..N completa
  y en orden estricto**; un número repetido o fuera de orden es una llamada mal etiquetada
  que apunta a otra nota.
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
- `chapter_bounds.py libro.pdf clean.md --sections secs.json --offset N [--apply]` —
  cuando **no puedes fiarte de los encabezados** de Docling: título repetido como
  running header y promovido a encabezado en sitio equivocado (¡a mitad de frase!),
  título recurrente como subtítulo, o título centrado partido en 2 líneas. Localiza el
  límite REAL de cada capítulo por la **frase de apertura** de su página en el PDF
  (índice → página del libro + `--offset` = página PDF). Determinista. `--apply` inserta
  los `#` y borra los encabezados espurios → luego `split_chapters.py --by-heading 1`.
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

> **Orden del flujo (importante):** en un escaneo con notas, hazlo
> **convertir → RECONSTRUIR NOTAS → traducir → PDF**. Si traduces antes, hay que rehacer
> el aparato en los dos idiomas a la vez. Comprueba SIEMPRE `grep -c "\[\^" markdown/*.md`
> antes de lanzar traducciones: sin `[^N]`, las citas se imprimen como párrafos sueltos
> en mitad del texto.

> **Nombres de archivo en Unicode DESCOMPUESTO (NFD):** «Öner Döser» puede estar en disco
> como `O`+U+0308. `pdfinfo`/`pdftotext` fallan aunque `ls` lo muestre bien, y **copiar la
> ruta de `ls` tampoco sirve**. Resuélvelo SIEMPRE por glob: `F=$(ls *Financial*.pdf | head -1)`.
> Afecta también al `.md` que genera `docling_incremental.py`.

### 3d. VERIFICACIÓN de completitud (obligatorio antes de traducir/publicar)
Los bisturíes pueden **perder texto sin avisar** (años, cláusulas) según el layout;
es invisible salvo que se mida. NO des una conversión por buena hasta verificar:
- `check_completeness.py cap.pdf cap.md [--pages A-B] [--repair]` — alinea el
  markdown contra `pdftotext -layout` y lista/repara el texto perdido. También
  como bandera del conversor: `pdf_chapters_to_markdown.py plan.json --verify`.
- **Auditoría de un LIBRO entero (escaneo OCR-eado y troceado):**
  `audit_conversion.py spec.json --out INFORME.md --sample 40 --render-dir ./pngs`.
  Un informe por libro con 4 capas, separando lo **demostrable** de lo **estimable**:
  [A] completitud determinista (ratio md/PDF por sección, lagunas, **balance de
  notas `[^N]`**: refs↔defs, cero huérfanas), [B] ruido OCR por diccionario (cota
  superior, aísla *garbage*), [C] renderiza N páginas para leerlas **contra la
  imagen** (única capa que ancla la verdad del OCR), [D] contraste con un 2º motor
  (tesseract sistema vs best) para señalar dónde MIRAR. **Nota clave aprendida:** el
  contraste debe OCR-ear ambos motores por `tesseract stdout` al MISMO dpi; comparar
  la capa `-layout` del PDF contra `tesseract stdout` mide orden de lectura, no
  errores, e infla el %. La discrepancia se concentra siempre en índice/bibliografía
  a 2 columnas (límite conocido), no en la prosa.
- Corrupción OUP/Distiller (ligaduras y diacríticos, parecen erratas pero son
  texto roto): `fix_ligatures.py` (fi→W… con guarda de diccionario y protección de
  nombres propios CamelCase), `fix_diacritics.py` (ı/€/acentos + NFC),
  `clean_openings.py` (portadillas/capitulares). Todo de una vez con
  `limpiar_academico.py ./markdown` (`--no-openings` para notas/índice).
- Back-matter a 2 columnas roto por el bisturí → Docling + `docling_clean.py`.
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
- Skills de QA: **`/qa-conversion`** (markdown vs PDF) antes de traducir;
  **`/qa-traduccion`** (incluye detección de truncamiento por ratio de palabras)
  después.

### 3b. Elegir bisturí PDF
| Situación | Script |
|---|---|
| **Cursiva significativa** o **2 columnas paralelas** original/traducción | `pdf_rich_to_markdown.py` (ver recuadro arriba) |
| **PDF de Acrobat ClearScan** (`pdfinfo` dice «Paper Capture … ClearScan») | `clearscan_to_markdown.py` (ver recuadro abajo) |
| **PDF digital cuya capa de texto está INCOMPLETA**: se pierden las llamadas de nota, los puntos suscritos o los dígitos | `pdfxml_to_markdown.py` (ver recuadro abajo) |
| Carpeta de **un PDF por capítulo**, notas a pie | `pdf_chapters_to_markdown.py plan.json` |
| **Un PDF digital limpio** (Calibre, con outline) | `detect_chapters.py` → `plan.json` → `pdf_sections_to_markdown.py plan.json` |
| Libro **escaneado ya OCR-eado** con citas Harvard | `pdf_book_to_markdown.py` |
| `pdftotext` **no extrae nada** pero tienes sidecar `.txt` de OCR | `ocr_text_to_markdown.py` |
| Solo **partir** el PDF en PDFs por capítulo | `detect_chapters.py` → `plan.json` → `split_pdf.py` |

> **PDF hecho con Acrobat ClearScan** → `clearscan_to_markdown.py`, NO `pdftotext` ni
> Docling. ClearScan no deja el OCR como capa invisible: **sustituye el texto por fuentes
> sintéticas** (`Fd<n>-Identity-H`), una por «racimo de formas». El texto se extrae bien,
> pero **la cursiva se pierde EN SILENCIO**, y en una edición académica es información
> (términos, transliteraciones, títulos, y a veces los propios subapartados). Ninguna vía
> normal la ve: `pdffonts` no da ningún nombre con «italic», `pdftohtml -xml` emite **0**
> marcas `<i>`, y el `/FontDescriptor` **miente** (`ItalicAngle` 0 y `Flags` idéntico en
> las 384 fuentes). Lo que sí es verdad son los CONTORNOS: el script mide la inclinación
> real de cada fuente embebida y decide redonda vs. cursiva. Medido en *The Search of the
> Heart* (Dykes, 239 pp): bimodal limpio —92.8 % redonda, 4.9 % cursiva, 2.3 % zona gris
> que resultaron ser los titulillos en versalita cursiva—, validado contra la imagen.
> Detección: `pdfinfo` → `Producer: … Paper Capture … ClearScan`.
>
> **Dos trampas medidas al escribirlo:** (1) los `fontspec` de `pdftohtml -xml` son
> GLOBALES y se declaran donde aparecen por primera vez —un mapa por página deja el 40 %
> del texto sin estilo—; (2) para rehacer párrafos hay que usar la sangría **relativa a la
> línea siguiente**, no la absoluta: los párrafos en BLOQUE (citas, párrafos numerados
> `[3]`) tienen todas sus líneas metidas y con un umbral absoluto se parten una a una.

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

> **MAQUETA SIN RENGLÓN EN BLANCO ENTRE PÁRRAFOS** (composición erudita: Brill y
> similares solo sangran la primera línea) → `pdf_rich_to_markdown.py --indent-paragraphs`.
> Sin ella el capítulo sale como UN párrafo gigante —el bisturí solo parte por salto
> vertical— y, peor, **las citas en bloque quedan sepultadas dentro y `pdf_blocks.py` ya
> no puede recuperarlas**. La sangría se mide **relativa a la línea SIGUIENTE, no en
> absoluto**: en una cita en bloque TODAS las líneas van metidas y un umbral absoluto la
> partiría renglón a renglón. Medido en Lehrich: 25 párrafos → 52, mismas palabras.
> **Y el ORDEN de la receta importa:** bisturí → promover el título de capítulo →
> `pdf_blocks` → quitar titulillos. Si se quitan los titulillos antes, el emparejamiento
> contra el PDF falla; si no se promueve el título antes, el epígrafe se detecta como
> cita y **se traga el encabezado del capítulo**.

> **PDF DIGITAL con la capa de texto INCOMPLETA** (nativo, `pdftotext` da prosa legible,
> pero faltan cosas que NADIE ve) → `pdfxml_to_markdown.py`. Medido en Attrell & Porreca,
> *Picatrix* (Penn State, 2019). Tres pérdidas simultáneas y todas silenciosas:
> (1) **las llamadas de nota desaparecen** —los volados van en una fuente sin `ToUnicode`
> y se extraen como cadena vacía o PUA: en el texto solo queda un doble espacio, y el
> aparato entero (95 notas) se evapora sin que el ratio ni el balance lo delaten—;
> (2) **el punto suscrito de las transliteraciones** se compone con una fuente aparte
> (`…DotUnder…`), así que `al-Qurṭubī` sale `al-Qurtubī` —una errata invisible—; y
> (3) **los dígitos elzevirianos** (tablas, cifras) son glifos PUA que ni `pdftotext` ni
> `mutool` extraen: la tabla conserva los rótulos y PIERDE los números.
> **Cómo se resuelve:** `pdftohtml -xml` da posición + familia + tamaño por palabra en
> 0,4 s (pdfminer tarda MINUTOS por página con fuentes Type 3). La familia dice qué lleva
> punto suscrito; el volado se reconoce por la **LÍNEA BASE ALZADA** —no por el tamaño,
> porque los dígitos elzevirianos también son bajos (260 glifos pequeños frente a 77
> volados reales)— y se CUENTA, como en un escaneo. Los glifos PUA de los dígitos se
> deducen comparando UNA tabla con su imagen y se pasan con `--charmap "U+F63A=2,…"`;
> entonces la llamada además se puede LEER, lo que da un **cotejo de dos señales
> independientes** (contada vs. impresa) que destapa cualquier desfase.
> **Trampas medidas:** los `<fontspec>` son GLOBALES (declararlos por página deja 33 de 34
> sin estilo); un volado de dos cifras son DOS glifos contiguos (sin agrupar, sales al
> doble de notas); `pdftohtml` no emite token de espacio entre palabras —el espacio se
> deduce del HUECO, y sin eso al cerrar una cursiva las palabras se pegan
> (`*Picatrix*stand`)—; y el aparato de final de libro reinicia en «1.», así que si no
> cortas ahí las notas de la sección siguiente se cuelan dentro de la última definición.
> **Límite honesto:** las tablas SIMPLES salen bien (`--tables`), las de encabezado
> apilado quedan aproximadas; y cada fuente de versalitas tiene SU propio mapeo corrupto,
> así que un `--charmap` global de una sola letra puede estropear otra fuente: mapea
> cadenas enteras (`Å±ÆÁÂ=TABLE`) y verifica contra la imagen.

`detect_chapters.py` lista páginas candidatas (no escribe el plan); con eso
**redactas el `plan.json`** y corres el conversor con `--dry-run` primero.

**Sondas de tipografía** (no convierten; te dicen qué hay antes de elegir):
`pdf_headings.py x.pdf` lista los tamaños de fuente y qué líneas serían encabezado;
`pdf_blocks.py x.pdf` vuelca los bloques con su fuente/tamaño/posición. Úsalas cuando
dudes de si un título es título o de dónde está el corte de columna.

### EPUB
```bash
python3 $T/build_plan.py "libro.epub" > plan.json   # spine + TOC (genérico)
python3 $T/epub_to_markdown.py plan.json --dry-run && python3 $T/epub_to_markdown.py plan.json
```
> **Pool de notas al final del libro → `footnotes_redistribute.py libro.md --apply`
> ANTES de trocear.** Si las definiciones `[^N]:` viven todas juntas al final, al
> partir por capítulos se van ENTERAS al último archivo y los demás quedan con las
> llamadas huérfanas. Las reparte al capítulo donde está su primera llamada; las que
> no tengan llamada se conservan y se reportan, nunca se borran.
EPUB muy ilustrado → `epub_illustrated_to_markdown.py`.

> **EPUB DE CALIBRE/KINDLE: LA CURSIVA SE PIERDE ENTERA Y EN SILENCIO.** Estos EPUB
> **casi nunca usan `<i>`/`<em>`**: el énfasis va en una CLASE
> (`<span class="italic">`, o una opaca `<span class="calibre12">` cuya regla es
> `font-style: italic`). Un conversor que solo mire etiquetas saca el texto entero
> —el ratio da 0.99 y el balance de notas cuadra— con **cero cursivas**, y en una
> edición académica la cursiva ES información: títulos de obra, transliteraciones,
> tecnicismos. La señal está en el CSS del propio libro, así que `epub_to_markdown.py`
> lo lee (`styles_from_css`) y deriva qué clases son cursiva/negrita: general, no una
> lista de nombres por libro. **Compruébalo en un segundo:**
> `unzip -p x.epub '*.css' | grep -c font-style` frente a
> `grep -c '<i>\|<em>' *.html`. Medido en *Astral High Magic* (Warnock): 94 `<span
> class="italic">` y **0** `<i>`; con el arreglo, 157 cursivas recuperadas.
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
