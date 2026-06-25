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
