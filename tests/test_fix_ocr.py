import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import fix_ocr  # noqa: E402


class TestFixOcrFacade(unittest.TestCase):
    def test_ordinals_wrapper(self):
        out, n = fix_ocr._ordinals("the 4 lh house")
        self.assertIn("4th", out)
        self.assertEqual(n, 1)

    def test_romans_wrapper(self):
        out, n = fix_ocr._romans("In Volume IT T will publish")
        self.assertIn("Volume II", out)
        self.assertIn("II I will", out)
        self.assertGreaterEqual(n, 2)

    def test_diacritics_wrapper(self):
        out, n = fix_ocr._diacritics("Martı´n")
        self.assertIn("Martín", out)
        self.assertGreater(n, 0)

    def test_deterministic_order(self):
        names = [k for k, _ in fix_ocr.DETERMINISTIC]
        self.assertEqual(names, ["ordinals", "romans", "ligatures", "diacritics"])

    def test_cli_all_dry_run_writes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.md"
            original = "The 4 lh house in Volume IT T will note.\n"
            f.write_text(original, encoding="utf-8")
            r = subprocess.run([sys.executable, str(TOOLS / "fix_ocr.py"), "all", str(f)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(f.read_text(encoding="utf-8"), original)  # dry-run: intacto
            self.assertIn("TOTAL all", r.stdout)


if __name__ == "__main__":
    unittest.main()
