---
name: traducir-md
description: Traduce markdown de libros (capítulo por capítulo) preservando notas al pie [^N], encabezados, tablas y formato, con glosario de términos consistente. Activa con "/traducir-md" o intención como "tradúceme este capítulo al español", "traduce esta carpeta de markdown al inglés".
---

# Traducir Markdown (suite La Forja)

Traduce documentos markdown producidos por la suite **La Forja** (un `.md` por
capítulo, con notas al pie resueltas como `[^N]`) a otro idioma, **conservando
intacta la estructura** y manteniendo **consistencia terminológica** entre
capítulos. Pensado para textos académicos/ensayísticos (astrología, alquimia,
filosofía) donde el registro y los términos clave importan.

## Cuándo se activa

- Invocación explícita: `/traducir-md`
- Intención: "traduce este capítulo al español", "pásame esta carpeta de
  markdown al inglés", "traduce el libro manteniendo las notas".

## Entradas

- **Archivo(s):** uno o varios `.md` (típicamente `./markdown/*.md`).
- **Idioma destino:** pregúntalo si no está claro. Por defecto, español neutro.
- **Idioma origen:** autodetéctalo.

## Reglas de preservación (CRÍTICAS — no romper la estructura)

Traduce SOLO el texto en prosa. Deja **literalmente intactos**:

1. **Marcadores de nota** `[^N]` en el cuerpo — mismo número, misma posición
   relativa en la frase traducida.
2. **Definiciones de nota** `[^N]: ...` — traduce el texto de la nota, pero
   conserva el `[^N]:` y el orden.
3. **Encabezados** `#`, `##`, … — mismo nivel; traduce solo el texto.
4. **Bloques de código** ` ``` ` y código en línea `` `...` `` — sin tocar.
5. **Enlaces e imágenes** `[texto](url)` / `![alt](url)` — traduce el texto/alt
   visible, NUNCA la URL.
6. **Tablas** — conserva la sintaxis `|`/`---`; traduce solo el contenido.
7. **Citas** `>` , listas, énfasis `*`/`_`/`**` — conserva el marcado.
8. **Matemáticas/LaTeX** `$...$`, `$$...$$` — sin tocar.
9. **Claves de cita** estilo Harvard/autor-año (p. ej. `(Smith 2001: 23)`) y
   **nombres propios** — no traducir salvo exónimos consagrados
   (p. ej. *Ptolemy → Tolomeo* si el destino es español y es lo convencional).

## Glosario (consistencia entre capítulos)

1. Antes de traducir, busca un `glosario.md` en la carpeta del libro (junto a
   `./markdown/`). Si existe, **respeta esas equivalencias** sin excepción.
2. Si no existe, créalo: a medida que fijes la traducción de términos técnicos
   recurrentes (p. ej. *triplicity → triplicidad*, *sect → secta*,
   *prime matter → materia prima*), regístralos en `glosario.md` como tabla
   `| origen | destino | nota |`.
3. Al traducir capítulos siguientes, **relee el glosario primero** para mantener
   la misma elección en todo el libro.
4. Si un término del glosario te parece mal, NO lo cambies en silencio:
   propónlo al usuario y actualiza el glosario solo con su visto bueno.

## POLÍTICA FIRME: cómo traducir con agy/Gemini (no negociable)

> El usuario lleva MUCHAS sesiones observando el mismo patrón. Tú solo recuerdas la
> tuya, así que **no lo re-evalúes: aplícalo.**

- **Archivo de más de ~4.000 palabras → `agy_retranslate_chunks.py`, de entrada.**
  Verifica CADA trozo nada más traducirlo (ratio + sus `[^N]`), reintenta solo el que
  falla y lo parte en dos si insiste.
- **Archivo corto → `agy_translate.py`** basta (verifica al final).
- **Por qué:** cuanto más larga es la entrada, más tiende agy a **RESUMIR en vez de
  traducir**. Y lo hace en silencio: puede **saltarse párrafos enteros de prosa dejando
  el aparato de notas cuadrado**, de modo que el balance `[^N]` da el visto bueno y
  **solo el ratio de palabras delata la pérdida** (medido: 21/21 notas correctas y 1.200
  palabras ausentes). `agy_translate.py` solo verifica el archivo entero al final, así
  que cuando lo detecta ya no hay reparación barata: relanzarlo completo vuelve a fallar.
- **Para localizar el texto perdido**, compara el volumen de texto ENTRE llamadas
  consecutivas: las `[^N]` son idénticas en ambos idiomas, así que parten los dos textos
  por los mismos puntos y el tramo con déficit salta a la vista.
- **Al informar, di cuántos archivos pasaron LIMPIOS, no solo cuántos fallaron.** Contar
  solo los fallos da la impresión falsa de que agy falla siempre; es sesgo del informe.

## Procedimiento

1. Confirma idioma destino y localiza el/los archivo(s).
2. Lee `glosario.md` (o prepárate para crearlo).
3. Traduce **un capítulo a la vez** (los libros son largos): lee el `.md`,
   traduce respetando TODAS las reglas de preservación, escribe el resultado.
4. **Salida:** por defecto `nombre.<lang>.md` junto al original
   (p. ej. `cap-03.es.md`), o una carpeta `./traduccion/` si el usuario prefiere
   no mezclar. Nunca sobrescribas el original.
5. Tras cada capítulo, actualiza `glosario.md` con los términos nuevos fijados.
6. Al final, reporta: capítulos traducidos, términos añadidos al glosario y
   cualquier pasaje dudoso que convenga revisar a mano.

## Registro y tono

- Mantén el **registro** del original (académico ↔ académico; no lo simplifiques).
- Respeta cursivas de términos técnicos y transliteraciones (griego, árabe).
- Ante ambigüedad real de sentido, traduce lo más fiel y deja una nota de
  traductor `[^t1]` SOLO si el usuario lo pide; por defecto no inventes notas.

## Verificación rápida (antes de entregar)

- ¿El número de `[^N]` en el cuerpo coincide con el número de definiciones
  `[^N]:`? (mismo conteo que el original).
- ¿Se conservaron todos los niveles de encabezado?
- ¿Ninguna URL ni bloque de código fue alterado?
- **¿El ratio de palabras ES/EN está en ~1.0?** Un ratio bajo es la ÚNICA señal de que
  agy se saltó prosa: el balance de notas puede cuadrar perfectamente y faltar texto.
- **¿Hay encabezados REPETIDOS?** Es la firma de que agy reemitió un trozo; el ratio no
  la detecta.
- **¿Algún párrafo se quedó sin traducir?** Mídelo por párrafo (palabras funcionales
  inglesas), no en el conjunto: en global se diluye y no se ve.
