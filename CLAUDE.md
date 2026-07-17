# CLAUDE.md — Manual de operación de La Forja (para el agente)

Este repo es un **taller de conversión de libros a markdown por capítulo**,
pensado para que **lo opere Claude**, no la persona usuaria. El usuario pide un
resultado ("pasa este libro a markdown", "prepáralo para NotebookLM") y **tú
diagnosticas el documento y eliges la herramienta correcta tú mismo**.

> También existe la skill global **`/forja`** con este mismo algoritmo. Este
> archivo lo replica para que el repo sea autoexplicativo aunque se use en otra
> máquina o sin la skill cargada.

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

> **Escaneo largo o equipo que se puede cerrar:** usa
> `python3 $T/docling_incremental.py x.pdf --out ./markdown` — procesa por lotes
> de páginas con **checkpoint + resume + progreso** (no pierde el trabajo si se
> corta). Si el PDF ya trae capa de texto (ABBYY/nativo digital), añade `--no-ocr`
> (acelera mucho). `--image-export-mode placeholder` evita incrustar imágenes.

### 3c. Limpieza post-conversión (OCR/Docling → estudio)
Tras convertir, dejar el markdown listo para leer/traducir:
- `clean_markdown.py` — quita running-headers de página (sin borrar contenido
  repetido legítimo), guion suave, saca imágenes base64 a archivo, normaliza espacios.
- `split_chapters.py libro.md --plan plan.json` (o `--by-heading 2`) — trocea en
  capítulos. Exige UNA de las dos banderas; el `.md` va siempre como posicional.
- `footnotes_rebuild.py cap.md --apply` — reconstruye notas `[^N]` **por capítulo**.
  Detecta 2 estilos de OCR: *pegado* (marcador partido `1 3 8`→`[^138]` + def. `114. …`)
  y *suelto* (marcador ` N ` con espacio + def. `N Texto` sin punto, incluso partida en
  dos líneas; numeración continua en todo el libro; libros AstroArt/Döser). NO en
  índices/bibliografía. Para rehacer un archivo ya convertido: revierte con regex
  (`^\[\^N\]:`→`N `, `\s*\[\^N\]`→` N`) y reaplica.
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
| Carpeta de **un PDF por capítulo**, notas a pie | `pdf_chapters_to_markdown.py plan.json` |
| **Un PDF digital limpio** (Calibre, con outline) | `detect_chapters.py` → `plan.json` → `pdf_sections_to_markdown.py plan.json` |
| Libro **escaneado ya OCR-eado** con citas Harvard | `pdf_book_to_markdown.py` |
| `pdftotext` **no extrae nada** pero tienes sidecar `.txt` de OCR | `ocr_text_to_markdown.py` |
| Solo **partir** el PDF en PDFs por capítulo | `detect_chapters.py` → `plan.json` → `split_pdf.py` |

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
EPUB muy ilustrado → `epub_illustrated_to_markdown.py`.

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
- Entregar un capítulo suelto en otro formato: `pandoc cap.md -o cap.epub|.docx`.
- **Libro fuente en LaTeX** (ediciones tipo janegca de Valens y clásicos helenísticos)
  → `python3 $T/latex_to_markdown.py maestro.tex --root ./src --out libro.md`.
  Expande los `\input`, mapea starfont/wasysym a Unicode (`\Saturn`→♄) y pasa por pandoc.

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

## Herramientas disponibles en el equipo
Scripts del repo · `pandoc` · `ocrmypdf` · `tesseract` · poppler (`pdfinfo`,
`pdftotext`, `pdfimages`) · `mutool` · **`docling`** (PDF complejos) ·
**`markitdown`** (Office/html/imágenes) · **`yt-dlp`** + `ffmpeg` (YouTube) ·
**`faster-whisper`** (ASR local, venv). Sin claves de API.

Detalles finos de cada script (manejo de notas por formato, límites): ver
`README.md` y `tools/README.md`.
