"""Tests de la fase «investigar y escribir un libro»: book_integrity, book_invariants,
apa_video_keys y los dos arreglos de md_to_pdf que salieron de maquetar un libro escrito
con La Forja (separador «·» en el H1; «## Notas» vacío seguido de «---»)."""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import apa_video_keys  # noqa: E402
import book_integrity  # noqa: E402
import book_invariants  # noqa: E402
import md_to_pdf  # noqa: E402

CAP4 = """# Capítulo 4 · Método

## 3. Ejes

### 3.3 Parejas

#### 3.3.3 Las otras parejas

Texto con nota.[^1] Según Masdeu (2021at, 2022k) y Raúl y Masdeu (2023e), la tabla
se sostiene (al-Tilimsānī, ca. 1291/2023, §12.1; Ibn al-ʿArabī, 1224/1996, n.º 36).

[^1]: Una nota.

## Referencias del capítulo

Ibn al-ʿArabī. (1996). *Kašf al-maʿnā*.

Masdeu, A. (2021at, 8 de julio). *Clase 10*.

Masdeu, A. (2022k, 30 de junio). *Antares 110*.

Raúl, F., y Masdeu, A. (2023e, 7 de enero). *Coloquio 5*.

al-Tilimsānī, ʿA. al-D. (2023). *The divine names*.
"""

CAP5 = """# Capítulo 5 · La Luna

## 1. Fuentes

Véase el capítulo 4, §3.3.3, y el capítulo 4, §9.1. También el Excurso, §XIV.[^2]
[pendiente de verificación]

## Referencias del capítulo

Obert, C. (2020). *The classical seven planets*.
"""

EXC = """# Excurso · Cómo se hace un Nombre

### XIV. Las presencias

Texto.
"""


class TestBookIntegrity(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "04.md").write_text(CAP4, encoding="utf-8")
        (self.d / "05.md").write_text(CAP5, encoding="utf-8")
        (self.d / "02b.md").write_text(EXC, encoding="utf-8")
        files = sorted(self.d.glob("*.md"))
        self.rep = book_integrity.check(files, "Referencias del capítulo",
                                        book_integrity.DEFAULT_MARKERS, None)

    def test_clean_chapter_has_no_errors(self):
        # citas narrativas, de tabla, «Raúl y Masdeu (2023e)» y original/edición: todas casan
        self.assertFalse([e for e in self.rep["errores"] if e.startswith("04.md")],
                         self.rep["errores"])
        self.assertFalse([w for w in self.rep["avisos"] if w.startswith("04.md")],
                         self.rep["avisos"])

    def test_broken_remission_and_note(self):
        errs = "\n".join(self.rep["errores"])
        self.assertIn("§9.1", errs)                      # el cap. 4 no tiene §9.1
        self.assertNotIn("§3.3.3", errs)                 # esa sí existe
        self.assertIn("llamada [^2] sin nota", errs)
        self.assertNotIn("Excurso", errs)                # §XIV existe en el Excurso

    def test_work_marker_and_uncited_entry_are_warnings(self):
        warns = "\n".join(self.rep["avisos"])
        self.assertIn("[pendiente", warns)
        self.assertIn("(obert, 2020) nunca citada", warns)


class TestBookInvariants(unittest.TestCase):
    def test_identical_is_clean(self):
        self.assertEqual(book_invariants.compare(CAP4, CAP4), {})

    def test_detects_quote_heading_and_mark_changes(self):
        a = CAP4 + "\nFrase «una cita literal bastante larga de la fuente» **[D]**.\n"
        b = a.replace("literal bastante", "literal muy").replace("#### 3.3.3", "#### 3.3.4") \
             .replace("**[D]**", "")
        d = book_invariants.compare(a, b)
        self.assertIn("citas", d)
        self.assertIn("encabezados", d)
        self.assertIn("marcas", d)


class TestApaVideoKeys(unittest.TestCase):
    def test_letters_beyond_z(self):
        self.assertEqual(apa_video_keys.letters(0), "a")
        self.assertEqual(apa_video_keys.letters(25), "z")
        self.assertEqual(apa_video_keys.letters(26), "aa")
        self.assertEqual(apa_video_keys.letters(51), "az")

    def test_keys_by_title_and_single_video_without_letter(self):
        d = Path(tempfile.mkdtemp())
        vids = [("2021-06-07", "Zodíaco y estaciones", "1"), ("2021-06-14", "Aspectos", "2"),
                ("2022-01-10", "Casas", "3")]
        for f, t, n in vids:
            (d / f"{f}.md").write_text(
                f'---\ntítulo: "{t}"\nclase: {n}\nfecha: {f}\nprofesor: Albert Masdeu\n'
                f'fuente: "YouTube — Logos Astrológico"\nvideo_id: abc{n}\n---\ntexto\n', encoding="utf-8")
        rows = {r["numero"]: r for r in apa_video_keys.build(d, None, None, "titulo")}
        self.assertEqual(rows["2"]["clave"], "2021a")    # «Aspectos» antes que «Zodíaco»
        self.assertEqual(rows["1"]["clave"], "2021b")
        self.assertEqual(rows["3"]["clave"], "2022")     # único del año: sin letra
        self.assertEqual(rows["1"]["cita"], "(Masdeu, 2021b)")
        self.assertTrue(rows["1"]["referencia"].startswith("Masdeu, A. (2021b, 7 de junio). *Zodíaco"))
        self.assertIn("Logos Astrológico. https://www.youtube.com/watch?v=abc1", rows["1"]["referencia"])


class TestMdToPdfBookFixes(unittest.TestCase):
    def test_middle_dot_chapter_heading(self):
        self.assertTrue(md_to_pdf.CHAP_RE.match("# Capítulo 5 · La Luna"))
        self.assertEqual(md_to_pdf.PREF_RE.sub("", "Capítulo 5 · La Luna"), "La Luna")

    def test_empty_notes_heading_before_rule_is_removed(self):
        src = "Texto\n\n## Notas\n\n[^1]: nota\n\n---\n\n## Referencias\n\nX"
        out = md_to_pdf.strip_empty_note_heading(src)
        self.assertNotIn("## Notas", out)
        self.assertIn("[^1]: nota", out)

    def test_notes_heading_with_prose_is_kept(self):
        src = "## Notas\n\nUn párrafo de verdad.\n\n[^1]: nota\n"
        self.assertIn("## Notas", md_to_pdf.strip_empty_note_heading(src))


if __name__ == "__main__":
    unittest.main()
