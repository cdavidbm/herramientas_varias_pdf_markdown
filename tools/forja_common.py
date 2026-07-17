#!/usr/bin/env python3
"""
forja_common.py — Lo que TODOS los conversores de La Forja hacían por su cuenta.

No es una capa de abstracción: es el sitio donde vive UNA sola versión de cuatro
cosas que estaban copiadas por el repo (slugify ×11, require_tool ×5,
page_count ×5, parseo de plan.json ×8) y que habían divergido en silencio.

Importar desde un script de `tools/`:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from forja_common import slugify, require_tool, pdf_page_count, load_plan

(El patrón ya lo usaba `limpiar_academico.py`.)

POR QUÉ IMPORTA `slugify`, y no es cosmética
--------------------------------------------
Las 11 copias eran 3 comportamientos incompatibles: unas preservaban Unicode y
otras lo aplastaban a ASCII con NFKD. El MISMO capítulo salía como `Bhāva_` o
`Bhava_` según qué script lo troceara — y en un taller de hermetismo, donde los
títulos van llenos de transliteraciones del griego, el árabe y el sánscrito, eso
es un nombre de archivo corrupto y un enlace roto.

Aquí el default PRESERVA Unicode (lo que hacía la mayoría, y lo correcto para
este material). `ascii_only=True` sigue disponible para quien lo quiera.

Y normaliza a **NFC**, que arregla un pisotón real y ya sufrido: «Öner Döser»
guardado en DESCOMPUESTO (`O` + U+0308) hace fallar a `pdfinfo`/`pdftotext`
aunque `ls` lo muestre perfecto. Todo slug sale precompuesto.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

__all__ = ["slugify", "require_tool", "pdf_page_count", "load_plan",
           "load_dict", "run", "pdftext"]

# Diccionarios del sistema, en orden de preferencia. La unión de british+american
# es lo que quiere el material (ortografía mixta en ediciones clásicas).
_DICT_PATHS = ["/usr/share/dict/british-english", "/usr/share/dict/american-english",
               "/usr/share/dict/words"]
_DICT_CACHE: set[str] | None = None


def load_dict() -> set[str]:
    """Palabras del diccionario del sistema (minúsculas), cacheadas.

    UNA sola versión de lo que `fix_ligatures.load_words`, `ocr_spellfix.load_dict`
    y `limpiar_academico` cargaban por su cuenta —con listas de rutas distintas, y
    por tanto vocabularios distintos—. Devuelve la UNIÓN de los diccionarios que
    existan; vacío si no hay ninguno (el llamador decide si eso es fatal)."""
    global _DICT_CACHE
    if _DICT_CACHE is None:
        words: set[str] = set()
        for p in _DICT_PATHS:
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    words |= {w.strip().lower() for w in fh if w.strip()}
            except FileNotFoundError:
                pass
        _DICT_CACHE = words
    return _DICT_CACHE


def run(cmd: list[str], *, check: bool = True, quiet: bool = True) -> str:
    """Ejecuta un comando y devuelve su stdout (texto). La versión única de los
    `def sh(...)` que estaban copiados en varios conversores."""
    out = subprocess.run(cmd, text=True, capture_output=True)
    if check and out.returncode != 0:
        msg = out.stderr.strip() or f"exit {out.returncode}"
        sys.exit(f"error: {cmd[0]} failed: {msg}")
    return out.stdout


def pdftext(pdf: Path | str, first: int | None = None, last: int | None = None,
            *, layout: bool = False, raw: bool = False) -> str:
    """Extrae texto de un PDF con pdftotext. `layout` conserva columnas; `raw`
    respeta el orden de lectura interno del OCR (mejor en escaneos MUY degradados,
    donde `-layout` dispersa la prosa). Sin ninguno, modo por defecto de poppler."""
    require_tool("pdftotext")
    cmd = ["pdftotext"]
    if layout:
        cmd.append("-layout")
    if raw:
        cmd.append("-raw")
    if first is not None:
        cmd += ["-f", str(first)]
    if last is not None:
        cmd += ["-l", str(last)]
    cmd += [str(pdf), "-"]
    return run(cmd, check=False)


def slugify(text: str, maxlen: int = 80, *, ascii_only: bool = False,
            lower: bool = False, fallback: str = "section") -> str:
    """Título → nombre de archivo seguro, SIN perder la tipografía del original.

    maxlen     : recorte (cada script tenía el suyo: 40-90).
    ascii_only : aplasta a ASCII (`Bhāva`→`Bhava`). Solo si de verdad necesitas
                 ASCII: DESTRUYE transliteraciones.
    lower       : fuerza minúsculas.
    fallback    : si no queda nada (título de puros símbolos, p. ej. `♄♃`).
    """
    text = unicodedata.normalize("NFC", text or "").strip()
    if ascii_only:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    if lower:
        text = text.lower()
    # Fuera todo lo que no sea palabra/espacio/guion (`\w` es Unicode por defecto
    # en py3, así que ā, ω y ñ sobreviven).
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    # Espacios y guiones bajos colapsan a UN separador. El GUION se conserva: en
    # `al-Mawālīd` o `al-Bīrūnī` es parte del nombre, no un separador.
    # Idempotente: slugify(slugify(x)) == slugify(x).
    text = re.sub(r"[\s_]+", "_", text.strip())
    text = text[:maxlen].strip("_-")
    return text or fallback


def require_tool(name: str, hint: str = "apt: poppler-utils") -> None:
    """Muere pronto y con un consejo si falta un binario externo."""
    if shutil.which(name) is None:
        sys.exit(f"error: required tool '{name}' is not installed ({hint})")


def pdf_page_count(pdf: Path | str) -> int:
    """Páginas de un PDF, vía pdfinfo."""
    require_tool("pdfinfo")
    try:
        out = subprocess.check_output(["pdfinfo", str(pdf)], text=True,
                                      stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Casi siempre: nombre en Unicode DESCOMPUESTO (NFD) o PDF cifrado.
        sys.exit(f"error: pdfinfo failed on {pdf}\n"
                 f"  ¿nombre en NFD? resuelve por glob: F=$(ls *Parte*.pdf | head -1)\n"
                 f"  ¿cifrado? qpdf --decrypt in.pdf out.pdf")
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"could not determine page count for {pdf}")


def load_plan(path: Path | str) -> dict:
    """Lee un plan.json y NORMALIZA sus secciones a una sola forma.

    Cierra las tres grietas que tenía el esquema repartido por 8 scripts:

    1. `pages: [ini, fin]` ⇄ `start`/`end` escalares — ambas formas entran, y
       salen SIEMPRE como las dos, así que da igual qué lea el conversor.
       `fin: null` = hasta el final (se deja en None; resuélvelo con el nº real
       de páginas).
    2. `slug` se RESPETA. `split_pdf.py` y `pdf_sections_to_markdown.py` lo
       descartaban y derivaban el nombre de `slugify(title)`: pedías
       `01_Prefacio` y salía `00_Prefacio`.
    3. Rutas relativas se resuelven contra la carpeta DEL PLAN, no contra el cwd.
    """
    path = Path(path)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"error: plan not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"error: {path} is not valid JSON: {e}")

    plan_dir = path.parent.resolve()
    plan["_plan_dir"] = plan_dir

    if plan.get("source"):
        src = Path(plan["source"])
        plan["source_path"] = src if src.is_absolute() else (plan_dir / src).resolve()

    out = Path(plan.get("output_dir", "markdown"))
    plan["output_path"] = out if out.is_absolute() else (plan_dir / out).resolve()

    sections = plan.get("sections") or []
    if not sections:
        sys.exit(f"error: {path} has no 'sections'")

    width = max(2, len(str(len(sections))))
    for i, sec in enumerate(sections):
        pages = sec.get("pages")
        if pages:
            sec["start"] = pages[0]
            sec["end"] = pages[1] if len(pages) > 1 else None
        elif sec.get("start") is not None:
            sec["pages"] = [sec["start"], sec.get("end")]
        # `pdf:` (un PDF entero como sección) no lleva páginas: es legítimo.

        title = sec.get("title", "")
        if not sec.get("slug"):
            sec["slug"] = f"{str(i + 1).zfill(width)}_{slugify(title)}"

    return plan
