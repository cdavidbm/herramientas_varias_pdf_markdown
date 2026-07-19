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
import unicodedata
import unittest
from pathlib import Path

# tools/ al path para importar los scripts como módulos
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import forja_common
import md_to_pdf
import clean_markdown
import check_completeness
import split_chapters
import fix_ordinals
import pdf_rich_to_markdown


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


class FootnoteNumbering(unittest.TestCase):
    """md_to_pdf.footnote_numbering: cuando el original numera las notas POR OBRA,
    hay que reiniciarlas por capítulo para conservar su numeración (y poder citar
    «On Questions, nota 115» sin que baile)."""

    def test_page_default(self):
        self.assertIn("MakePerPage", md_to_pdf.footnote_numbering("page"))

    def test_chapter_resets_counter(self):
        self.assertIn(r"\counterwithin*{footnote}{chapter}",
                      md_to_pdf.footnote_numbering("chapter"))
        # y NO debe reiniciar además por página: se pisarían
        self.assertNotIn("MakePerPage", md_to_pdf.footnote_numbering("chapter"))

    def test_book_is_latex_default(self):
        self.assertEqual(md_to_pdf.footnote_numbering("book").strip(), "")

    def test_mode_reaches_the_preamble(self):
        pre = md_to_pdf.preamble("T", "A", "spanish", False, "", "chapter")
        self.assertIn(r"\counterwithin*{footnote}{chapter}", pre)
        self.assertNotIn("%%FOOTNOTE_NUMBERING%%", pre)   # el marcador se sustituyó


class StarSections(unittest.TestCase):
    """md_to_pdf.star_sections: las secciones de apéndice van SIN numerar (no
    arrastran el contador de capítulo) pero SÍ entran al índice con su página."""

    def test_stars_and_keeps_in_toc(self):
        out = md_to_pdf.star_sections(r"\section{Términos según los egipcios}")
        self.assertIn(r"\section*{Términos según los egipcios}", out)
        self.assertIn(r"\addcontentsline{toc}{section}{Términos según los egipcios}", out)

    def test_short_title_form_with_footnote(self):
        # pandoc emite \section[corto]{...} cuando el encabezado lleva una nota;
        # antes escapaba al starrado y salía numerado («0.4»).
        out = md_to_pdf.star_sections(r"\subsection[Cap 24]{Del capítulo 24\footnote{x}}")
        self.assertIn(r"\subsection*{", out)
        self.assertNotIn(r"\subsection[", out)
        self.assertIn(r"\addcontentsline{toc}{subsection}", out)

    def test_nested_braces_in_title(self):
        out = md_to_pdf.star_sections(r"\section{Tabla de \textit{monomoiria}}")
        self.assertIn(r"\section*{Tabla de \textit{monomoiria}}", out)

    def test_paragraph_not_in_toc(self):
        out = md_to_pdf.star_sections(r"\paragraph{Nota al margen}")
        self.assertIn(r"\paragraph*{Nota al margen}", out)
        self.assertNotIn(r"\addcontentsline", out)

    def test_footnote_in_heading_uses_short_for_toc(self):
        # pandoc emite \section[corto]{largo\footnote{...}} cuando el encabezado
        # markdown lleva [^N]. El índice debe usar el CORTO (sin la nota), y la
        # nota debe imprimirse UNA vez en el cuerpo (dentro del \section*).
        src = r"\section[Cap 48: On the Nodes]{Cap 48: On the Nodes\footnote{Domiciliis.}}"
        out = md_to_pdf.star_sections(src)
        self.assertIn(r"\section*{Cap 48: On the Nodes\footnote{Domiciliis.}}", out)
        self.assertIn(r"\addcontentsline{toc}{section}{Cap 48: On the Nodes}", out)
        # la nota NO debe colarse en el índice (doble disparo):
        self.assertNotIn(r"{toc}{section}{Cap 48: On the Nodes\footnote", out)

    def test_footnote_with_nested_braces_in_heading(self):
        # el \footnote del título contiene OTRO grupo con llaves: el escáner debe
        # cerrar en la llave correcta, no en la primera.
        src = r"\subsection[T]{T\footnote{Véase \textit{Carmen} IV.1}}"
        out = md_to_pdf.star_sections(src)
        self.assertIn(r"\subsection*{T\footnote{Véase \textit{Carmen} IV.1}}", out)
        self.assertIn(r"\addcontentsline{toc}{subsection}{T}", out)


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


