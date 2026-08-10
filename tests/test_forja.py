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
import epub_to_markdown
import citas_en_bloque
import cose_parrafos
import traducir_libro
import check_completeness
import split_chapters
import fix_ordinals
import pdf_rich_to_markdown
import crop_figure
import agy_consolidate
import agy_translate


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


class StripEmptyNoteHeading(unittest.TestCase):
    """md_to_pdf.strip_empty_note_heading: el título «Notas» sobre puras definiciones
    `[^x]:` sale vacío en el PDF (notas al pie) -> se quita el título, se dejan las defs."""

    def test_drops_heading_keeps_defs(self):
        src = "Cuerpo.\n\n## Notas\n\n[^1]: uno\n[^2]: dos\n"
        out = md_to_pdf.strip_empty_note_heading(src)
        self.assertNotIn("## Notas", out)
        self.assertIn("[^1]: uno", out)
        self.assertIn("[^2]: dos", out)

    def test_english_notes_and_deeper_level(self):
        self.assertNotIn("# Notes", md_to_pdf.strip_empty_note_heading("x\n\n### Notes\n\n[^a]: y\n"))

    def test_keeps_heading_with_real_content(self):
        # un «Notas» seguido de prosa real NO se toca (no es el bloque de aparato)
        src = "## Notas\n\nEsto es prosa, no una definición.\n"
        self.assertIn("## Notas", md_to_pdf.strip_empty_note_heading(src))

    def test_unrelated_heading_untouched(self):
        src = "## Capítulo\n\n[^1]: def\n"
        self.assertIn("## Capítulo", md_to_pdf.strip_empty_note_heading(src))


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


