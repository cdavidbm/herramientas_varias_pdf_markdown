#!/usr/bin/env python3
"""forja_common.py — COMPATIBILIDAD. El código vive ahora en `forja.comun`.

Se conserva este módulo porque 21 scripts de `tools/` lo importan con el patrón
`sys.path.insert(tools) ; from forja_common import ...`, y porque hay carpetas
de libros con guiones de compilación que invocan esas herramientas. Romper los
nombres para ganar orden habría sido cambiar un desorden por una avería.

Código nuevo: `from forja.comun import ...`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forja.comun import (  # noqa: F401,E402
    load_dict, load_plan, pdf_page_count, pdftext, require_tool, run, slugify,
)

__all__ = ["slugify", "require_tool", "pdf_page_count", "load_plan",
           "load_dict", "run", "pdftext"]
