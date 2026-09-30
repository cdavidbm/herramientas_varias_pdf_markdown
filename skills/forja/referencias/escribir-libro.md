# Investigar y escribir un libro a partir de un corpus de fuentes

Fase para cuando el usuario pide **escribir** algo propio (un libro, un ensayo largo, un
estudio) a partir de fuentes que él aporta: libros de su biblioteca, transcripciones de
clases, cuadernos de NotebookLM, PDF por convertir. No es traducir ni resumir: es construir
una tesis propia, documentada, con citas verificables.

El método está medido en *El cielo de los Nombres* (86 000 palabras, 14 capítulos, un
excurso y 7 apéndices; 9 fuentes, 153 clases en vídeo, 7 coloquios). Las plantillas están en
`plantillas/libro/` junto a esta skill; los prompts de los agentes, en `plantillas/libro/prompts/`.

## Principios (no negociables)

1. **Corpus cerrado.** Solo las fuentes autorizadas por el usuario. Todo dato ajeno va en
   nota, marcado **[X]**, o no va. Es lo que hace creíble el libro y verificable cada frase.
2. **Toda correspondencia o tesis lleva su grado de evidencia.** Los niveles, fijados en la
   matriz antes de redactar, se escriben en el texto. En el libro de modelo eran:
   - **[E]** explícito en la fuente;
   - **[D]** derivado de dos fuentes que describen el mismo rasgo;
   - **[P]** propuesto por el libro;
   - **[O]** operativo (una fuente práctica que corrobora, pero no funda);
   - **[X]** externo.

   Súmales la **convergencia por familias de fuentes** (C·A·B). Esas distinciones NO son
   «blindaje»: son el método, y ninguna revisión de estilo puede borrarlas.
3. **Se investiga antes de escribir.** Dossiers primero, plan y matriz después, y solo
   entonces la redacción. El usuario suele pedirlo así («primero investiga, haz el plan,
   profundiza»); si no lo dice, hazlo igual.
4. **Las citas se verifican contra la fuente local, no contra el dossier.** El dossier es
   un intermediario y hereda erratas: dos páginas mal tomadas del dossier de al-Būnī se
   propagaron a tres capítulos hasta la verificación.
5. **Lo determinista, en scripts.** Integridad, invariantes y claves de cita se comprueban
   con herramientas (abajo), nunca releyendo.
6. **Decisiones del usuario, solo las suyas.** Si delega la arquitectura («elige con
   sabiduría y libertad»), decide y déjalo registrado en la matriz (§ Decisiones) con fecha.
   Lo que es suyo, pregúntalo una vez: tesis, tono, público, alcance y si un texto propio
   debe integrarse.

## Estructura de la carpeta del proyecto

```
<Proyecto>/
  00_investigacion/   README (corpus y hallazgos) · dossiers por fuente · transcripciones ·
                      verificacion/ · revision/ (informes y registros de agentes)
  01_plan/            PLAN · MATRIZ_DE_DECISIONES · BIBLIOGRAFIA · GUIA_DE_ESTILO · CLAVES
  02_libro/           00_Indice · NN_Capitulo.md … · apéndices · referencias
  REANUDAR.md         estado y siguiente paso (proyecto de varias sesiones)
```

Copia las plantillas: `cp -r <skill>/plantillas/libro/* <Proyecto>/01_plan/` y rellénalas.
Al terminar el libro **no borres el trabajo**: archívalo (`tar czf _archivo_de_trabajo.tar.gz
00_investigacion 01_plan REANUDAR.md`). El usuario puede querer reutilizarlo como método.

## Fases

### 1. Encargo y corpus

- Anota en `00_investigacion/README.md` el objetivo, el público, el idioma, el sistema de
  citas (APA 7 por defecto) y la lista cerrada de fuentes, con su ruta o su cuaderno NotebookLM.