class CropFigureBbox(unittest.TestCase):
    """crop_figure.parse_bbox: la caja fraccionaria se valida antes de recortar."""

    def test_valid_bbox(self):
        self.assertEqual(crop_figure.parse_bbox("0.2,0.26,0.8,0.64"),
                         (0.2, 0.26, 0.8, 0.64))

    def test_tolerates_spaces(self):
        self.assertEqual(crop_figure.parse_bbox(" 0.0, 0.1 ,1.0, 0.9 "),
                         (0.0, 0.1, 1.0, 0.9))

    def test_wrong_arity_rejected(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            crop_figure.parse_bbox("0.1,0.2,0.3")

    def test_out_of_range_rejected(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            crop_figure.parse_bbox("0.1,0.2,1.3,0.9")

    def test_inverted_box_rejected(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            crop_figure.parse_bbox("0.8,0.2,0.3,0.9")  # x1<=x0

    def test_nonnumeric_rejected(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            crop_figure.parse_bbox("a,b,c,d")


class AgyConsolidate(unittest.TestCase):
    """agy_consolidate: separar notas, unir cuerpos a través del salto de página."""

    def test_parse_pages(self):
        raw = "=== pdf001-001.png ===\nHola\n=== pdf002-002.png ===\nMundo\n"
        pages = agy_consolidate.parse_pages(raw)
        self.assertEqual(len(pages), 2)
        self.assertIn("Hola", pages[0])
        self.assertIn("Mundo", pages[1])

    def test_split_body_notes_separates_and_joins_continuation(self):
        lines = ["Cuerpo con marca.[^1]", "", "[^1]: definición que sigue",
                 "en una segunda línea."]
        body, notes = agy_consolidate.split_body_notes(lines)
        self.assertEqual(body[0], "Cuerpo con marca.[^1]")
        self.assertEqual(notes, [(1, "definición que sigue en una segunda línea.")])

    def test_join_dehyphenates_across_pages(self):
        # última línea acaba en "-" → une sin espacio ni guion
        out = agy_consolidate.join_bodies([["una parte tradi-"], ["cional del texto."]])
        self.assertIn("tradicional del texto.", "\n".join(out))

    def test_join_continues_sentence_across_pages(self):
        # sin puntuación terminal → une con espacio
        out = agy_consolidate.join_bodies([["for centuries. In"], ["ITA, I inserted"]])
        self.assertEqual(out, ["for centuries. In ITA, I inserted"])

    def test_join_keeps_separate_paragraphs(self):
        # termina en punto → párrafo nuevo (línea en blanco entre medias)
        out = agy_consolidate.join_bodies([["Fin del párrafo."], ["Nuevo párrafo."]])
        self.assertEqual(out, ["Fin del párrafo.", "", "Nuevo párrafo."])

    def test_heading_not_glued_to_previous(self):
        out = agy_consolidate.join_bodies([["texto sin punto final"], ["## §2: Título"]])
        self.assertEqual(out, ["texto sin punto final", "", "## §2: Título"])


class AgyTranslate(unittest.TestCase):
    """agy_translate: separar cuerpo/notas y trocear por párrafos sin partir."""

    def test_split_body_defs(self):
        md = ("# Libro\n\n## §1: T\n\nUn párrafo con nota.[^1]\n\n"
              "![fig](../figuras/fig001.png)\n\n"
              "[^1]: definición uno\n[^2]: definición dos\n")
        body, defs, _tail = agy_translate.split_body_defs(md)
        self.assertIn("Un párrafo con nota.[^1]", body)
        self.assertIn("![fig]", body)
        self.assertNotIn("[^1]: definición", body)
        self.assertEqual(defs, "[^1]: definición uno\n[^2]: definición dos")

    def test_split_no_defs(self):
        md = "# Solo\n\nCuerpo sin notas.\n"
        body, defs, _tail = agy_translate.split_body_defs(md)
        self.assertEqual(defs, "")
        self.assertIn("Cuerpo sin notas.", body)

    def test_chunk_respects_paragraphs_and_size(self):
        text = "\n\n".join(f"parrafo {i} con varias palabras aqui" for i in range(6))
        chunks = agy_translate.chunk_paragraphs(text, max_words=12)
        # ningún trozo parte un párrafo; recomponer da el texto original
        self.assertEqual("\n\n".join(chunks).split(), text.split())
        self.assertGreater(len(chunks), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class EpubEmphasisAndPool(unittest.TestCase):
    """Calibre/Kindle EPUBs: emphasis by CSS class y pool de notas plano.

    Medido en *Astral High Magic* (Warnock, Renaissance Astrology 2012).
    """

    def test_styles_from_css(self):
        css = """
        .italic { font-style: italic; }
        .bold { font-weight: bold }
        .calibre12 { font-style: italic; font-size: 1em }
        .peso { font-weight: 700 }
        .nada { color: red }
        p.tit, span.tit2 { font-weight: bold }
        .a .b { font-style: italic }
        """
        ital, bold = epub_to_markdown.styles_from_css(css)
        self.assertEqual(ital, {"italic", "calibre12"})
        self.assertEqual(bold, {"bold", "peso", "tit", "tit2"})
        # Un selector DESCENDIENTE no debe aportar clases: sobre-aplicaría.
        self.assertNotIn("b", ital)

    def test_italic_span_becomes_markdown(self):
        html = ('<p>Cita de <span class="italic">Picatrix</span> y de '
                '<span class="bold">Thabit</span>.</p>')
        conv = epub_to_markdown.Converter(italic_classes={"italic"},
                                          bold_classes={"bold"})
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("*Picatrix*", out)
        self.assertIn("**Thabit**", out)

    def test_emphasis_marks_outside_whitespace(self):
        # `*foo *` con el espacio DENTRO no lo renderiza pandoc.
        html = '<p>ver <span class="italic">De Imaginibus </span>ahora</p>'
        conv = epub_to_markdown.Converter(italic_classes={"italic"})
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("*De Imaginibus* ahora", out)

    def test_source_newline_does_not_break_line(self):
        # Un salto de línea del FUENTE es espacio en HTML; conservarlo dejaba la
        # llamada de nota sola en su renglón (pandoc la haría párrafo aparte).
        html = '<p>fin de la frase.\n<sup><a href="pool.html#n1">5</a></sup>\n</p>'
        conv = epub_to_markdown.Converter(footnote_lookup={"n1": "cuerpo"},
                                          footnote_file_marker="pool.html")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("frase. [^1]", out.replace("\n", " "))
        self.assertNotRegex(out, r"(?m)^\[\^1\]")

    def test_pool_by_a_id_split(self):
        # Las 68 notas del libro viven en UN solo <p>, separadas por <br/>.
        html = ('<p class="calibre_14">\n'
                '<a id="fp1"></a>1. <span class="italic">Centiloquium</span> af. 9. '
                '<span>[</span><a href="c.html#x">return</a><span>]</span><br/><br/>\n'
                '<a id="fp2"></a>2. Segunda nota. '
                '<span>[</span><a href="c.html#y">return</a><span>]</span><br/><br/>\n'
                '</p>')
        got = epub_to_markdown.load_footnote_lookup(
            html, fmt="by_a_id_split", italic_classes={"italic"})
        self.assertEqual(set(got), {"fp1", "fp2"})
        self.assertEqual(got["fp2"], "Segunda nota.")
        # La cursiva del pool se conserva y el "[return]" desaparece entero.
        self.assertIn("*Centiloquium*", got["fp1"])
        self.assertNotIn("return", got["fp1"])
        self.assertNotIn("[", got["fp1"])

    def test_bold_paragraph_repeating_title_is_dropped(self):
        html = '<p class="c3"><span class="bold">Chapter 1</span></p><p>Texto.</p>'
        conv = epub_to_markdown.Converter(bold_classes={"bold"},
                                          section_title="Chapter 1")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertNotIn("**Chapter 1**", out)
        self.assertIn("Texto.", out)

    def test_heading_paragraphs_promotes_and_strips_bold(self):
        # Dos <span> en negrita adyacentes dejaban `**` en medio del título.
        html = ('<p class="c3"><span class="sub"><span class="bold">Version I: </span>'
                '</span><span class="sub"><span class="bold">Part Three</span></span></p>')
        conv = epub_to_markdown.Converter(bold_classes={"bold"},
                                          heading_paragraphs={"sub": 2})
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("## Version I: Part Three", out)
        self.assertNotIn("*", out)

    def test_images_kept_when_image_dir_set(self):
        html = '<p><img src="images/00002.jpg" alt="Carta"/></p>'
        conv = epub_to_markdown.Converter(image_dir="imagenes")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("![Carta](imagenes/00002.jpg)", out)
        self.assertEqual(conv.used_images, {"images/00002.jpg"})
        # Sin image_dir se mantiene el comportamiento anterior (se descartan).
        conv2 = epub_to_markdown.Converter()
        self.assertNotIn("![", "\n".join(conv2.convert_file(html, filename="x.html")))

    def test_image_skip(self):
        html = '<p><img src="images/calibre_cover.jpg"/></p>'
        conv = epub_to_markdown.Converter(image_dir="img",
                                          image_skip={"calibre_cover.jpg"})
        self.assertNotIn("![", "\n".join(conv.convert_file(html, filename="x.html")))


class CitasEnBloque(unittest.TestCase):
    """Párrafos que son una cita entera → `>`. Medido en *Astral High Magic*."""

    def test_cita_simple_pierde_las_comillas_envolventes(self):
        md = 'Plotino dice,\n\n"Creo, por tanto, que aquellos sabios."[^4]\n'
        out, st = citas_en_bloque.process(md)
        self.assertIn("> Creo, por tanto, que aquellos sabios.[^4]", out)
        self.assertNotIn('"', out)
        self.assertEqual(st["cita"], 1)

    def test_comillas_interiores_se_respetan(self):
        md = '"Dijo el rey "basta" y calló."\n'
        out, _ = citas_en_bloque.process(md)
        self.assertEqual(out.strip(), '> Dijo el rey "basta" y calló.')

    def test_cita_multiparrafo_lleva_mayor_en_el_separador(self):
        # Sin `>` en el renglón separador, pandoc ve DOS citas distintas.
        md = ('"Primer párrafo de la cita que no cierra\n\n'
              'Segundo párrafo, sigue dentro\n\n'
              'y aquí cierra la cita."\n\nProsa del autor.\n')
        out, st = citas_en_bloque.process(md)
        self.assertIn("> Primer párrafo", out)
        self.assertIn("\n>\n", out)
        self.assertIn("> y aquí cierra la cita.", out)
        self.assertIn("\nProsa del autor.", out)
        self.assertNotIn("> Prosa del autor", out)
        self.assertEqual(st["cita_multiparrafo"], 2)

    def test_cita_que_cierra_a_media_linea_se_parte(self):
        md = ('"…living Images."[^45] Agrippa goes on to note that timing matters,\n')
        out, st = citas_en_bloque.process(md)
        self.assertEqual(st["cita_partida"], 1)
        self.assertIn("> …living Images.[^45]", out)
        self.assertRegex(out, r"(?m)^Agrippa goes on to note")

    def test_no_toca_encabezados_listas_ni_notas(self):
        md = '# Título\n\n- "un ítem entrecomillado"\n\n[^1]: "una definición"\n'
        out, st = citas_en_bloque.process(md)
        self.assertEqual(st["cita"], 0)
        self.assertNotIn(">", out)

    def test_llamadas_de_nota_se_pegan(self):
        t, n = citas_en_bloque.glue_footnotes("la ciencia de las imágenes [^1] y luego")
        self.assertIn("imágenes[^1]", t)
        self.assertEqual(n, 1)

    def test_punto_espurio_tras_la_llamada(self):
        t, _ = citas_en_bloque.glue_footnotes('miserable."[^3]. Y sigue')
        self.assertIn('miserable."[^3] Y sigue', t)

    def test_encabezado_no_se_come_el_renglon_en_blanco(self):
        # La trampa: `\s*$` en multilínea pega el encabezado al párrafo.
        out = citas_en_bloque.fix_headings("## Version I:\n\nThabit dijo\n")
        self.assertEqual(out, "## Version I\n\nThabit dijo\n")

    def test_encabezado_ya_pegado_se_separa(self):
        out = citas_en_bloque.fix_headings("## Versión I\nThabit dijo\n")
        self.assertEqual(out, "## Versión I\n\nThabit dijo\n")

    def test_comillas_tipograficas_alternan(self):
        self.assertEqual(citas_en_bloque.curl_quotes('dijo "hola" y "adiós"'),
                         'dijo “hola” y “adiós”')

    def test_idempotente(self):
        md = 'Plotino dice,\n\n"Creo que sí."[^4]\n\nY sigue.\n'
        a, _ = citas_en_bloque.process(md)
        b, _ = citas_en_bloque.process(a)
        self.assertEqual(a, b)


class DensidadJFIF(unittest.TestCase):
    """Un JPEG con densidad 1 dpi desaparece del PDF en silencio."""

    def _jpeg(self, units, xd, yd):
        import struct
        # JPEG mínimo: SOI + APP0 (JFIF) + EOI. Basta para el parcheo del APP0.
        app0 = b"JFIF\x00" + b"\x01\x02" + bytes([units]) + struct.pack(">HH", xd, yd) + b"\x00\x00"
        return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", len(app0) + 2) + app0 + b"\xff\xd9"

    def test_corrige_densidad_1dpi(self):
        import tempfile, struct
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "carta.jpg"
            p.write_bytes(self._jpeg(1, 1, 1))
            tocadas = md_to_pdf.check_image_density([p], fix=True, dpi=96)
            self.assertEqual(len(tocadas), 1)
            b = p.read_bytes()
            o = 2 + 2 + 2 + 5 + 2          # SOI + marcador + longitud + 'JFIF\0' + versión
            self.assertEqual(b[o], 1)
            self.assertEqual(struct.unpack(">HH", b[o + 1:o + 5]), (96, 96))
            # Idempotente: una segunda pasada ya no la toca.
            self.assertEqual(md_to_pdf.check_image_density([p], fix=True), [])

    def test_unidades_cero_tambien_es_absurdo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jpg"
            p.write_bytes(self._jpeg(0, 100, 100))
            self.assertEqual(len(md_to_pdf.check_image_density([p], fix=True)), 1)

    def test_no_toca_la_densidad_correcta(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ok.jpg"
            p.write_bytes(self._jpeg(1, 72, 72))
            antes = p.read_bytes()
            self.assertEqual(md_to_pdf.check_image_density([p], fix=True), [])
            self.assertEqual(p.read_bytes(), antes)

    def test_solo_avisa_si_fix_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "y.jpg"
            p.write_bytes(self._jpeg(1, 1, 1))
            antes = p.read_bytes()
            self.assertEqual(len(md_to_pdf.check_image_density([p], fix=False)), 1)
            self.assertEqual(p.read_bytes(), antes)

    def test_subtitulo_admite_cursiva_markdown(self):
        pre = md_to_pdf.preamble("T", "A", "spanish", False,
                                 subtitles=["*De Imaginibus*, el libro"])
        self.assertIn(r"\emph{De Imaginibus}", pre)
        self.assertNotIn("*De Imaginibus*", pre)


class EpubAgrippaPurdue(unittest.TestCase):
    """Edición Purdue de Agripa (Inner Traditions): pool `by_p_id` y título partido."""

    def test_pool_ftn_se_detecta_por_el_nombre(self):
        import build_plan
        for n in ("9781644114179_ftn.xhtml", "book_tn.xhtml", "ftn.xhtml",
                  "notes.xhtml", "Footnote.xhtml"):
            self.assertTrue(build_plan.FOOTNOTE_NAME.search(n), n)
        # …sin cazar palabras corrientes que lo contengan.
        for n in ("chapter.xhtml", "fiction.xhtml", "content.opf"):
            self.assertFalse(build_plan.FOOTNOTE_NAME.search(n), n)

    def test_by_p_id_quita_el_marcador_enlazado_del_principio(self):
        html = ('<p class="ntstx" id="nt36"><a href="c05.xhtml#nr36"><b>1</b></a>. '
                'Ref. Pico, <em>Heptaplus</em>.</p>')
        got = epub_to_markdown.load_footnote_lookup(html, fmt="by_p_id")
        self.assertEqual(got["nt36"], "Ref. Pico, *Heptaplus*.")

    def test_sup_con_ancla_vacia_delante(self):
        # El <sup> lleva DOS <a>: el ancla de destino (vacía) y el enlace real.
        # Quedarse con el primero dejaba un `^` suelto: `superior,^[^1]`.
        html = ('<p>su superior,<sup><a id="nr36"></a>'
                '<a href="pool.xhtml#nt36">1</a></sup> acepta</p>')
        conv = epub_to_markdown.Converter(footnote_lookup={"nt36": "cuerpo"},
                                          footnote_file_marker="pool.xhtml")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("su superior,[^1] acepta", out)
        self.assertNotIn("^[^1]", out)

    def test_titulo_partido_en_dos_parrafos_no_se_duplica(self):
        html = ('<p class="chn">Chapter 1</p><p class="cht">How magicians collect'
                ' virtues.</p><p>There is a threefold world.</p>')
        conv = epub_to_markdown.Converter(
            section_title="Chapter 1. How magicians collect virtues.")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertNotIn("Chapter 1\n", out)
        self.assertNotIn("How magicians collect virtues.", out)
        self.assertIn("There is a threefold world.", out)

    def test_no_suprime_prosa_que_repita_el_titulo_mas_adelante(self):
        # La guarda es la POSICIÓN: solo la cabecera del documento.
        html = ("<p>uno</p><p>dos</p><p>tres</p><p>cuatro</p><p>cinco</p>"
                "<p>seis</p><p>El fuego</p>")
        conv = epub_to_markdown.Converter(section_title="El fuego")
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("El fuego", out)

    def test_blockquote_sin_mayores_vacios_sobrantes(self):
        got = epub_to_markdown.tidy_blockquotes(
            [">", ">", "> texto", ">", ">", "> más", ">", ">"])
        self.assertEqual(got, ["> texto", ">", "> más"])

    def test_enfasis_con_espacio_interior(self):
        # `in<em> Dionysii</em>` daría `in* Dionysii*`, que pandoc imprime crudo.
        html = "<p>ref. Ficino, in<em> Dionysii 1049.</em></p>"
        conv = epub_to_markdown.Converter()
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("in *Dionysii 1049.*", out)


class TraducirLibro(unittest.TestCase):
    """Verificación por archivo de una traducción de libro."""

    def test_tabla_desmontada_se_detecta(self):
        en = "Texto.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        # El motor funde dos columnas: el ratio no se mueve y las notas cuadran.
        es = "Texto.\n\n| a b |\n|---|\n| 1 2 |\n| 3 4 |\n"
        self.assertTrue(any("tabla" in f for f in traducir_libro.verificar_tablas(en, es)))

    def test_renglon_de_tabla_perdido(self):
        en = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        es = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        self.assertTrue(traducir_libro.verificar_tablas(en, es))

    def test_tabla_traducida_bien_pasa(self):
        en = "| Name | Value |\n|---|---|\n| Fire | Heat |\n"
        es = "| Nombre | Valor |\n|---|---|\n| Fuego | Calor |\n"
        self.assertEqual(traducir_libro.verificar_tablas(en, es), [])

    def test_verificar_detecta_llamada_perdida(self):
        en = "Uno[^1] y dos[^2].\n\n[^1]: a\n[^2]: b\n"
        es = "Uno[^1] y dos.\n\n[^1]: a\n[^2]: b\n"
        self.assertTrue(any("llamadas" in f for f in traducir_libro.verificar(en, es)))

    def test_verificar_acepta_una_traduccion_correcta(self):
        en = "# T\n\nOne[^1] two three four five.\n\n[^1]: a short note\n"
        es = "# T\n\nUno[^1] dos tres cuatro cinco.\n\n[^1]: una nota breve\n"
        self.assertEqual(traducir_libro.verificar(en, es), [])


class ImagenesInline(unittest.TestCase):
    """Una imagen diminuta es un glifo a media frase, no una lámina."""

    def _png(self, alto):
        import struct, zlib
        ihdr = struct.pack(">II", 40, alto) + b"\x08\x02\x00\x00\x00"
        chunk = b"IHDR" + ihdr
        return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk
                + struct.pack(">I", zlib.crc32(chunk)))

    def test_glifo_pequeno_va_en_linea(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "images").mkdir()
            (root / "images/g.png").write_bytes(self._png(20))
            conv = epub_to_markdown.Converter(image_dir="imagenes", image_root=root,
                                              inline_img_px=60)
            html = '<p>de los cuernos <img src="images/g.png"/> , y de la cola</p>'
            out = "\n".join(conv.convert_file(html, filename="x.html"))
            # todo en un renglón: la frase no se parte
            self.assertRegex(out, r"cuernos !\[\]\(imagenes/g\.png\)")
            self.assertNotIn("\n\n![", out)

    def test_lamina_grande_sigue_siendo_bloque(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "images").mkdir()
            (root / "images/lam.png").write_bytes(self._png(900))
            conv = epub_to_markdown.Converter(image_dir="imagenes", image_root=root,
                                              inline_img_px=60)
            html = '<p>Texto.</p><p><img src="images/lam.png"/></p>'
            out = "\n".join(conv.convert_file(html, filename="x.html"))
            self.assertIn("\n\n![](imagenes/lam.png)", out)

    def test_sin_image_root_no_mide_y_deja_bloque(self):
        conv = epub_to_markdown.Converter(image_dir="im", inline_img_px=60)
        html = '<p>a <img src="images/g.png"/> b</p>'
        out = "\n".join(conv.convert_file(html, filename="x.html"))
        self.assertIn("![](im/g.png)", out)

    def test_huella_detecta_origen_cambiado(self):
        a = traducir_libro.huella("Un texto.")
        self.assertEqual(a, traducir_libro.huella("Un texto."))
        self.assertNotEqual(a, traducir_libro.huella("Un texto cambiado."))

    def test_metricas_no_borran_nada(self):
        # El resultado traducido se SOBRESCRIBE; nunca hay que borrarlo para
        # rehacerlo. Aquí solo se comprueba que las métricas no tocan disco.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.md"
            f.write_text("hola")
            traducir_libro.metricas("hola", "hola")
            self.assertTrue(f.is_file())


class HebreoYSangria(unittest.TestCase):
    """Hebreo en el PDF y párrafos por sangría de primera línea."""

    def test_hebrew_font_declara_el_locale(self):
        import subprocess, sys, tempfile, os
        # Se comprueba en el preámbulo generado, sin compilar.
        pre = md_to_pdf.preamble("T", "", "spanish", False, arabfont=
            "\\babelprovide[import=he, onchar=ids fonts]{hebrew}\n"
            "\\babelfont[hebrew]{rm}[Script=Hebrew]{Noto Serif Hebrew}")
        self.assertIn("import=he", pre)
        self.assertIn("Script=Hebrew", pre)
        # bidi=basic ya venía: es lo que reordena de derecha a izquierda.
        self.assertIn("bidi=basic", pre)

    def test_arabe_y_hebreo_conviven(self):
        pre = md_to_pdf.preamble("T", "", "spanish", False, arabfont=
            "\\babelprovide[import=ar, onchar=ids fonts]{arabic}\n"
            "\\babelprovide[import=he, onchar=ids fonts]{hebrew}")
        self.assertIn("import=ar", pre)
        self.assertIn("import=he", pre)

    def test_notas_sin_traducir_se_detectan(self):
        notas = "\n".join(f"[^{i}]: Although it could certainly be argued that this "
                          f"phenomenon remains universal beyond metaphysics, number {i}."
                          for i in range(1, 9))
        en = "Cuerpo.\n\n" + notas + "\n"
        # El motor devolvió el bloque de notas INTACTO: cuerpo traducido, notas no.
        es = "Cuerpo traducido.\n\n" + notas + "\n"
        self.assertTrue(traducir_libro.verificar_notas_traducidas(en, es))

    def test_notas_traducidas_pasan(self):
        en = "\n".join(f"[^{i}]: Although it could certainly be argued that this "
                        f"phenomenon remains universal beyond metaphysics, number {i}."
                        for i in range(1, 9))
        es = "\n".join(f"[^{i}]: Aunque ciertamente podría sostenerse que este "
                        f"fenómeno permanece universal más allá de la metafísica, {i}."
                        for i in range(1, 9))
        self.assertEqual(traducir_libro.verificar_notas_traducidas(en, es), [])

    def test_sin_notas_no_opina(self):
        self.assertEqual(traducir_libro.verificar_notas_traducidas("a", "b"), [])

    def test_el_ratio_no_ve_las_notas_sin_traducir(self):
        # Por qué hace falta el control: el ratio EXCLUYE las definiciones.
        notas = "\n".join(f"[^{i}]: A rather long English footnote which was simply "
                          f"left completely untranslated right here, number {i}."
                          for i in range(1, 9))
        en = "Uno dos tres.\n\n" + notas + "\n"
        es = "Uno dos tres.\n\n" + notas + "\n"
        self.assertNotIn("ratio", " ".join(traducir_libro.verificar(en, es)))
        self.assertTrue(any("NOTAS" in f for f in traducir_libro.verificar(en, es)))

    def test_valla_de_codigo_se_detecta(self):
        en = "# T\n\nUn párrafo con nota.[^1]\n\n[^1]: nota\n"
        es = "```markdown\n# T\n\nUn párrafo con nota.[^1]\n```\n\n[^1]: nota\n"
        self.assertTrue(any("VALLA" in f for f in traducir_libro.verificar(en, es)))

    def test_valla_legitima_del_original_no_falla(self):
        en = "# T\n\n```\ncodigo\n```\n"
        es = "# T\n\n```\ncodigo\n```\n"
        self.assertFalse(any("VALLA" in f for f in traducir_libro.verificar(en, es)))

    def test_aparato_bibliografico_no_da_falso_positivo(self):
        # Casi todo son títulos y nombres propios que NO cambian de idioma; solo
        # la prosa que los rodea se traduce. No debe marcarse.
        en = "\n".join([
            "[^1]: *De occulta philosophia libri tres* (Cologne, 1531/33); see Abbreviations for details.",
            "[^2]: Gershom Scholem, *Major Trends in Jewish Mysticism* (New York: Schocken, 1946), see also 28.",
            "[^3]: Moshe Idel, *Kabbalah: New Perspectives* (New Haven: Yale, 1988), for a brief historiography.",
            "[^4]: Frances Yates, *Giordano Bruno*, esp. chapter 8, pages 144-56, in which magic is discussed."])
        es = "\n".join([
            "[^1]: *De occulta philosophia libri tres* (Colonia, 1531/33); véase Abreviaturas para los detalles.",
            "[^2]: Gershom Scholem, *Major Trends in Jewish Mysticism* (Nueva York: Schocken, 1946), véase también 28.",
            "[^3]: Moshe Idel, *Kabbalah: New Perspectives* (New Haven: Yale, 1988), para una breve historiografía.",
            "[^4]: Frances Yates, *Giordano Bruno*, esp. capítulo 8, páginas 144-56, donde se trata la magia."])
        self.assertEqual(traducir_libro.verificar_notas_traducidas(en, es), [])

    def test_notas_de_una_palabra_latina_no_cuentan(self):
        # *Westphaliae.* es idéntica en los dos idiomas con toda razón.
        en = "[^1]: Hermann V Archbishop of Cologne (1477-1552).\n[^2]: *Wydae.*\n[^3]: *Westphaliae.*\n[^4]: *Mechlinia.*\n"
        es = "[^1]: Hermann V, arzobispo de Colonia (1477-1552).\n[^2]: *Wydae.*\n[^3]: *Westphaliae.*\n[^4]: *Mechlinia.*\n"
        self.assertEqual(traducir_libro.verificar_notas_traducidas(en, es), [])


class CoseParrafos(unittest.TestCase):
    """Párrafos partidos por el salto de página."""

    def test_cose_frase_partida(self):
        md = "Idel subdividió el abanico. En numerosas\n\nocasiones ha argumentado que sí.\n"
        out, n, _detalle, _dudosos = cose_parrafos.cose(md)
        self.assertEqual(n, 1)
        self.assertIn("En numerosas ocasiones ha argumentado", out)

    def test_no_cose_si_la_frase_cierra(self):
        md = "Idel subdividió el abanico.\n\nen numerosas ocasiones lo dijo.\n"
        self.assertEqual(cose_parrafos.cose(md)[1], 0)

    def test_cose_tras_palabra_funcion_aunque_siga_mayuscula(self):
        """La MAYÚSCULA del siguiente párrafo no prueba que el anterior cerrara.

        La primera versión exigía que la continuación abriera en minúscula, y eso
        dejaba fuera un caso medido en Ficino: «…para ambos pensadores, aunque» ␤␤
        «Ficino, para defender…». Una palabra función abierta —conjunción,
        preposición, artículo, relativo— no puede ser la última de un párrafo pase
        lo que pase detrás, así que manda ella y no la caja de la letra siguiente.
        """
        md = "Idel subdividió el abanico y\n\nScholem no estuvo de acuerdo.\n"
        self.assertEqual(cose_parrafos.cose(md)[1], 1)

    def test_no_cose_si_cierra_frase_y_sigue_mayuscula(self):
        """El contrapunto del anterior: con puntuación terminal no se toca nada."""
        md = "Idel subdividió el abanico.\n\nScholem no estuvo de acuerdo.\n"
        self.assertEqual(cose_parrafos.cose(md)[1], 0)

    def test_nunca_cose_alrededor_de_una_cita(self):
        # La frase entra en la cita y sale de ella: es la estructura del ORIGINAL.
        md = ("la extensión del lenguaje es\n\n> lógicamente superior al habla,\n\n"
              "y con sus virtudes. La escritura descansa.\n")
        out, n, _detalle, _dudosos = cose_parrafos.cose(md)
        self.assertEqual(n, 0)
        self.assertIn("\n\n> lógicamente", out)

    def test_no_toca_notas_ni_encabezados(self):
        md = "# Título\n\n[^1]: una nota\n\n[^2]: otra nota\n"
        self.assertEqual(cose_parrafos.cose(md)[1], 0)

    def test_llamada_de_nota_cuenta_como_cierre(self):
        md = "Esto ya cerró la frase.[^12]\n\nasí que esto no se cose.\n"
        self.assertEqual(cose_parrafos.cose(md)[1], 0)
