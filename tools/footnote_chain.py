#!/usr/bin/env python3
"""footnote_chain.py — separa el APARATO del CUERPO por la CADENA de números.

CLI sobre `forja.aparato`. La lógica y sus guardas viven en el módulo, con sus
tests en `tests/test_aparato.py`.

Cuándo se usa
-------------
Al extraer una página de PDF el bloque de notas va siempre al pie, pero la señal
habitual para encontrarlo —«las continuaciones van sangradas»— falla cuando se
recortó una columna (el recorte reinicia el origen X, p. ej. la mitad inglesa de
un facing árabe|inglés) o cuando el OCR aplastó la sangría. Sin sangría, una
línea de nota y una de cuerpo se parecen demasiado.

Lo que sí es robusto es que **los números de nota corren consecutivos**. Medido
en la *Abbreviation* de Abū Maʿshar (Brill, notas 1-112) y en las *Flowers*
(Dykes, 1-308, sin huecos).

Dos formatos de marcador, ambos vistos en ediciones reales:

* **misma línea** (por defecto): «  26 Latin: 'argumentum'.», incluso pegado
  («25P gives…»);
* **número solo** (`--number-only`): el volado va solo en su renglón y el texto
  en el siguiente.

Uso como módulo, que es lo normal dentro de un extractor:

    from forja.aparato import procesar_pagina
    md = procesar_pagina(texto_de_una_pagina, numero_solo=False)

Uso como CLI (un archivo como UN bloque; para probar o un caso suelto):

    python3 footnote_chain.py pagina.txt [--number-only]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forja.aparato import (  # noqa: F401,E402  (reexportado por compatibilidad)
    anclar_por_cursor, notas_por_cadena, procesar_pagina, separar_por_cadena,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, help="texto de una página (o bloque) a separar")
    ap.add_argument("--number-only", action="store_true",
                    help="el número de nota va solo en su línea (estilo Flowers/Dykes)")
    a = ap.parse_args()
    md = procesar_pagina(a.file.read_text(encoding="utf-8"), numero_solo=a.number_only)
    sys.stdout.write(md + "\n")
    sys.stderr.write(f"\n{len(re.findall(r'(?m)^\\[\\^\\d+\\]:', md))} notas separadas\n")


if __name__ == "__main__":
    main()
