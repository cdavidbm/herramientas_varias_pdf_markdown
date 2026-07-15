#!/usr/bin/env python3
"""
test_forja.py — Red de seguridad (stdlib `unittest`, sin dependencias) para la
LÓGICA PURA de los scripts de La Forja. No cubre subprocess ni conversión real de
PDF/EPUB; fija los invariantes que, de romperse, causan PÉRDIDA SILENCIOSA de texto
o compilaciones rotas (los mismos que reparó la auditoría).

Correr:
    python3 -m unittest discover -s tests        # desde la raíz del repo
    python3 tests/test_forja.py                   # equivalente

Solo se importan módulos que cargan con la stdlib (sin bs4/striprtf/cv2). Los
scripts que dependen de terceros se prueban replicando su regex, no importándolos.
"""
import re
import sys
import unittest
from pathlib import Path

# tools/ al path para importar los scripts como módulos
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import md_to_pdf
import clean_markdown
import check_completeness
import split_chapters


class LatexEscape(unittest.TestCase):
    """md_to_pdf.latex_escape: título/autor con metacaracteres no rompen LaTeX."""

    def test_metachars(self):
        self.assertEqual(
            md_to_pdf.latex_escape("Q&A 100% #1_test $x"),
            r"Q\&A 100\% \#1\_test \$x")

    def test_backslash(self):
        self.assertEqual(md_to_pdf.latex_escape(r"a\b"), r"a\textbackslash{}b")

    def test_braces_and_carets(self):
        self.assertEqual(md_to_pdf.latex_escape("{x}~y^z"),
                         r"\{x\}\textasciitilde{}y\textasciicircum{}z")

    def test_plain_text_untouched(self):
        self.assertEqual(md_to_pdf.latex_escape("El arte de la astrología horaria"),
                         "El arte de la astrología horaria")


class EndsTerminal(unittest.TestCase):
    """clean_markdown.ends_terminal: sin el "" espurio en TERMINAL, la detección
    de «el encabezado parte una frase» vuelve a funcionar."""

    def test_empty_is_terminal(self):
        self.assertTrue(clean_markdown.ends_terminal(""))
        self.assertTrue(clean_markdown.ends_terminal("   "))

    def test_finished_sentence(self):
        self.assertTrue(clean_markdown.ends_terminal("Una frase completa."))
        self.assertTrue(clean_markdown.ends_terminal("¿Pregunta?"))

    def test_unfinished_sentence_is_not_terminal(self):
        # ANTES devolvía True (endswith("") siempre True) y anulaba la lógica.
        self.assertFalse(clean_markdown.ends_terminal("una frase que continúa"))
        self.assertFalse(clean_markdown.ends_terminal("el planeta regente del"))

    def test_empty_string_not_in_terminal(self):
        self.assertNotIn("", clean_markdown.TERMINAL)


class ToksUnicode(unittest.TestCase):
    """check_completeness.toks: el texto no-ASCII (griego, acentos) es VISIBLE a la
    verificación de completitud; si no, un capítulo en griego «faltaría» sin avisar."""

    def test_greek_and_accents_visible(self):
        words = [w for w, _, _ in check_completeness.toks("λόγος ῥητορική acción 123")]
        self.assertIn("λόγος", words)
        self.assertIn("ῥητορική", words)
        self.assertIn("acción", words)
        self.assertIn("123", words)

    def test_underscore_is_separator(self):
        # `[^\W_]` trata el guion bajo como separador, no como parte de palabra.
        words = [w for w, _, _ in check_completeness.toks("foo_bar")]
        self.assertEqual(words, ["foo", "bar"])


class SplitByPlanMonotonic(unittest.TestCase):
    """split_chapters.split_by_plan: headings desordenados/repetidos abortan en vez
    de producir una rebanada negativa (capítulo vacío = texto perdido)."""

    def _lines(self):
        return [
            "# Índice",
            "## Capítulo 2",     # el título aparece PRIMERO en el índice
            "## Capítulo 1",
            "texto del cuerpo",
            "## Capítulo 1",     # y de nuevo en el cuerpo, más abajo
            "cuerpo cap 1",
            "## Capítulo 2",
            "cuerpo cap 2",
        ]

    def test_ordered_plan_ok(self):
        plan = {"sections": [
            {"heading": "## Capítulo 1", "title": "Cap 1"},
            {"heading": "## Capítulo 2", "title": "Cap 2"},
        ]}
        # Cap 1 (línea 2) antes que Cap 2 (línea 1) -> starts NO monótonos -> aborta.
        with self.assertRaises(SystemExit):
            split_chapters.split_by_plan(self._lines(), plan)

    def test_good_document_does_not_raise(self):
        lines = ["front", "## Uno", "a", "## Dos", "b"]
        plan = {"sections": [
            {"title": "Front"},                       # front matter (start 0)
            {"heading": "## Uno", "title": "Uno"},
            {"heading": "## Dos", "title": "Dos"},
        ]}
        out = split_chapters.split_by_plan(lines, plan)
        self.assertEqual(len(out), 3)


class InlineRefRegexes(unittest.TestCase):
    """Los regex de referencias inline (rtf_to_markdown / pdf_chapters_to_markdown)
    no capturan números que NO son marcadores de nota. Se replican aquí porque esos
    módulos importan terceros (striprtf) que pueden no estar instalados."""

    @staticmethod
    def _rtf(s):
        return re.sub(r'\[(\d{1,3})\](?![(:])', lambda m: f'[^{m.group(1)}]', s)

    def test_rtf_bracketed_note(self):
        self.assertEqual(self._rtf("nota[3] aquí"), "nota[^3] aquí")

    def test_rtf_year_and_links_untouched(self):
        self.assertEqual(self._rtf("año[2024]"), "año[2024]")       # 4 dígitos
        self.assertEqual(self._rtf("link[1](url)"), "link[1](url)")  # enlace md
        self.assertEqual(self._rtf("def[1]: x"), "def[1]: x")        # definición

    @staticmethod
    def _glued(p, valid=(1, 11)):
        def repl(m):
            n = int(m.group(2))
            return m.group(0) if n not in valid else f"{m.group(1)}[^{n}]"
        return re.sub(r"(?<!\d)([^\s\d])(\d{1,3})(?=\W|$)", repl, p)

    def test_glued_marker_converted(self):
        self.assertEqual(self._glued("temperamento1 aparte"),
                         "temperamento[^1] aparte")

    def test_decimals_and_dates_untouched(self):
        self.assertEqual(self._glued("valor 1970.01 grados"), "valor 1970.01 grados")
        self.assertEqual(self._glued("27.11 grados"), "27.11 grados")


if __name__ == "__main__":
    unittest.main(verbosity=2)
