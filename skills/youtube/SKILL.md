---
name: youtube
description: Trabaja con YouTube usando yt-dlp — descarga video, audio y subtítulos, y sobre todo convierte un video en un markdown de estudio de alta calidad a partir de sus subtítulos (incluidos los AUTO-GENERADOS): sin marcas de tiempo, con ortografía corregida, buena puntuación y párrafos bien escritos, sin resumir ni recortar nada. Si el video NO tiene subtítulos, transcribe el audio con ASR local (faster-whisper). Maneja videos ocultos/no listados y, con cookies, privados o con login. Activa con "/youtube" o intención como "pásame este video a markdown", "saca los subtítulos de este video", "transcribe este video de YouTube", "transcribe el audio de este video sin subtítulos", "baja el audio/video", "extrae el material de este video".
---

# YouTube → material de estudio (suite La Forja)

Extrae el contenido de un video de YouTube y lo entrega como **markdown limpio
de calidad editorial**, listo para estudiar, indexar ([[explorar-libro]]),
traducir ([[traducir-md]]) o subir a NotebookLM ([[notebooklm]]). La fuente
preferida son los **subtítulos** —incluidos los **auto-generados** de YouTube—
porque dan el texto íntegro sin transcribir audio.

## PRINCIPIO RECTOR — la herramienta la opera el agente

