#!/usr/bin/env python3
"""traducir_cascada.py — traduce un libro AGOTANDO un motor y pasando al siguiente.

Por qué existe
--------------
`traducir_libro.py` traduce con UN modelo. Cuando ese modelo se queda sin cuota
a mitad de un libro de 200.000 palabras, la traducción se para y hay que estar
delante para relanzarla a mano con otro `--model`.

Esto encadena los modelos: corre con el primero hasta que el motor avisa de que
no puede responder (código `EXIT_AGOTADO`, 86), y entonces sigue con el siguiente
SIN perder nada — el estado de `traducir_libro.py` se escribe tras cada archivo,
así que lo ya traducido no se repite y lo pendiente sigue pendiente.

Distinguir «cuota agotada» de «ha traducido mal» es lo que hace esto posible, y
no era gratis: antes `agy()` devolvía sólo `stdout`, así que una cuota agotada
llegaba como cadena vacía, indistinguible de un trozo mal traducido. El libro
entero se habría marcado «en fallo» archivo a archivo sin que nadie supiera que
bastaba con cambiar de modelo.

El orden de los modelos es CALIDAD DESCENDENTE, no capacidad: lo que primero se
agota debe ser lo mejor, para que el grueso del libro salga con el mejor motor
disponible y sólo la cola caiga en los flojos.

Cuando se agotan TODOS, sale con `EXIT_TODOS_AGOTADOS` (87) y lista lo que queda,
para que lo termine una persona o un agente.

Uso
---
    python3 traducir_cascada.py markdown --out es --glosario g.md --prompt P.txt \\
        --modelos "Gemini 3.1 Pro (High)" "Claude Sonnet 4.6 (Thinking)" \\
        --parallel 2
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

LIBRO = Path(__file__).resolve().parent / "traducir_libro.py"
EXIT_AGOTADO = 86
EXIT_TODOS_AGOTADOS = 87

# Calidad descendente. Los dos Claude van antes que los Flash aunque tengan menos
# cuota: es preferible que traduzcan pocos capítulos buenos a muchos mediocres.
MODELOS = [
    "Gemini 3.1 Pro (High)",
    "Claude Sonnet 4.6 (Thinking)",
    "Claude Opus 4.6 (Thinking)",
    "Gemini 3.6 Flash (High)",
    "Gemini 3.5 Flash (High)",
    "GPT-OSS 120B (Medium)",
]


def pendientes(estado_p: Path, src_dir: Path) -> list[str]:
    estado = json.loads(estado_p.read_text()) if estado_p.is_file() else {}
    return [f.name for f in sorted(src_dir.glob("*.md"))
            if estado.get(f.name, {}).get("estado") != "ok"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glosario", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, default=Path("_work"))
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--chunk-words", type=int, default=700)
    ap.add_argument("--modelos", nargs="+", default=MODELOS)
    ap.add_argument("--estado", type=Path, default=None)
    a = ap.parse_args()

    estado_p = a.estado or (a.out / "_estado_traduccion.json")

    for i, modelo in enumerate(a.modelos, 1):
        queda = pendientes(estado_p, a.src_dir)
        if not queda:
            print(f"\n=== nada pendiente: el libro está entero ===", flush=True)
            return 0
        print(f"\n=== [{i}/{len(a.modelos)}] {modelo} — {len(queda)} archivo(s) "
              f"pendientes ===", flush=True)

        cmd = [sys.executable, str(LIBRO), str(a.src_dir),
               "--out", str(a.out), "--glosario", str(a.glosario),
               "--prompt", str(a.prompt), "--workdir", str(a.workdir),
               "--parallel", str(a.parallel), "--chunk-words", str(a.chunk_words),
               "--model", modelo, "--rehacer"]
        r = subprocess.run(cmd)

        if r.returncode == EXIT_AGOTADO:
            print(f"--- {modelo} AGOTADO; paso al siguiente ---", flush=True)
            continue
        # Salió por su cuenta. Si aún queda algo, es fallo de contenido y no lo
        # arregla cambiar de modelo... salvo que otro modelo lo lea mejor, así
        # que se le da una oportunidad al siguiente igualmente.
        queda = pendientes(estado_p, a.src_dir)
        if not queda:
            print(f"\n=== libro completo con {modelo} ===", flush=True)
            return 0
        print(f"--- {modelo} terminó dejando {len(queda)} en fallo; "
              f"lo intenta el siguiente ---", flush=True)

    queda = pendientes(estado_p, a.src_dir)
    if not queda:
        return 0
    print(f"\nMOTORES_AGOTADOS quedan {len(queda)}: {', '.join(queda)}", flush=True)
    return EXIT_TODOS_AGOTADOS


if __name__ == "__main__":
    raise SystemExit(main())
