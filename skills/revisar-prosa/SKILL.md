---
name: revisar-prosa
description: Pasada de corrector editorial sobre un manuscrito markdown (textos propios o traducciones). Revisa consistencia de terminología y nombres propios, registro uniforme, repeticiones, gramática y erratas, sin alterar el sentido ni la voz del autor. Activa con "/revisar-prosa" o intención como "corrige el estilo de este capítulo", "revisa este texto como editor", "dale una pasada de copyedición".
---

# Revisar Prosa — corrector editorial

Hace de **copyeditor** sobre markdown académico/ensayístico (astrología,
alquimia, filosofía): pule consistencia, gramática y erratas **respetando la voz
del autor y sin cambiar el sentido**. Sirve para tus textos propios y para
traducciones ya pasadas por [[qa-traduccion]].

## Cuándo se activa

- Explícito: `/revisar-prosa`
- Intención: "corrige el estilo", "revísalo como editor", "pasada de copyedición".

## Principio

Corregir, **no reescribir**. No impongas tu estilo: respeta el registro y la voz.
Cambios mínimos y justificados. Ante una elección estilística válida del autor,
**no la toques** (o coméntala, no la cambies).

## Qué revisar

1. **Consistencia terminológica:** un mismo concepto, siempre el mismo término.
   Señala variantes (p. ej. "regente" vs "señor" del signo si se usan como
   sinónimos sin querer). Si existe `glosario.md`, respétalo.
2. **Nombres propios y transliteraciones:** misma grafía siempre
   (p. ej. *Tolomeo* / *Ptolomeo*, *al-Bīrūnī*), acentos y cursivas uniformes.
3. **Registro y tono:** académico parejo; sin coloquialismos sueltos ni saltos
   de formalidad.
4. **Gramática y sintaxis:** concordancia, tiempos verbales, preposiciones,
   puntuación (incluida la de citas y comillas — « » vs " " consistente).
5. **Repeticiones y muletillas:** palabras o conectores repetidos muy cerca;
   propón variación solo si mejora sin forzar.
6. **Erratas y tipografía:** dobles espacios, guion/raya (-, –, —), comillas
   rectas vs tipográficas, números y unidades.
7. **Estructura markdown intacta:** NO toques `[^N]`, encabezados, enlaces,
   tablas ni bloques de código.

## Capa mecánica primero (script, exhaustivo)

Antes de la lectura crítica, corre el script incluido — atrapa lo tipográfico de
forma exhaustiva (no se le escapa ninguno) y te deja libre para el criterio:

```bash
python3 ~/.claude/skills/revisar-prosa/proofread.py capitulo.md [mas.md ...]
```

Reporta `archivo:línea` para: dobles espacios, espacio final, espacio antes de
puntuación, comillas rectas, `...` vs `…`, guion suelto ` - ` (¿raya?), espacio
antes de `[^N]`, `¿`/`¡` sin cierre, palabras repetidas consecutivas y bloques de
líneas en blanco. NO modifica el archivo. Incluye estos hallazgos en tu informe.

## Modo de trabajo (elige con el usuario)

- **Informe primero (por defecto):** entrega una lista de hallazgos agrupados por
  tipo, con `archivo:línea`, el texto actual y la corrección propuesta. El
  usuario aprueba y luego aplicas.
- **Aplicar directo:** si el usuario lo pide, corrige sobre el `.md` y entrega un
  resumen de los cambios hechos (para que pueda revisarlos con `git diff` si el
  texto está versionado).

## Salida

Hallazgos agrupados (consistencia · gramática · tipografía · repeticiones), con
ubicación y propuesta. Marca como **duda** (no como error) lo que sea elección
estilística legítima. Cierra con un veredicto: ¿listo, o requiere otra pasada?

## Límite honesto

Es una pasada de consistencia y corrección, no una edición de fondo (estructura
argumental, ritmo). Si detectas problemas de fondo, señálalos aparte pero no los
"arregles" por tu cuenta.