El usuario pide un resultado ("pásame este video a markdown", "saca los
subtítulos"); **tú sondeas el video y decides la ruta**. No le preguntes lo
inferible (si tiene subs manuales o auto, en qué idiomas, si tiene capítulos:
se detecta). Pregunta SOLO lo que cambia el resultado y no puedes inferir:
**idioma** si hay varios y no está claro cuál quiere, o si además quiere
**traducirlo**.

**Toolbox:** `/mnt/c/ideas/_La_Forja/tools/`. Define `T=/mnt/c/ideas/_La_Forja/tools`.
Si esa ruta no existe (repo clonado en otra máquina), usa la ruta real del clon:
desde la raíz del repo, `T=tools`.

Tres scripts:
- `yt_transcript.py` — URL → texto limpio, **sin timestamps y sin la
  duplicación de ventana rodante** de los auto-subtítulos. Es la pieza clave
  cuando el video TIENE subtítulos.
- `yt_audio_transcribe.py` — cuando **no hay subtítulos**: baja el audio y lo
  transcribe con ASR local (faster-whisper). Misma salida `.txt`/`.meta.json`.
- `yt_media.py` — descargas con yt-dlp (audio, video, archivos de subtítulos,
  miniatura, descripción) y metadatos.

Las tres aceptan `--cookies archivo.txt` / `--cookies-from-browser NAV` para
videos privados o con login (ver sección de videos ocultos/privados).

---

## FLUJO PRINCIPAL: video → markdown de estudio

### Paso 1 · Sondea el video

```bash
python3 $T/yt_transcript.py "URL" --list
```

Te dice: título, canal, duración, **subtítulos manuales** disponibles,
**auto-generados** disponibles y **capítulos**. Con eso eliges idioma y sabes si
podrás poner encabezados por capítulo.

### Paso 2 · Saca el transcript limpio

Regla de preferencia (el script ya la aplica): **manual > auto**. Los subtítulos
manuales traen puntuación y mayúsculas; los auto-generados no (y hay que
restaurarlos tú en el paso 3).

```bash
# Idioma preferido; cae a auto si no hay manual en ese idioma:
python3 $T/yt_transcript.py "URL" --lang es -o ./yt

# Forzar auto-generados (p. ej. no hay manual, o los quieres en el idioma hablado):
python3 $T/yt_transcript.py "URL" --lang en --auto -o ./yt
```

Salida: `slug.txt` (texto limpio) + `slug.meta.json` (título, canal, url, fecha,
duración, **capítulos**, descripción, y `subtitle_kind`: manual/auto).

Si el video **no tiene subtítulos** de ningún tipo (`--list` muestra 0 y 0),
no hay texto que extraer: pasa a la **transcripción por audio (ASR)** del paso 2b.

### Paso 2b · Sin subtítulos → transcribe el audio (ASR local)

Cuando NO hay subtítulos (típico de clases largas, directos, canales pequeños),
el video se "lee" transcribiendo su audio con **faster-whisper** (local, sin
API). Requiere el venv de ASR una sola vez:

```bash
bash $T/asr_setup.sh             # asr_setup.sh vive en el propio tools/ ($T)
PY="$HOME/.local/share/forja-asr-venv/bin/python"
```

Transcribe (baja el audio y lo pasa por Whisper; misma salida `.txt` + `.meta.json`):

```bash
$PY $T/yt_audio_transcribe.py "URL" --lang es --model large-v3 -o ./yt
```

- **Prueba primero un tramo** en videos largos para calibrar idioma/calidad:
  `--start 20:00 --end 23:00`. Si convence, lanza el completo.
- **Modelo:** `large-v3` = máxima calidad (por defecto; prioriza calidad sobre
  velocidad, coherente con la regla del usuario). En CPU es lento: una clase de
  varias horas puede tardar **horas**. Avísale del tiempo y, si tiene prisa,
  ofrece `medium` (más rápido, algo menos fino). No bajes de `medium` para
  material de estudio salvo que lo pida.
- **Idioma:** fíjalo con `--lang` si lo conoces (evita que autodetecte mal en los
  primeros segundos de música).
- Whisper YA pone puntuación y mayúsculas, pero comete errores en **nombres
  propios y tecnicismos** (astrología, alquimia, autores, estrellas): el paso 3
  del agente los corrige con criterio (contexto del tema, glosario si existe).
- Trabajos muy largos: puedes lanzarlo en segundo plano y seguir. El `.txt`
  resultante entra igual al paso 3.

### Paso 3 · Redáctalo como markdown de calidad (LO HACE EL AGENTE)

El `.txt` es fiel pero crudo (sobre todo si viene de auto-subs: sin puntuación,
sin mayúsculas, sin párrafos, con errores de reconocimiento). **Tú** lo conviertes
en prosa legible. Esto es trabajo de juicio, no mecánico. Reglas:

1. **Fidelidad total — NUNCA resumas ni recortes.** Restaura la forma, no cambies
   el contenido. Cada idea, ejemplo y matiz del hablante se conserva. Está
   PROHIBIDO comprimir, parafrasear de más u omitir. Es una transcripción
   editada, no un resumen.
2. **Puntuación y mayúsculas.** Añade comas, puntos, signos de interrogación y
   mayúsculas de inicio de frase y nombres propios. En español, abre `¿` y `¡`.
3. **Párrafos.** Agrupa las frases en párrafos por unidad de sentido (cambio de
   idea/tema). Ni una sola línea kilométrica ni frases sueltas por renglón.
4. **Ortografía y errores de reconocimiento.** Corrige erratas obvias y palabras
   que el reconocimiento de voz oyó mal (términos técnicos, nombres). Si dudas
   entre dos lecturas plausibles, elige la coherente con el tema y, si es
   relevante, deja una nota `[?]` breve. No "mejores" el estilo del hablante ni
   le cambies el registro.
5. **Muletillas y ruido.** Puedes quitar tartamudeos y repeticiones involuntarias
   ("e-eh", "o sea o sea") y marcas como `[Music]`/`[Applause]` que no aportan.
   No elimines contenido real por considerarlo "de relleno".
6. **Encabezados por capítulo.** Si `meta.json` trae `chapters`, usa sus títulos
   como `##` para seccionar el texto en los puntos correspondientes (guíate por
   el sentido; los tiempos de los capítulos orientan el orden). Si no hay
   capítulos, crea secciones tú por cambios de tema, con títulos sobrios.
7. **Front matter.** Encabeza el `.md` con un H1 (título del video) y una ficha:

   ```markdown
   # <título del video>

   > **Canal:** <canal> · **Publicado:** <fecha> · **Duración:** <duración>
   > **Fuente:** <url>
   > **Transcripción:** subtítulos <manual|auto-generados> (<idioma>), editada.
   ```

8. **Números, siglas, citas.** Escribe cifras y unidades con criterio; expande
   siglas la primera vez si el contexto lo pide. Si el hablante cita a alguien o
   un libro, respeta el nombre.

**Trabaja por tramos si el video es largo** (una charla de 1 h son miles de
palabras): edita el texto por bloques sin saltarte nada, manteniendo coherencia
de términos entre tramos. Nunca "resumas para que quepa".

### Paso 4 · Salida y siguiente eslabón

Guarda `NN_slug.md` (o el nombre que encaje en la carpeta del usuario). Según lo
que quiera:
- **Traducir** → [[traducir-md]] (preserva encabezados y notas, glosario).
- **Corregir estilo** → [[revisar-prosa]].
- **Estudiar/indexar** con otros materiales → [[explorar-libro]].
- **NotebookLM** → el `.md` va directo como fuente ([[notebooklm]]).

---

## DESCARGAS (cuando piden el archivo, no el texto)

Usa `yt_media.py`. Soporta videos y playlists.

```bash
python3 $T/yt_media.py "URL" --info                 # metadatos (o --json para todo)
python3 $T/yt_media.py "URL" --audio                # bestaudio -> mp3 (necesita ffmpeg)
python3 $T/yt_media.py "URL" --audio --format m4a   # sin re-codificar
python3 $T/yt_media.py "URL" --video --quality 1080 # mp4 combinado
python3 $T/yt_media.py "URL" --subs --lang es       # archivos de subtítulos (manual+auto)
python3 $T/yt_media.py "URL" --thumbnail
python3 $T/yt_media.py "URL" --description          # descripción (con sus enlaces)
```

Añade `--dry-run` para ver el comando de yt-dlp sin ejecutarlo, `-o DIR` para la
carpeta, `--no-playlist` para bajar solo el video de una URL de lista.

---

## Videos "ocultos", privados o con restricción

Distingue dos casos (sondea con `--list` o `yt_media.py --info`):

1. **No listados / ocultos con enlace** — accesibles con la URL aunque no salgan
   en el canal. **yt-dlp los baja sin nada especial** (metadatos, audio, video).
   Si "no salen" es casi siempre porque **no tienen subtítulos** → usa ASR
   (paso 2b), no hace falta autenticación.
2. **Privados, de miembros, con login o restricción de edad** — yt-dlp da error
   de acceso. Aquí sí hacen falta **cookies** de una sesión donde el video se ve.
   Las tres herramientas aceptan:
   - `--cookies archivo.txt` — un `cookies.txt` (formato Netscape).
   - `--cookies-from-browser NAV` — lee cookies de un navegador del **mismo
     sistema** (firefox, chrome, chromium, brave, vivaldi, edge).

   **Importante en WSL:** `--cookies-from-browser vivaldi` **NO** sirve para la
   Vivaldi instalada en **Windows**: su base de cookies está bloqueada por el
   navegador y cifrada con DPAPI de Windows, que yt-dlp en Linux no puede
   descifrar (probado: da *Permission denied*). La vía fiable es **exportar un
   `cookies.txt`** desde Vivaldi con una extensión tipo *"Get cookies.txt
   LOCALLY"* (estando con sesión iniciada y viendo el video), guardarlo y pasarlo:

   ```bash
   python3 $T/yt_transcript.py "URL" --lang es --cookies /ruta/cookies.txt
   $PY $T/yt_audio_transcribe.py "URL" --lang es --cookies /ruta/cookies.txt
   ```

   (`--cookies-from-browser` sí funciona directo si algún día usas un navegador
   **dentro de** WSL/Linux.)

## Notas y límites

- **Idioma de los auto-subtítulos:** YouTube ofrece la pista original y muchas
  "traducciones" automáticas. Para máxima fidelidad prefiere la pista **original**
  del hablante (el script elige `-orig` cuando no pides idioma) y, si hace falta
  en otro idioma, traduce después con [[traducir-md]] en vez de fiarte de la
  traducción automática de YouTube.
- **Calidad de auto-subs:** el reconocimiento de voz falla en nombres propios,
  tecnicismos y homófonos. Por eso el paso 3 lo hace el agente, no un script.
- **`yt_transcript.py` también limpia archivos locales**: si ya tienes un `.vtt`
  o `.srt`, pásaselo directamente (sin red, sin yt-dlp).
- **Existe además el MCP `youtube`** (transcripciones rápidas) y `yt-dlp` directo;
  estos scripts son la vía con control fino sobre idioma, de-duplicación y
  metadatos para producir markdown de estudio.

## Requisitos

`yt-dlp` en el PATH (para URLs) y `ffmpeg` (para `--audio`/`--video` combinado
y para el ASR). Los instala `setup.sh`. La limpieza de un `.vtt/.srt` local no
necesita nada más que Python.

Para la **transcripción por audio (ASR)**: `bash tools/asr_setup.sh` crea el venv
`~/.local/share/forja-asr-venv` con **faster-whisper** (fuera de git). Los modelos
de Whisper se descargan solos la primera vez (`large-v3` ≈ 3 GB, caché en
`~/.cache/huggingface`).
