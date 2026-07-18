import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ocr_geometry as og  # noqa: E402


def line(block, top, left, height, text):
    """Genera filas TSV nivel-5 (una palabra por token) para una línea."""
    rows, x = [], left
    for wn, w in enumerate(text.split(), 1):
        rows.append(f"5\t1\t{block}\t1\t1\t{wn}\t{x}\t{top}\t{len(w)*15}\t{height}\t95\t{w}")
        x += len(w) * 15 + 10
    return rows


def page(*lines):
    return "level\tpage\tblock\tpar\tline\tword\tleft\ttop\twidth\theight\tconf\ttext\n" + \
           "\n".join(r for ln in lines for r in ln)


class TestOcrGeometry(unittest.TestCase):
    def _prose_page(self):
        # 2 párrafos (línea 1 sangrada a 150; continuaciones a 100) + 1 nota tras hueco
        return page(
            line(1, 100, 150, 35, "First paragraph begins here with an indent."),
            line(2, 160, 100, 35, "It continues onward with more words present."),
            line(3, 220, 100, 35, "and still more text to fill the margin."),
            line(4, 280, 150, 35, "Second paragraph also begins with an indent."),
            line(5, 340, 100, 35, "and keeps going along the common left margin."),
            line(6, 540, 100, 28, "1 A footnote about the source, cf. Carmen."),  # tras hueco 200
        )

    def test_notes_split_by_gap(self):
        rh, body, notes = og.split_page(self._prose_page())
        self.assertEqual(len(notes), 1)
        self.assertIn("footnote about the source", notes[0])
        # el cuerpo NO contiene la nota
        self.assertFalse(any("footnote" in t for _, t in body))

    def test_paragraphs_by_median_indent(self):
        rh, body, notes = og.split_page(self._prose_page())
        starts = [t for ind, t in body if ind]
        self.assertTrue(any(t.startswith("First paragraph") for t in starts))
        self.assertTrue(any(t.startswith("Second paragraph") for t in starts))
        # las líneas de continuación NO se marcan como párrafo
        self.assertFalse(any(t.startswith("It continues") for t in starts))

    def test_hanging_marker_does_not_fake_indent(self):
        # un marcador volado «§» cuelga muy a la izquierda; con `min` habría hecho
        # que TODAS las líneas parecieran sangradas. Con mediana, no.
        p = page(
            line(1, 100, 100, 35, "Main body text at the common margin here now."),
            line(2, 160, 100, 35, "More body text continuing at the same margin."),
            line(3, 220, 40, 35, "§ hanging marker then body continuing here too."),
            line(4, 280, 100, 35, "Yet more ordinary body text at the margin here."),
        )
        rh, body, notes = og.split_page(p)
        indented = [t for ind, t in body if ind]
        self.assertEqual(indented, [])  # ninguna línea es párrafo nuevo espurio

    def test_reflow_dehyphenates(self):
        body = [(True, "This is impor-"), (False, "tance in context.")]
        paras = og.reflow(body)
        self.assertEqual(len(paras), 1)
        self.assertIn("importance", paras[0])

    def test_reflow_join_mode_single_block(self):
        body = [(True, "Verse one text."), (True, "Verse two text.")]
        self.assertEqual(len(og.reflow(body, join=True)), 1)   # un bloque
        self.assertEqual(len(og.reflow(body, join=False)), 2)  # dos párrafos

    def test_join_notes_drops_garbage(self):
        notes = ["TE", "1:9} 7%) ®R", "1 A real footnote about the source."]
        out = og.join_notes(notes)
        self.assertEqual(len(out), 1)
        self.assertIn("real footnote", out[0])


if __name__ == "__main__":
    unittest.main()