class FixOrdinals(unittest.TestCase):
    """fix_ordinals: el OCR rompe los ordinales volados de escaneos («4 lh» → 4th).
    El sufijo se deriva del NÚMERO, no de la basura que dejó el OCR."""

    def test_suffix_rule(self):
        self.assertEqual(fix_ordinals.suffix(1), "st")
        self.assertEqual(fix_ordinals.suffix(2), "nd")
        self.assertEqual(fix_ordinals.suffix(3), "rd")
        self.assertEqual(fix_ordinals.suffix(4), "th")
        # 11/12/13 son 'th' aunque acaben en 1/2/3
        for n in (11, 12, 13):
            self.assertEqual(fix_ordinals.suffix(n), "th")

    def test_corrupt_forms(self):
        for src, want in [
            ("the 4 lh house", "the 4th house"),
            ("the 12 ,h house", "the 12th house"),
            ("the 9' h house", "the 9th house"),
            ("Venus in the 4' v house", "Venus in the 4th house"),
        ]:
            self.assertEqual(fix_ordinals.fix(src)[0], want)

    def test_ll_is_eleven(self):
        self.assertEqual(fix_ordinals.fix("the ll' h house")[0], "the 11th house")

    def test_capital_i_is_one(self):
        self.assertIn("1st", fix_ordinals.fix("the I 1 ', 2 nd houses")[0])

    def test_clean_spacing_normalized(self):
        self.assertEqual(fix_ordinals.fix("the 12 th house")[0], "the 12th house")

    def test_controls_untouched(self):
        # horas, fechas, cifras y palabras con 'll' NO se tocan
        for s in ("8 41 00 PM EET -02:00:00", "Feb 12 1966",
                  "He earned 500 dollars in 2015", "all the still water"):
            self.assertEqual(fix_ordinals.fix(s)[0], s)

    def test_out_of_range_untouched(self):
        # solo 1-31: un año no es un ordinal de casa/día
        self.assertEqual(fix_ordinals.fix("in 2015 th")[0], "in 2015 th")

    def test_count_reported(self):
        _, n = fix_ordinals.fix("the 4 lh and the 9' h houses")
        self.assertEqual(n, 2)


class FakeChar:
    """Un LTChar de mentira: a `find_gutter` solo le importan x0/x1/y0 y el texto,
    así que se puede probar la geometría sin pdfminer ni un PDF de verdad."""

    def __init__(self, ch: str, x0: float, y0: float, w: float = 5.0):
        self.x0, self.x1, self.y0 = x0, x0 + w, y0
        self.size, self.fontname = 10.0, "Times"
        self._t = ch

    def get_text(self):
        return self._t


def _run(y: float, x0: float, x1: float):
    """Caracteres pegados de x0 a x1 (sin huecos internos)."""
    return [FakeChar("a", float(x), y) for x in range(int(x0), int(x1), 5)]


def _rows(specs):
    """[(y, [(x0,x1), …]), …] -> filas como las arma cluster_rows."""
    out = []
    for y, runs in specs:
        cs = [c for x0, x1 in runs for c in _run(y, x0, x1)]
        out.append((float(y), sorted(cs, key=lambda c: c.x0)))
    return out


