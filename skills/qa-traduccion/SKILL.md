---
name: qa-traduccion
description: Control de calidad de una traducción markdown contra su original. Verifica que la estructura se preservó (notas [^N], encabezados, enlaces, nada sin traducir) y revisa consistencia terminológica y de registro. Activa con "/qa-traduccion" o intención como "revisa esta traducción", "verifica que el capítulo traducido quedó bien", "controla la calidad de la traducción".
---

# QA de Traducción (suite La Forja)

Verifica una traducción markdown contra su original, en dos capas: **mecánica**
(estructura preservada, la hace un script) y **de criterio** (consistencia,
registro, fidelidad, la haces tú). Complementa a [[traducir-md]]: tradúcelo,
luego pásale esta QA antes de la revisión humana final.

## Cuándo se activa

- Explícito: `/qa-traduccion`
- Intención: "revisa/verifica esta traducción", "controla la calidad del
  capítulo traducido".

## Entradas

- El `.md` **original** y el `.md` **traducido** (capítulo a capítulo).
- Opcional: `glosario.md` del libro (tabla `| origen | destino | nota |`).

## Capa 1 — Chequeos mecánicos (script, deterministas)

Ejecuta el script incluido por cada par de archivos:

```bash
python3 ~/.claude/skills/qa-traduccion/check_translation.py \
    original.md traducido.md --glosario glosario.md
```

Detecta y reporta:
- **Truncamiento:** el ratio de palabras traducido/original (🔴 si < 0.85). Es el
  fallo más traicionero al traducir capítulos largos: el modelo se corta a mitad y
  el `.md` sale incompleto. El español suele dar ~1.0–1.15; un ratio bajo casi
  siempre es truncamiento u omisión. Verás también la última frase para cotejar
  con el final del original.
- **Notas al pie:** que el conjunto de `[^N]` del cuerpo coincida con el original
  y que cada cita tenga su definición `[^N]:` (🔴 si se rompe).
- **Encabezados:** mismo número y misma jerarquía de niveles.
- **Enlaces/imágenes/código:** que las URLs y bloques se conserven idénticos.
- **Sin traducir:** párrafos idénticos al original (posible olvido).
- **Glosario:** términos del idioma origen que quedaron sueltos en la traducción.

Sale con código 1 si hay PROBLEMAS estructurales (🔴); 0 si solo avisos o limpio.
Para un libro entero, recórrelo en bucle por capítulo y resume al final.

## Capa 2 — Revisión de criterio (la haces tú leyendo)

El script no juzga sentido. Tras pasarlo, revisa:
1. **Consistencia terminológica:** los términos clave se tradujeron igual en todo
   el capítulo y conforme al `glosario.md`. Si fijaste un término nuevo,
   regístralo en el glosario.
2. **Registro:** se mantuvo el tono académico del original; no se simplificó.
3. **Fidelidad:** no hay omisiones ni añadidos; las transliteraciones (griego,
   árabe) y cursivas técnicas se conservaron.
4. **Naturalidad:** la prosa fluye en el idioma destino sin calcos forzados.
5. **Falsos amigos / números / nombres propios:** revisados.

## Salida

Un **informe breve** por capítulo: 🔴 problemas a corregir, 🟡 dudas a mirar,
🟢 lo que pasó limpio. Si el usuario lo pide, aplica las correcciones al `.md`
traducido (nunca toques el original). Cierra recomendando si está listo para
revisión humana o necesita otra pasada.

## Nota

Esta QA es un colador mecánico + lectura crítica, **no** sustituye tu revisión
final como autor/traductor: la atrapa lo evidente para que tú te concentres en
los matices.
