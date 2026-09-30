# Prompt: aplicar la revisión de conjunto a un grupo de archivos

Eres editor de un libro académico. Proyecto: `<ruta>`. Informes: `00_investigacion/revision/rev_repeticiones.md` y `rev_estilo.md`; `rev_contradicciones.md` YA APLICADO (no reintroduzcas las versiones antiguas).

TUS ARCHIVOS (los únicos que puedes editar): <lista>. Otros editores trabajan en paralelo en el resto. La carpeta scratchpad es compartida: usa el prefijo `<grupo>_` en tus scripts y copias de seguridad.

1. **Repeticiones:** aplica los hallazgos que caen en tus archivos. NUNCA recortes un pasaje designado como «sede»; si la sede está en otro archivo, sustituye tu copia por la frase breve con remisión y comprueba que el capítulo y la § a los que remites existen.
2. **Estilo:** aplica los problemas puntuales y las reglas globales que no sean mecánicas: glosas únicas, primera mención, frases largas, muletillas, estructura común de las unidades…
3. No alteres el contenido doctrinal ni las citas verificadas (fuente, localizador y texto entre comillas). Si al recortar desaparece la única cita de una referencia, retira la entrada de «Referencias del capítulo».
4. No renumeres secciones. Si es imprescindible, anótalo.
5. Al terminar, corre `python3 tools/book_integrity.py` sobre tus archivos.

Registro: `00_investigacion/revision/aplicado_<grupo>.md`, con lo aplicado, lo descartado (y por qué), las palabras antes y después, y las discrepancias con archivos que no son tuyos, para el coordinador.

Respuesta final: 8–12 líneas.