class FindGutter(unittest.TestCase):
    """pdf_rich_to_markdown.find_gutter: separa texto a 2 columnas (original y
    traducción en paralelo) sin fundirlas, y NO se inventa columnas en prosa."""

    def test_two_columns_detected(self):
        rows = _rows([(600 - 14 * i, [(100, 300), (310, 500)]) for i in range(20)])
        g = pdf_rich_to_markdown.find_gutter(rows, 100.0, 500.0)
        self.assertIsNotNone(g)
        self.assertTrue(300 <= g <= 310, f"canal fuera del hueco: {g}")

    def test_single_column_is_none(self):
        rows = _rows([(600 - 14 * i, [(100, 500)]) for i in range(20)])
        self.assertIsNone(pdf_rich_to_markdown.find_gutter(rows, 100.0, 500.0))

    def test_justified_prose_is_not_a_gutter(self):
        # El falso positivo real: al justificar se estiran los espacios y unas
        # cuantas filas tienen un hueco ancho cerca del centro por casualidad.
        # Lo que lo delata es que las DEMÁS filas cruzan esa x tan tranquilas.
        specs = []
        for i in range(20):
            y = 600 - 14 * i
            if i % 3 == 0:
                specs.append((y, [(100, 300), (308, 500)]))   # hueco casual
            else:
                specs.append((y, [(100, 500)]))               # cruza el «canal»
        self.assertIsNone(pdf_rich_to_markdown.find_gutter(_rows(specs), 100.0, 500.0))

    def test_full_width_footnotes_below_columns_do_not_break_detection(self):
        # Las notas al pie cruzan la página entera, pero van DEBAJO del bloque a
        # dos columnas: no deben impedir que se detecte el canal.
        specs = [(600 - 14 * i, [(100, 300), (310, 500)]) for i in range(20)]
        specs += [(300 - 12 * j, [(100, 500)]) for j in range(4)]
        g = pdf_rich_to_markdown.find_gutter(_rows(specs), 100.0, 500.0)
        self.assertIsNotNone(g, "las notas al pie tumbaron la detección")

    def test_gutter_must_be_central(self):
        # Un hueco pegado al margen es sangría o una columna de cifras, no un canal.
        rows = _rows([(600 - 14 * i, [(100, 140), (150, 500)]) for i in range(20)])
        self.assertIsNone(pdf_rich_to_markdown.find_gutter(rows, 100.0, 500.0))


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


class ForjaCommonSlugify(unittest.TestCase):
    """UNA slugify para todo el repo. Antes eran 11 copias en 3 variantes
    incompatibles: el mismo capítulo salía `Bhāva_` o `Bhava_` según el script."""

    def test_transliterations_survive(self):
        # El bug que motivó el módulo: NFKD→ASCII destruía el sánscrito/griego.
        self.assertEqual(forja_common.slugify("Bhāva"), "Bhāva")
        self.assertEqual(forja_common.slugify("Περὶ κράσεως"), "Περὶ_κράσεως")

    def test_ascii_only_is_opt_in(self):
        self.assertEqual(forja_common.slugify("Bhāva", ascii_only=True), "Bhava")

    def test_nfc_normalised(self):
        # «Döser» en DESCOMPUESTO (O + U+0308) hace fallar a pdfinfo/pdftotext.
        nfd = "Do" + "̈" + "ser"
        out = forja_common.slugify(nfd)
        self.assertEqual(out, "Döser")
        self.assertEqual(out, unicodedata.normalize("NFC", out))
        self.assertNotIn("̈", out)

    def test_idempotent(self):
        for s in ("1. Judío de Galilea", "ANEXO  2 — Criterios", "a - b"):
            once = forja_common.slugify(s)
            self.assertEqual(forja_common.slugify(once), once, f"no idempotente: {s}")

    def test_separators_and_punctuation(self):
        self.assertEqual(forja_common.slugify("1. Judío de Galilea"),
                         "1_Judío_de_Galilea")
        self.assertEqual(forja_common.slugify("a   b"), "a_b")

    def test_hyphen_kept_inside_arabic_transliteration(self):
        # En `al-Mawālīd` el guion es parte del nombre, no un separador.
        self.assertEqual(forja_common.slugify("Kitāb al-Mawālīd"), "Kitāb_al-Mawālīd")
        self.assertEqual(forja_common.slugify("al-Bīrūnī"), "al-Bīrūnī")

    def test_fallback_when_nothing_survives(self):
        # Un título de puros glifos astrológicos no puede dar nombre vacío.
        self.assertEqual(forja_common.slugify("♄♃♂"), "section")
        self.assertEqual(forja_common.slugify(""), "section")
        self.assertEqual(forja_common.slugify("♄", fallback="cap"), "cap")

    def test_maxlen_and_no_trailing_separator(self):
        self.assertEqual(forja_common.slugify("a" * 200, maxlen=10), "a" * 10)
        self.assertFalse(forja_common.slugify("Capítulo uno", maxlen=9).endswith("_"))

    def test_lower(self):
        self.assertEqual(forja_common.slugify("Judío DE Galilea", lower=True),
                         "judío_de_galilea")


