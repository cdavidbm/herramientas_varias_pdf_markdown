"""La Forja — núcleo compartido del taller de conversión de libros.

Este paquete existe porque durante mucho tiempo NO existió. `tools/` llegó a 79
scripts con 18.000 líneas de las que solo 21 importaban algo común: 25
implementaban su propio `--apply`, 14 su `--dry-run`, 76 su `main()` y 6
llamaban a `pdftotext` cada uno a su manera. Sin un sitio donde apoyarse, cada
libro nuevo salía más barato resolverlo con un script suelto que averiguando si
alguna de las 79 encajaba — y así el conocimiento acabó en prosa (advertencias
en el CLAUDE.md) en vez de en código con su test.

La regla de este paquete: **una lección medida se codifica como GUARDA con su
test de regresión**, no como párrafo de aviso. Si algo solo está documentado,
solo actúa cuando alguien se acuerda de leerlo.

    forja.comun    — primitivas (slugify, pdftext, plan.json, diccionario)
    forja.aparato  — el aparato de notas: separar, anclar, repartir, auditar
"""
