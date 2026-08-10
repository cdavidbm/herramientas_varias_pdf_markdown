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


class FolioAntesDelHueco(unittest.TestCase):
    """El folio hay que quitarlo ANTES de buscar el hueco cuerpo/notas."""

    def _pagina(self, con_folio: bool):
        ls, b = [], 0
        for k in range(20):                       # cuerpo
            b += 1
            ls.append(line(b, 100 + k * 40, 150 if k == 0 else 100, 34,
                           "cuerpo de la pagina con bastantes palabras aqui"))
        for k in range(8):                        # aparato, tras un hueco grande
            b += 1
            ls.append(line(b, 1000 + k * 26, 100, 22,
                           "%d Una nota al pie con su referencia, p. 12." % (k + 1)))
        if con_folio:                             # folio SOLO, muy abajo
            b += 1
            ls.append(line(b, 1400, 600, 30, "76"))
        return page(*ls)

    def test_el_folio_no_debe_ganar_el_hueco(self):
        """Sin la guarda, el aparato entero se queda en el cuerpo — EN SILENCIO.

        El folio va solo al pie, con blanco arriba y abajo, así que es el mayor
        hueco vertical de la mitad inferior siempre y por mucho. La herramienta
        clasificaba como «notas» solo el folio, dejaba las notas reales en la
        prosa y salía sin error, emitiendo un `## Notes` con un número dentro.

        Medido en Greenbaum, *The Daimon in Hellenistic Astrology*: la p. 76, con
        OCHO notas al pie, daba 43 líneas de cuerpo y 1 de notas, que era «76».
        Con la guarda: 23 de cuerpo y 20 de notas.
        """
        _rh, _cuerpo, notas = og.split_page(self._pagina(con_folio=True))
        self.assertGreaterEqual(len(notas), 5,
                                "el aparato se ha quedado en el cuerpo: ganó el folio")
        self.assertFalse(any(n.strip() == "76" for n in notas),
                         "el folio no debe acabar entre las notas")

    def test_sin_folio_se_comporta_igual(self):
        """La guarda no puede cambiar el resultado de una página sin folio."""
        _rh, _cuerpo, notas = og.split_page(self._pagina(con_folio=False))
        self.assertGreaterEqual(len(notas), 5)

    def test_una_cifra_del_cuerpo_no_se_confunde_con_el_folio(self):
        """Solo cuenta la ÚLTIMA línea, y solo si está pegada al pie."""
        ls = [line(1, 100, 150, 34, "una frase del cuerpo que menciona el ano 76"),
              line(2, 140, 100, 34, "y sigue con mas prosa normal aqui"),
              line(3, 180, 100, 34, "y todavia mas texto para dar cuerpo")]
        _rh, cuerpo, _notas = og.split_page(page(*ls))
        self.assertEqual(len(cuerpo), 3, "no debe recortar nada")


class FiltroDeBasuraUnicode(unittest.TestCase):
    """El filtro de `join_notes` cuenta LETRAS, no minúsculas ASCII."""

    def test_no_borra_una_nota_en_griego(self):
        """Medido en Greenbaum: 550 bloques de griego borrados en un capítulo.

        `[a-z]{3,}` no casa con ninguna escritura no latina, así que la línea
        entera se descartaba como si fuera un filete. Y es la pérdida más cara
        posible: el griego es lo que más cuesta recuperar —hizo falta un re-OCR
        con `-l eng+grc`— y lo que nadie echa de menos leyendo el markdown.
        """
        notas = ["θεοῖς καὶ δαίμοσι μεμισημένον.",
                 "τῶν ἄνωθεν αὐτῆς δεχομένη ἀστέρων καὶ διακονοῦσα."]
        salida = " ".join(og.join_notes(notas, D=set()))
        for pieza in ("δαίμοσι", "ἀστέρων"):
            self.assertIn(pieza, salida, "se ha perdido griego")

    def test_tampoco_borra_arabe_ni_hebreo(self):
        salida = " ".join(og.join_notes(["الرحمن الرحيم الملك", "אלהים אחד ברוך"], D=set()))
        for pieza in ("الرحيم", "אחד"):
            self.assertIn(pieza, salida)

    def test_sigue_borrando_los_filetes_y_la_basura_corta(self):
        """La guarda no puede volverse permisiva: eso era lo que el filtro hacía bien."""
        for basura in ("---", "***", "1", "~~", "|| ||"):
            self.assertEqual(og.join_notes([basura], D=set()), [],
                             "no debería conservar %r" % basura)

    def test_conserva_una_nota_latina_normal(self):
        self.assertEqual(len(og.join_notes(["1 Plutarch, De genio Socratis, 589."], D=set())), 1)
