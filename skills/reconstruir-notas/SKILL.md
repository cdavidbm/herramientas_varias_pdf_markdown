---
name: reconstruir-notas
description: Reconstruye el aparato de NOTAS AL PIE de un libro escaneado cuyo OCR corrompió los marcadores (y a menudo el griego), y cuyo bisturí perdió o entremezcló el texto de las notas. Un agente por capítulo lee el markdown + el PDF (verdad del pie de página) y rehace las [^N] enlazadas, recupera notas perdidas y normaliza el griego. Activa con "/reconstruir-notas" o intención como "reconstruye las notas de este libro", "las notas al pie quedaron rotas/perdidas", "arregla el aparato de notas".
---

# Reconstruir aparato de notas (suite La Forja)

Para libros **escaneados y muy cargados de notas al pie** donde el OCR (ABBYY,
Internet Archive, etc.) **destrozó los marcadores** (10→"')", 11→"u", volados→símbolos)
y a menudo el **griego**, y donde el bisturí de conversión **perdió, partió o
entremezcló** el texto de las notas con el cuerpo. Probado en Hadot, Elliott, Dodds.

## Cuándo se activa

- Explícito: `/reconstruir-notas`.
- Intención: "las notas al pie salieron rotas/perdidas", "reenlaza las [^N]",
  "arregla el aparato de notas de este libro".
- Señal diagnóstica: tras convertir con un bisturí, el capítulo tiene **muchísimas
  menos** `[^N]` de las que el libro tiene notas (p. ej. el bisturí reconstruyó 5 en
  un capítulo de 40 páginas), y/o `check_completeness` marca texto de nota perdido.

## Requisitos previos

1. El markdown ya convertido (un `.md` por capítulo, cuerpo limpio) en `./markdown/`.
2. El **PDF fuente de cada capítulo** (o el libro con el rango de páginas): es la
   VERDAD de las notas. Las notas al pie se leen con `pdftotext -layout "cap.pdf" -`
   (aparecen al fondo de cada página).
3. Haz primero la limpieza estructural (running-heads, guion de corte, bloque de
   título redundante) — ver [[forja]] §3c. Las notas se reconstruyen sobre el cuerpo
   ya limpio.

## Procedimiento

**Un agente por capítulo, en paralelo** (los libros son largos; cada capítulo es
independiente). A cada agente dale el `.md` del capítulo, su PDF, y este encargo
(plantilla — ajusta idioma/detalles del daño y si hay griego/latín):

> Eres editor de un libro académico escaneado con OCR. Reconstruye el APARATO DE
> NOTAS AL PIE de UN capítulo. NO traduzcas ni reescribas la prosa del cuerpo.
> ARCHIVOS: markdown a corregir «…/markdown/NN_cap.md»; PDF fuente (VERDAD de las
> notas) «…/cap.pdf».
> CONTEXTO: las notas van AL PIE DE CADA PÁGINA — míralas con `pdftotext -layout
> "<PDF>" -`. El OCR corrompió los marcadores numéricos (10→"')", 11→"u", *) y (si
> aplica) el griego. El bisturí perdió/partió parte del texto de notas: recupéralo
> del PDF. Numeración por capítulo (1..N) salvo que el libro numere de otro modo.
> TAREA: (1) extrae del `-layout` TODAS las notas en orden (une líneas envueltas;
> ignora encabezados de página y números sueltos). (2) Sección final `## Notas`: una
> `[^n]:` por nota, 1..N en orden, texto completo; corrige erratas OBVIAS de OCR;
> el griego/latín transcríbelo lo mejor posible y si un tramo es irrecuperable pon
> `[griego ilegible]` (NO lo inventes). (3) En el CUERPO enlaza `[^n]` donde el
> marcador sea identificable (volado OCR-eado pegado a palabra); NO enlaces
> fechas/cifras/loci clásicos (p. ej. "Rep., 476 C", años); si un marcador es
> irrecuperable, deja la nota definida sin ancla. (4) PRESERVA la prosa: solo añade
> `[^n]` y mueve a su `[^n]:` el texto de nota que el bisturí incrustó en el cuerpo.
> Informe: N notas; marcadores enlazados; notas recuperadas; tramos ilegibles.

## Verificación (tras los agentes)

Comprueba paridad y contigüidad por capítulo:

```bash
python3 - <<'PY'
import re, glob
for f in sorted(glob.glob("markdown/*.md")):
    t=open(f,encoding='utf-8').read()
    refs=[int(x) for x in re.findall(r'(?<!\])\[\^(\d+)\](?!:)',t)]
    defs=[int(x) for x in re.findall(r'^\[\^(\d+)\]:',t,re.M)]
    rs,ds=set(refs),set(defs); N=max(ds) if ds else 0
    ok = rs<=ds and ds==set(range(1,N+1)) and len(defs)==len(ds)
    print(f"  {'OK' if ok else '‼️'} {f} N={N} refs={len(refs)} defs={len(defs)}"
          + ("" if ok else f"  defs sin ancla={sorted(ds-rs)[:8]}"))
PY
```

Es **normal y correcto** que unas pocas notas queden definidas sin ancla en el
cuerpo (marcador volado irrecuperable): mejor eso que inventar la posición. Cuenta
los tramos `[griego ilegible]` y avísale al usuario para cotejo manual contra la
imagen. `check_completeness` dará falsos positivos porque los agentes CORRIGEN el
OCR (el texto ya no casa con el `-layout` crudo); fíate de la paridad + de que las
notas antes perdidas ya aparezcan (grep de un autor/obra que faltaba).

## Límite honesto

El agente reconstruye contra lo que el OCR dejó legible. En escaneos con griego muy
degradado quedan tramos `[ilegible]`: pertenecen al **re-OCR selectivo del griego**
(otra herramienta), no a esta. Esta skill garantiza aparato **completo, numerado y
en su mayoría enlazado**; la fidelidad carácter-a-carácter del griego es otra pasada.

Relacionado: [[forja]], [[qa-conversion]], [[ocr]].
