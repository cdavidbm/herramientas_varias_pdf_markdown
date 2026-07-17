import unittest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from ocr_spellfix import Fixer

# corpus donde 'book' y 'text' son MUY frecuentes; nombres propios raros
CORPUS = (("book " * 20) + ("text " * 20) + ("Hōroskopos " * 12) + ("zōidion " * 12)
          + ("nativity native the of and " * 8) + " Malik Castile Bishr Cordoban ")

class T(unittest.TestCase):
    def setUp(self): self.fx = Fixer(CORPUS, min_freq=3, max_edits=2, common=8, cap_factor=2)
    def fix(self, s):
        ch=[]; return self.fx.fix_text(s, ch)
    def test_bosk_to_book(self):
        self.assertEqual(self.fix("the so-called Bosk of Aristotle"), "the so-called Book of Aristotle")
    def test_boks_to_book(self):
        self.assertEqual(self.fix("many boks here"), "many book here")
    def test_transliteration_protected(self):
        self.assertEqual(self.fix("the Hōroskopos rises"), "the Hōroskopos rises")
    def test_dict_word_untouched(self):
        self.assertEqual(self.fix("the nativity of the native"), "the nativity of the native")
    def test_acronym_protected(self):
        self.assertEqual(self.fix("see the CCAG and P"), "see the CCAG and P")
    def test_proper_nouns_protected(self):
        # nombres propios raros NO se tocan (no se vuelven palabras comunes)
        self.assertEqual(self.fix("Malik and Castile and Bishr and Cordoban"),
                         "Malik and Castile and Bishr and Cordoban")

if __name__ == "__main__":
    unittest.main()
