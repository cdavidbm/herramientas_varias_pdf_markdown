# Prompt: auditoría de contradicciones (solo lectura)

Eres revisor de un libro académico. Proyecto: `<ruta>`. Libro en `02_libro/`. Autoridad para las decisiones: `01_plan/02_MATRIZ_DE_DECISIONES.md` (§ Decisiones).

SOLO LECTURA: no edites el libro. Lee el libro completo y detecta CONTRADICCIONES INTERNAS:
- un mismo término asignado a unidades distintas sin reconocer la doble asignación (capítulos vs extensiones vs apéndices);
- discrepancias con los elementos fijados en la matriz;
- marcas de evidencia o convergencia distintas para la misma correspondencia en texto, tablas y apéndices;
- datos técnicos contradictorios entre capítulos;
- afirmaciones de método que los capítulos incumplen, y conclusiones que resumen algo distinto de lo que dicen los capítulos;
- recuentos inconsistentes;
- remisiones «véase el capítulo N, §X» que apuntan a una sección inexistente o que no trata el tema (apóyate en `tools/book_integrity.py`).

Informe en `00_investigacion/revision/rev_contradicciones.md` (único archivo que escribes). Por hallazgo: id, archivo:línea de cada lado, cita breve de cada lado, en qué consiste y PROPUESTA concreta (qué versión es la correcta según la matriz o los dossiers y la frase corregida). Ordena por gravedad. Sin cuestiones de estilo ni repeticiones.

Respuesta final: resumen de 5–10 líneas y la ruta.
