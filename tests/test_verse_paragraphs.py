import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import verse_paragraphs as vp


class TestVerseParagraphs(unittest.TestCase):
    def test_splits_verses_on_number_plus_capital(self):
        t = "1 Alpha statement here. 2 Beta follows it. 3 Gamma ends it."
        out = vp.split_verses(t)
        self.assertIn("**1** Alpha", out)
        self.assertIn("**2** Beta", out)
        self.assertIn("**3** Gamma", out)
        # cada verso en su propio párrafo
        self.assertEqual(out.count("\n\n"), 2)

    def test_quantities_not_split(self):
        # número seguido de MINÚSCULA = cantidad, no verso
        t = "The Sun traverses 30 degrees and 360 units in the year"
        out = vp.split_verses(t)
        self.assertNotIn("**30**", out)
        self.assertNotIn("**360**", out)

    def test_reset_allowed_new_chapter(self):
        # el contador puede resetear (nuevo capítulo) porque no exige secuencia
        t = "5 Epsilon here. 6 Zeta here. 2 New chapter opens. 3 And continues."
        out = vp.split_verses(t)
        self.assertIn("**5**", out)
        self.assertIn("**2** New", out)
        self.assertIn("**3** And", out)

    def test_idempotent_and_protects_headings(self):
        t = "## Chapter I.1: On things\n\n**1** Already bold verse. 2 Second one."
        out, v = vp.process(t, 199)
        # el encabezado se conserva intacto
        self.assertIn("## Chapter I.1: On things", out)
        # la línea ya en negrita NO se re-procesa (idempotente)
        self.assertIn("**1** Already bold verse. 2 Second one.", out)

    def test_max_bound(self):
        t = "1 First. 500 Not a verse because too big."
        out = vp.split_verses(t, vmax=199)
        self.assertIn("**1** First", out)
        self.assertNotIn("**500**", out)


if __name__ == "__main__":
    unittest.main()
