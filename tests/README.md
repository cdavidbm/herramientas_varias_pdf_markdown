# tests/ — red de seguridad de La Forja

Tests de **lógica pura** (stdlib `unittest`, sin dependencias) que fijan los
invariantes cuya rotura causa **pérdida silenciosa de texto** o compilaciones
rotas. No cubren subprocess ni conversión real de PDF/EPUB; cubren las funciones
que deciden qué texto se conserva y cómo se escapa/formatea.

```bash
python3 -m unittest discover -s tests      # desde la raíz del repo
```

Qué protegen (todos surgieron de la auditoría):

- `latex_escape` — metacaracteres (`& % _ # $ ~ ^ { } \`) en título/autor no
  rompen la portada de `md_to_pdf.py`.
- `ends_terminal` — la detección de «el encabezado parte una frase»
  (`clean_markdown.py`) sigue viva (el `""` en `TERMINAL` la anulaba).
- `toks` Unicode — el griego y los acentos son visibles a la verificación de
  completitud (`check_completeness.py`); si no, un capítulo en griego «faltaría»
  sin avisar.
- `split_by_plan` monótono — headings repetidos/desordenados abortan en vez de
  producir una rebanada negativa (`split_chapters.py`).
- regex de referencias inline — no capturan años/decimales/enlaces como marcadores
  de nota (`rtf_to_markdown.py`, `pdf_chapters_to_markdown.py`).

Al reparar un bug de conversión, **añade aquí el caso** que lo reproduce antes de
arreglarlo: así no vuelve.