class ForjaCommonLoadPlan(unittest.TestCase):
    """load_plan normaliza el esquema: `pages` ⇄ `start`/`end`, y RESPETA `slug`."""

    def _plan(self, obj):
        import json as _json
        import tempfile
        d = Path(tempfile.mkdtemp())
        p = d / "plan.json"
        p.write_text(_json.dumps(obj), encoding="utf-8")
        return forja_common.load_plan(p)

    def test_pages_to_scalar(self):
        plan = self._plan({"source": "x.pdf",
                           "sections": [{"title": "T", "pages": [11, 20]}]})
        sec = plan["sections"][0]
        self.assertEqual((sec["start"], sec["end"]), (11, 20))

    def test_scalar_to_pages(self):
        plan = self._plan({"source": "x.pdf",
                           "sections": [{"title": "T", "start": 11, "end": 20}]})
        self.assertEqual(plan["sections"][0]["pages"], [11, 20])

    def test_null_end_means_to_the_end(self):
        plan = self._plan({"source": "x.pdf",
                           "sections": [{"title": "T", "pages": [4, None]}]})
        self.assertIsNone(plan["sections"][0]["end"])

    def test_explicit_slug_is_honoured(self):
        # split_pdf/pdf_sections lo descartaban: pedías 01_Prefacio, salía 00_Prefacio.
        plan = self._plan({"source": "x.pdf",
                           "sections": [{"slug": "01_Prefacio", "title": "Prefacio",
                                         "pages": [9, 10]}]})
        self.assertEqual(plan["sections"][0]["slug"], "01_Prefacio")

    def test_slug_derived_when_absent(self):
        plan = self._plan({"source": "x.pdf",
                           "sections": [{"title": "Bhāva", "pages": [1, 2]}]})
        self.assertEqual(plan["sections"][0]["slug"], "01_Bhāva")


class RtfDeriveSections(unittest.TestCase):
    """`rtf_to_markdown.py libro.rtf` deriva las secciones del layout del RTF (lo
    que CLAUDE.md promete). El plan a mano es opcional. Se stubbea striprtf porque
    la lógica de derivación no lo necesita y la suite no debe pedir terceros."""

    @classmethod
    def setUpClass(cls):
        import types
        if "striprtf.striprtf" not in sys.modules:
            pkg = types.ModuleType("striprtf")
            mod = types.ModuleType("striprtf.striprtf")
            mod.rtf_to_text = lambda *a, **k: ""
            pkg.striprtf = mod
            sys.modules.setdefault("striprtf", pkg)
            sys.modules["striprtf.striprtf"] = mod
        import rtf_to_markdown
        cls.rtf = rtf_to_markdown

    # Layout ePubLibre: cap = número suelto + título en MAYÚSCULAS; cuerpo con tab.
    LINES = [
        "PRESENTACIÓN",
        "\tProsa sin notas.",
        "1",
        "JUDÍO DE GALILEA",
        "\tPárrafo con nota[1].",
        "2",
        "LA VÍA DEL ORO",
        "\tOtro capítulo, nota[1].",
        "Notas",
        "[1]", "Nota del uno. <<",
        "[1]", "Nota del dos. <<",
    ]

    def _derive(self, pool=(({1: "a"}), ({1: "b"}))):
        return self.rtf.derive_sections(self.LINES, "Notas", list(pool))

    def test_finds_every_section(self):
        titles = [s["title"] for s in self._derive()]
        self.assertEqual(titles, ["Presentación", "1. Judío de Galilea",
                                  "2. La Vía del Oro"])

    def test_pool_stops_the_body(self):
        # Ninguna sección puede alcanzar la línea del pool: sería aparato como prosa.
        pool_at = self.LINES.index("Notas")
        for sec in self._derive():
            self.assertLess(sec["ranges"][0][1], pool_at)

    def test_notes_go_to_the_chapters_that_cite_them(self):
        secs = self._derive()
        self.assertEqual([s["notes"] for s in secs], [[], [1], [2]])

    def test_titlecase_keeps_function_words_lowercase(self):
        self.assertEqual(self.rtf.titlecase("LA VÍA DEL ORO"), "La Vía del Oro")
        self.assertEqual(self.rtf.titlecase("JUDÍO DE GALILEA"), "Judío de Galilea")

    def test_unknown_layout_derives_nothing(self):
        # Sin señales, mejor 0 secciones (error claro) que una falsa.
        self.assertEqual(self.rtf.derive_sections(["\tsolo prosa suelta."],
                                                  "Notas", []), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
