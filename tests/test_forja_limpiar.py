import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"


class TestForjaLimpiar(unittest.TestCase):
    def _run(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cap.md"
            f.write_text(text, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(TOOLS / "forja_limpiar.py"), str(f), *args],
                capture_output=True, text=True)
            return r, (f.read_text(encoding="utf-8") if f.exists() else "")

    def test_dry_run_does_not_write(self):
        original = "The 4 lh house in Volume IT T will note it.\n"
        r, after = self._run(original)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(after, original)              # dry-run intacto
        self.assertIn("DRY-RUN", r.stdout)

    def test_apply_runs_deterministic_core(self):
        r, after = self._run("The 4 lh house in Volume IT T will note it.\n", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("4th", after)                    # ordinales
        self.assertIn("Volume II", after)              # romanos
        self.assertIn("APLICADO", r.stdout)

    def test_verses_toggle_splits_paragraphs(self):
        text = "## Chapter I.1: On things\n\n1 Alpha here. 2 Beta here. 3 Gamma here.\n"
        r, after = self._run(text, "--verses", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("**2**", after)
        self.assertIn("**3**", after)

    def test_final_report_present(self):
        r, _ = self._run("Plain clean prose without artifacts.\n")
        self.assertIn("revisar a mano", r.stdout)


if __name__ == "__main__":
    unittest.main()
