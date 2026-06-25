---
name: citas
description: Gestiona citas y bibliografía académica en markdown con pandoc --citeproc. Inserta citas [@clave], mantiene un archivo .bib, genera la bibliografía formateada en el estilo elegido (Chicago, MLA, APA…) y verifica claves huérfanas o sin definir. Activa con "/citas" o intención como "añade la bibliografía", "formatea las citas", "gestiona las referencias de este documento".
---

# Citas y Bibliografía — pandoc citeproc

Flujo de **citas académicas** sobre markdown: citas con clave `[@autor2020]`, una
base bibliográfica `.bib` y generación de la bibliografía formateada con
**pandoc `--citeproc`** (ya instalado, integrado en pandoc 3.x; no requiere
biber). Útil para tus textos académicos y para anotar traducciones.

## Cuándo se activa

- Explícito: `/citas`
- Intención: "añade/formatea la bibliografía", "gestiona las referencias",
  "convierte estas citas al estilo Chicago".

## Piezas del flujo

1. **Base bibliográfica:** un archivo `referencias.bib` (BibTeX) o `.yaml`/CSL-JSON
   con las entradas. Cada entrada tiene una **clave de cita** (p. ej. `ptolemy1940`).
2. **Citas en el texto:** sintaxis pandoc —
   - `[@ptolemy1940]` → (Ptolomeo 1940)
   - `[@ptolemy1940, p. 23]` → con localizador
   - `[-@ptolemy1940]` → solo el año
   - `@ptolemy1940` → Ptolomeo (1940) en prosa
   - varias: `[@a2001; @b1999]`
3. **Estilo (CSL):** Chicago author-date (por defecto en pandoc), o uno `.csl`
   concreto (MLA, APA, Harvard…) con `--csl estilo.csl`.

## Operaciones que puedes hacer

**Insertar/normalizar citas:** convertir referencias sueltas del texto a claves
`[@clave]` y crear/actualizar la entrada en el `.bib`.

**Generar el documento con bibliografía:**
```bash
pandoc capitulo.md \
    --citeproc \
    --bibliography=referencias.bib \
    --csl=chicago-author-date.csl \
    -o capitulo.pdf        # o .docx, .html, .tex
```
O dejar los metadatos en el YAML del markdown:
```yaml
---
bibliography: referencias.bib
csl: chicago-author-date.csl
---
```
La bibliografía se inserta donde haya un `# Bibliografía` con `::: {#refs} :::`,
o al final por defecto.

**Verificar consistencia (script incluido):**

```bash
python3 ~/.claude/skills/citas/check_citations.py referencias.bib capitulo.md [mas.md ...]
```
Cruza las claves `[@clave]` del texto contra el `.bib` (o CSL-JSON) y reporta:
- 🔴 **Claves citadas sin entrada** en el `.bib` (sale con código 1).
- 🟡 **Entradas nunca citadas** (huérfanas, para limpiar).
- 🔴 **Claves duplicadas** en el `.bib`.

Es exhaustivo y va más allá del aviso de pandoc (que no lista las huérfanas).

## Procedimiento sugerido

1. Localiza o crea `referencias.bib` junto al documento.
2. Si el texto trae citas en prosa o estilo Harvard `(Autor año)`, ofrécete a
   convertirlas a `[@clave]` y poblar el `.bib` (pidiendo los datos que falten).
3. Pregunta el **estilo** deseado si no está claro (por defecto Chicago
   author-date). Si hace falta un `.csl` que no esté, indícale al usuario de
   dónde bajarlo (repo oficial *citation-style-language/styles*) o usa el de
   pandoc por defecto.
4. Genera la salida con `--citeproc` y reporta cualquier cita no encontrada.

## Límite honesto

pandoc citeproc formatea según el CSL: la **exactitud de los datos** (autor, año,
páginas) depende de tu `.bib`. Reviso consistencia y formato, no verifico que la
referencia sea bibliográficamente correcta contra la fuente real.
