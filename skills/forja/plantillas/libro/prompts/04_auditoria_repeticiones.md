# Prompt: auditoría de repeticiones (solo lectura)

Eres revisor de un libro académico. Proyecto: `<ruta>`. Libro en `02_libro/`.

SOLO LECTURA. Lee el libro completo y detecta repeticiones entre capítulos (y dentro de cada uno):
- doctrinas o explicaciones expuestas por extenso más de una vez;
- la misma cita comentada con el mismo propósito en varios lugares;
- párrafos de apertura o cierre casi idénticos entre capítulos paralelos (fórmulas estereotipadas);
- capítulos de síntesis que reexponen en vez de sintetizar;
- si hay un texto integrado (excurso) que desarrolla lo que un capítulo resume: ¿debe acortarse el capítulo?
Distingue la repetición útil (paralelismo deliberado de la plantilla, recapitulación breve con remisión) de la redundante.

Informe en `00_investigacion/revision/rev_repeticiones.md` (único archivo que escribes). Por hallazgo: id, ubicaciones (archivo:línea), diagnóstico y PROPUESTA: la «sede» (el único lugar que conserva la exposición completa) y el texto breve de sustitución con remisión en los demás. Prioridad y palabras ahorrables estimadas.

Respuesta final: resumen de 5–10 líneas y la ruta.
