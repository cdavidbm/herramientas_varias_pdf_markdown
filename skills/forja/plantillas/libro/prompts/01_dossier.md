# Prompt: dossier de una fuente

Eres investigador para un libro académico en español. Proyecto: `<ruta>`. Encargo y corpus: `00_investigacion/README.md`.

TU FUENTE: <autor, título, tramo> en `<ruta local>`.

Escribe `00_investigacion/fuente_<sig>.md` siguiendo la plantilla `DOSSIER_FUENTE.md`:
- Lee la fuente ENTERA en su tramo; no muestrees. Oriéntate con `tools/book_map.py` y localiza con `tools/book_index.py`.
- Cada afirmación lleva su localizador exacto (§, n.º, p. impresa, cap., clase). Fija la regla de paginación en la cabecera.
- Citas textuales: breves y literales, copiadas de la fuente, nunca reconstruidas.
- Señala lo que conecta con <el otro dominio del libro> y su grado de explicitud (explícito / derivable / nada).
- Sección final de advertencias: erratas, capas de autoría dudosa, contradicciones internas y lo que la fuente NO dice.
- Nada externo a la fuente sin la marca **[externo]**.

Respuesta final: 5–8 líneas con los hallazgos que condicionan el plan.
