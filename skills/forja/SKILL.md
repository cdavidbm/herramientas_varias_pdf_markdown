---
name: forja
description: Trabaja con LIBROS y DOCUMENTOS de principio a fin — convertir PDF/EPUB/RTF/DjVu/Office a markdown limpio por capítulo, hacer OCR de escaneos malos, reconstruir el aparato de notas al pie, traducir capítulo a capítulo con glosario, verificar que no se perdió texto, corregir la prosa, gestionar citas y bibliografía, explorar un libro por tema y maquetar el PDF final. Actívala ante CUALQUIER petición sobre un libro o documento largo, tanto si abarca un solo paso ("pasa este PDF a markdown", "haz OCR de este escaneo", "tradúceme este capítulo", "revisa esta traducción", "qué dice este libro sobre X") como si abarca varios ("procesa este libro", "prepáralo para estudio", "de este PDF sácame un PDF español"). No la uses para vídeos de YouTube.
---

# La Forja — libros y documentos, de principio a fin

Suite para convertir libros a **markdown limpio por capítulo** (con las notas al pie
resueltas como `[^N]`), traducirlos, verificarlos y maquetarlos.

## Cómo se usa esta skill

**El usuario no elige herramientas ni fases: describe un resultado y tú decides.** Nunca
le preguntes qué script usar ni qué skill aplicar. Por tanto:

1. **Identifica en qué fase estás** con la tabla de abajo. Si la petición abarca varias,
   encadénalas en el orden del flujo, sin pedir permiso entre pasos.
2. **Lee el archivo de referencia de esa fase** —solo ese— antes de actuar. Contienen el
   criterio detallado y las trampas medidas; esta página es solo el enrutador.
3. **Sondea, no preguntes lo inferible.** Formato, escaneo o digital, columnas, tablas: se
   detectan con comandos. Pregunta SOLO lo que no se puede inferir: idioma destino al
   traducir, o qué front-matter descartar.
4. **Previsualiza siempre** (`--dry-run`, o un capítulo suelto) antes del libro entero, y
   **anuncia en una línea la ruta elegida y por qué**.

Define `T=tools` (o la ruta absoluta del repo) al empezar.

## Fases y dónde está el criterio

| Si la petición es… | Lee |
|---|---|
| convertir un documento a markdown | `referencias/conversion.md` |
| el escaneo está mal, el OCR salió corrupto | `referencias/ocr.md` |
| las notas al pie se perdieron, rompieron o no están enlazadas | `referencias/aparato-notas.md` |
| comprobar que la conversión no perdió texto | `referencias/qa-conversion.md` |
| traducir a otro idioma | `referencias/traducir.md` |
| comprobar una traducción ya hecha | `referencias/qa-traduccion.md` |
| corregir estilo, erratas, consistencia | `referencias/revisar-prosa.md` |
| citas `[@clave]`, `.bib`, bibliografía | `referencias/citas.md` |
| buscar qué dice un libro sobre un tema | `referencias/explorar.md` |
| la petición abarca varios pasos | `referencias/flujo.md` |

## El orden del flujo, que importa

```
convertir → RECONSTRUIR NOTAS → traducir → QA → prosa/citas → PDF
```

**Reconstruir el aparato va ANTES de traducir.** Si traduces primero, hay que rehacerlo en
los dos idiomas a la vez. Comprueba siempre `grep -c "\[\^" markdown/*.md` antes de lanzar
una traducción: sin `[^N]`, las notas se imprimen como párrafos sueltos en mitad del texto.

**Y verifica antes de traducir**, no después: traducir desde una fuente incompleta propaga
el defecto al idioma destino y multiplica el trabajo por dos.

## Dónde vive el conocimiento

- **`CLAUDE.md` del repo** — el algoritmo de diagnóstico completo y las lecciones medidas
  que todavía no son código. Es la referencia larga; consúltala ante un libro difícil.
- **`tools/CATALOG.md`** — el índice de las herramientas, autogenerado desde sus docstrings.
- **`forja/`** — el núcleo (`comun`, `aparato`, `paginas`, `pdfxml`). Sus guardas tienen
  test en `tests/`, así que **actúan solas**: no dependen de que recuerdes leerlas.
- **El docstring de cada herramienta** explica la patología que ataca y sus trampas.

Ante un libro difícil, mira el catálogo antes de escribir un script suelto. Casi todo lo
que parece un caso nuevo ya está resuelto en alguna parte.
