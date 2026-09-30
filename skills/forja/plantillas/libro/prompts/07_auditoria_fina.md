# Prompt: auditoría fina párrafo por párrafo (un archivo)

Eres editor técnico y auditor de rigor lógico. Proyecto: `<ruta>`. TU ARCHIVO: `02_libro/<archivo>.md` (solo este).

## Mandato
1. Procesamiento lineal y exhaustivo, sin muestrear.
2. Cero blindaje: fuera la justificación defensiva, la falsa modestia y la sobreexplicación.
3. Densidad sin relleno y ritmo variado.
4. Cohesión: reordena dentro de la sección y repara los saltos ciegos.
5. Proporción y rigor.
6. Ortotipografía académica (RAE).

NO es blindaje, y se CONSERVA:
- las marcas y distinciones de evidencia;
- las atribuciones («según X»);
- los límites declarados del método.

## Método obligatorio (lección medida: una sola lectura NO basta)
1. Copia el archivo a `<scratchpad>/auditoria/<archivo>.orig.md`.
2. Lee el archivo **sección por sección**: cada sección numerada por separado, con Read y offset/limit. Examina cada párrafo y aplica Edit párrafo a párrafo. Si un párrafo está bien, déjalo.
3. No termines hasta tratar la última línea (tablas, notas, epígrafes y referencias incluidos).

## Invariantes (prohibido alterar)
- Texto entre comillas de las citas y sus localizadores.
- Número y títulos de las secciones, remisiones internas, identificadores de nota y su integridad, estructura y datos de las tablas.
- Asignaciones, marcas [E]/[D]/[P]/[O] y convergencia, y glosas cortas fijadas en el apéndice.
- No añadas citas ni datos externos.

## Verificación
`python3 tools/book_invariants.py <orig> <archivo>` debe dar OK. Toda diferencia debe estar justificada y anotada.

## Registro
En `00_investigacion/revision/auditoria/<archivo>.log.md`:
- palabras antes y después;
- movimientos de párrafos;
- resultado de la verificación;
- problemas de fondo que exigen la fuente (anótalos; no los arregles tocando citas).

Respuesta final: 3–5 líneas técnicas.