- Convierte lo que haga falta con las fases de conversión de La Forja. Orienta cada fuente
  con `book_map.py` y búscala con `book_index.py` antes de leerla entera.
- **Corpus en vídeo:** genera YA la tabla de claves con
  `python3 tools/apa_video_keys.py carpeta/ > 01_plan/CLAVES.md`. Las letras (2021a, 2021b…)
  asignadas a mano producen citas cruzadas (medido: dos capítulos con la clave de otra clase).
- **NotebookLM:** pide las transcripciones completas (no resúmenes) y guárdalas en
  `00_investigacion/`. Lo que venga de un resumen de NotebookLM y no esté en la transcripción
  no puede ir entre comillas (medido: una lista de «vicios solares» que ningún ponente dijo).

### 2. Dossiers por fuente (agentes en paralelo)

- Un agente por fuente o tramo de fuente, con `prompts/01_dossier.md`. Cada dossier sigue
  `DOSSIER_FUENTE.md`:
  - ficha APA y forma de cita;
  - síntesis de las tesis;
  - fichas por concepto con localizador exacto (§, n.º, p., clase);
  - citas textuales breves;
  - advertencias (erratas, capas de autoría dudosa, variantes).
- La paginación se fija en el dossier una vez y para siempre (p. ej. «página impresa = PDF − 12»).
- Cierra con un README de hallazgos: qué condiciona el plan y qué no es fiable.

### 3. Plan, matriz, guía y bibliografía

- **PLAN:** propósito, pregunta de investigación, tesis, alcance, método, arquitectura por
  partes y capítulos, fases y decisiones abiertas.
- **MATRIZ DE DECISIONES:** el corazón del libro.
  - el principio rector y los niveles de evidencia;
  - los **ejes o puentes** que conectan los dos dominios (en el modelo eran tres: complexional,
    septenario de atributos y parejas-polaridades);
  - las fichas de cada unidad (capítulo o elemento);
  - la tabla general;
  - § **Decisiones**, numeradas y fechadas.
- **GUIA DE ESTILO:** voz, transliteración, formato markdown, forma de citar cada fuente,
  marcas y términos. Escríbela sobre la PRÁCTICA: una guía que nadie sigue genera la mitad
  de los hallazgos de la revisión.
- **BIBLIOGRAFÍA:** siglas de trabajo (solo para el plan), la lista APA y la forma de las citas.

### 4. Redacción

- Primero la Parte I (fundamentos y método), después las unidades con **una plantilla
  común** (en el modelo, el capítulo planetario: fuentes → atributo cardinal → regente →
  pareja → corte → temple → tríada → catarsis → cuadro de síntesis), y al final extensiones,
  conclusión y apéndices.
- Títulos: `# Capítulo N · Título`, secciones numeradas `## 1.`, `### 1.1`. Las remisiones
  internas («véase el capítulo 4, §3.3.3») dependen de esa numeración: **no renumeres después**.
- Cada capítulo cierra con `## Referencias del capítulo`. El apéndice de referencias
  general se genera con script a partir de ellas.
- Actualiza `REANUDAR.md` y la memoria del proyecto al final de cada sesión.

### 5. Verificación de citas (agentes por bloques de capítulos)

- Un agente por cada 3–4 capítulos, con `prompts/02_verificar_citas.md`. Coteja cada cita entre
  comillas y cada localizador **contra la fuente local**, corrige en el archivo y deja un
  registro con la leyenda V (verificada), C (corregida), P (pasada a paráfrasis), E (eliminada)
  o Pd (pendiente).
- Cuando un verificador descubre una errata de un dossier, **avisa a los demás** (SendMessage):
  la errata suele repetirse en otros capítulos.
- Números medidos: sobre unas 1 000 citas, un 13 % hubo que corregirlas y un 2 % no eran
  literales. Sin esta fase el libro no es fiable.

### 6. Revisión de conjunto (dos fases)

