import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import catalog  # noqa: E402


class TestCatalog(unittest.TestCase):
    def test_every_tool_is_catalogued(self):
        py = {p.name for p in TOOLS.glob("*.py")}
        text, _ = catalog.build()
        for name in py:
            self.assertIn(name, text, f"{name} falta en el catálogo")

    def test_one_liner_strips_filename_prefix(self):
        # el prefijo «name.py —» se elimina, queda solo el propósito
        line = catalog.one_liner(TOOLS / "fix_ocr.py")
        self.assertNotIn("fix_ocr.py", line)
        self.assertTrue(line)

    def test_catalog_file_in_sync(self):
        # CATALOG.md debe coincidir con lo generado (si no, corre --write)
        text, _ = catalog.build()
        current = (TOOLS / "CATALOG.md").read_text(encoding="utf-8")
        self.assertEqual(current.strip(), text.strip(),
                         "CATALOG.md desactualizado: python3 tools/catalog.py --write")


if __name__ == "__main__":
    unittest.main()
