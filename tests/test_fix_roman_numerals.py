import unittest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from fix_roman_numerals import process, coerce_roman

class T(unittest.TestCase):
    def fix(self, s): return process(s)[0]
    def test_user_example(self):
        self.assertEqual(self.fix("In Volume IT T will publish a new translation"),
                         "In Volume II I will publish a new translation")
    def test_counter_words(self):
        self.assertEqual(self.fix("Book IIL of the Anthology"), "Book III of the Anthology")
        self.assertEqual(self.fix("Chapter 1V, Book I."), "Chapter IV, Book I.")
        self.assertEqual(self.fix("in Volume ll we saw"), "in Volume II we saw")
    def test_arabic_number_untouched(self):
        self.assertEqual(self.fix("the Liber Hermetis, chapter 16"), "the Liber Hermetis, chapter 16")
    def test_valid_roman_untouched(self):
        self.assertEqual(self.fix("From Chapter 24, Book III. Ptolemy"), "From Chapter 24, Book III. Ptolemy")
    def test_pronoun_before_verb(self):
        self.assertEqual(self.fix("and T am the one who T think wrote it"),
                         "and I am the one who I think wrote it")
    def test_manuscript_siglum_kept(self):
        # «T reads» / «P reads» son siglas de manuscrito, NO el pronombre
        self.assertEqual(self.fix("where T reads differently and B omits"),
                         "where T reads differently and B omits")
    def test_coerce(self):
        self.assertEqual(coerce_roman("IT"), "II")
        self.assertEqual(coerce_roman("1V"), "IV")
        self.assertEqual(coerce_roman("IIL"), "III")
        self.assertIsNone(coerce_roman("III"))
        self.assertIsNone(coerce_roman("16"))

if __name__ == "__main__":
    unittest.main()