1. **Tres auditorías de solo lectura en paralelo**, sobre el libro entero, cada una con su
   informe en `00_investigacion/revision/`:
   - contradicciones (`prompts/03_auditoria_contradicciones.md`);
   - repeticiones, con «sede» y reducción por hallazgo (`04_…`);
   - estilo, con reglas globales y problemas puntuales (`05_…`).
2. **Aplicación.**
   - Primero lo mecánico, con un script tuyo (encabezados, transliteración, formato de citas).
   - Después, agentes con **archivos disjuntos** (`06_aplicar_revision.md`). Nunca dos
     agentes sobre el mismo archivo; la carpeta scratchpad se comparte, así que cada uno usa
     un prefijo propio para sus scripts.
   - Antes de recortar repeticiones, resuelve las contradicciones: si no, se conserva la
     versión equivocada.

### 7. Auditoría fina párrafo por párrafo (si el usuario la pide)

- Un agente por archivo, con `prompts/07_auditoria_fina.md`. **Exige lectura sección por
  sección desde el primer encargo**: en la primera ronda, los agentes que reciben el archivo
  entero hacen una sola lectura con unas 15 ediciones por 5 000 palabras, y hubo que pedir a
  casi todos una segunda pasada.
- Cada agente guarda una copia `.orig` y al final corre
  `python3 tools/book_invariants.py orig.md editado.md`. El coordinador autoriza uno por uno
  los cambios de fondo que aparezcan (comillas quitadas a una paráfrasis, una marca añadida
  por coherencia).
- Los problemas que exigen la fuente se anotan en el registro y los resuelve el coordinador
  cotejando los dossiers.

### 8. Cierre

- `python3 tools/book_integrity.py 02_libro/ --global-refs 02_libro/<apéndice_referencias>.md`
  debe dar 0 errores. Comprueba notas, remisiones, marcas de trabajo olvidadas y cobertura
  de referencias.
- PDF:
  ```
  python3 tools/md_to_pdf.py libro.pdf <capítulos en orden> --title "…" --subtitle "…" \
    --toc --toc-depth section --own-section-numbers --footnotes chapter \
    --short-headers --less-hyphenation [--arabic-font "Noto Naskh Arabic"] \
    [--font-fallback "TeX Gyre Pagella"]
  ```
  - `--own-section-numbers` porque los títulos ya numeran.
  - `--footnotes chapter` para que casen las remisiones del tipo «nota 4».
  - `TeX Gyre Pagella` de reserva cubre ✓ ≈ ↔ ∩, que Latin Modern descarta.
  - Revisa en imagen (`pdftoppm`) la portada, el índice, una tabla ancha y cualquier escritura
    no latina.
- Archiva el trabajo (ver arriba) y deja la carpeta con `02_libro/`, el PDF y el `.tar.gz`.

## Textos propios del usuario

Si el usuario aporta un texto suyo para integrarlo:
- colócalo donde sirva al argumento (en el modelo, un excurso entre los caps. 2 y 3, con su
  tabla como apéndice);
- conviértelo en remisión interna, nunca en fuente externa: «(véase el Excurso, §X)»;
- conserva su voz y su numeración. Homogeneiza con criterio conservador y archiva siempre el
  original. Al revisarlo se le aplican las mismas comprobaciones: el cotejo de sus recuentos
  reveló tres cifras que no cuadraban.

## Herramientas de esta fase

| Herramienta | Para qué |
|---|---|
| `tools/apa_video_keys.py` | tabla de claves APA de un corpus de vídeos (letras deterministas) |
| `tools/book_integrity.py` | notas, remisiones internas, marcas olvidadas y cobertura de referencias |
| `tools/book_invariants.py` | qué tocó una edición de estilo: citas, localizadores, encabezados, notas, remisiones, tablas y marcas |
| `tools/md_to_pdf.py` | PDF final (acepta títulos `# Capítulo N · …`) |
| `tools/book_map.py`, `book_index.py` | orientarse en las fuentes sin cargarlas enteras |
