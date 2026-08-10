#!/usr/bin/env python3
"""footnotes_redistribute.py — reparte las definiciones `[^N]:` a su sección.

CLI sobre `forja.aparato`. La lógica y sus guardas viven en el módulo, con sus
tests en `tests/test_aparato.py`.

Para qué sirve
--------------
Muchos EPUB (Calibre/Kindle) guardan TODAS las notas en un documento-pool, así
que el conversor las vuelca juntas al final de cada archivo, típicamente bajo un
encabezado «## Notes». Eso se lee bien mientras el archivo es un libro entero,
pero **al trocear por capítulos las definiciones se quedan TODAS en el último
trozo**: los capítulos anteriores conservan sus llamadas `[^N]` sin definición y,
al maquetar, esas notas NO se imprimen —pandoc descarta la llamada huérfana en
silencio—. El balance refs↔defs del archivo sin trocear no lo ve.

Por eso este paso va ANTES de `split_chapters.py`.

Reglas
------
* Una definición va a la sección donde aparece su PRIMERA llamada.
* Las definiciones sin llamada NO se borran: se quedan donde estaban y se
  reportan. Perderlas es peor que dejarlas descolocadas.
* El encabezado del bloque se elimina solo si queda vacío.
* No se renumera nada (`md_to_pdf` renumera al maquetar) y no se tocan los
  bloques de código cercados.

Uso
---
    python3 footnotes_redistribute.py libro.md --level 3            # dry-run
    python3 footnotes_redistribute.py libro.md --level 3 --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forja.aparato import repartir  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--level", type=int, default=2,
                    help="nivel de encabezado que delimita la sección (def. 2)")
    ap.add_argument("--apply", action="store_true", help="escribir los cambios")
    args = ap.parse_args()

    rc = 0
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"warning: no existe: {p}", file=sys.stderr)
            rc = 1
            continue
        texto = p.read_text(encoding="utf-8")
        nuevo, stats = repartir(texto, args.level)
        print(f"{p.name}: {stats['defs']} definición(es), {stats['moved']} reubicada(s)")
        if stats["orphan_defs"]:
            print(f"  ⚠ {len(stats['orphan_defs'])} SIN LLAMADA (se conservan donde estaban; "
                  f"pandoc no las imprimiría): {stats['orphan_defs'][:10]}")
        if stats["unresolved_refs"]:
            print(f"  ⚠ {len(stats['unresolved_refs'])} llamada(s) sin definición: "
                  f"{stats['unresolved_refs'][:10]}")
        if args.apply and nuevo != texto:
            p.write_text(nuevo, encoding="utf-8")
            print("  escrito")
        elif not args.apply and nuevo != texto:
            print("  (ensayo: nada escrito. Añade --apply)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
