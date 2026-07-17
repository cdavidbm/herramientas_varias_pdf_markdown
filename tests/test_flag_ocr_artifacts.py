import unittest, sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from pathlib import Path
import flag_ocr_artifacts as F

class T(unittest.TestCase):
    def flags(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text); p=Path(f.name)
        return {k for _,k,_ in F.check([p], set())}
    def test_garbage(self):
        self.assertIn("garbage", self.flags("010 OQ Fo vio Oar Iu wioOQ wo OQ go 0 QQ FY vio r"))
    def test_glued(self):
        self.assertIn("glued", self.flags("**Ares** (*Arēs*): Mars. arise: epitello. Used for rising."))
    def test_dash(self):
        self.assertIn("dash", self.flags("And in\n\n- such a manner the effects are revealed."))
    def test_split(self):
        self.assertIn("split", self.flags("the light of the\n\nsect and of the Horoskopos, and their rulers."))
    def test_clean_text_no_flags(self):
        f=self.flags("**house** (*oikos*): In the modern idiom, a sign is the dwelling place.\n\n"
                     "**hour** (*hōra*): A unit of time.")
        self.assertEqual(f, set())

if __name__ == "__main__":
    unittest.main()
