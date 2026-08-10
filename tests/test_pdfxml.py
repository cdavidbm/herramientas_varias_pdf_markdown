"""Las dos trampas de `pdftohtml -xml`, como código ejecutable.

Ambas se caracterizan por perder estilo EN SILENCIO: el texto sale entero, el
ratio de palabras es perfecto y el balance de notas cuadra, mientras la cursiva
—que en este fondo es contenido, no adorno— se ha evaporado.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forja import pdfxml as px  # noqa: E402


XML = """<pdf2xml>
<page number="1" width="600" height="900">
<fontspec id="0" size="23" family="AdobeTextNYUP"/>
<fontspec id="1" size="23" family="AdobeTextNYUP-It"/>
<text top="100" left="50" width="80" height="20" font="0">Redonda</text>
<text top="130" left="50" width="80" height="20" font="1">Cursiva</text>
</page>
<page number="5" width="600" height="900">
<text top="100" left="50" width="80" height="20" font="1">Sigue cursiva</text>
</page>
</pdf2xml>"""


class FontspecGlobales(unittest.TestCase):
    """Trampa 1: se declaran una vez y valen para todo el documento."""

    def test_una_fuente_declarada_en_la_pagina_1_resuelve_en_la_5(self):
        """Un mapa POR PÁGINA pierde los ids heredados.

        Medido en ClearScan: el 40 % del texto se quedaba sin estilo, y en un
        libro donde la cursiva marca las transliteraciones eso es perder el
        aparato entero sin que nada lo denuncie.
        """
        pgs = px.tokens(XML)
        self.assertEqual(len(pgs), 2)
        ultima = pgs[1]["toks"][0]
        self.assertEqual(ultima["txt"], "Sigue cursiva")
        self.assertTrue(ultima["ital"], "la fuente de la página 1 debe seguir resolviendo")

    def test_fontspecs_acumula_sobre_el_xml_entero(self):
        spec = px.fontspecs(XML)
        self.assertEqual(set(spec), {"0", "1"})
        self.assertEqual(spec["1"][1], "AdobeTextNYUP-It")


class CursivaAbreviada(unittest.TestCase):
    """Trampa 2: la cursiva no siempre se llama «Italic»."""

    def test_reconoce_la_abreviatura_del_nombre_de_la_fuente(self):
        """`AdobeTextNYUP-It` es la cursiva de la Library of Arabic Literature.

        Un detector que solo mire «italic»/«oblique» da por redonda toda la
        cursiva del libro y no avisa. Medido: 1.558 tramos recuperados.
        """
        self.assertTrue(px.es_cursiva("AdobeTextNYUP-It"))
        self.assertTrue(px.es_cursiva("AdobeTextNYUP-Ita"))
        self.assertTrue(px.es_cursiva("TimesNewRomanPS-ItalicMT"))
        self.assertTrue(px.es_cursiva("Minion-Oblique"))

    def test_no_confunde_nombres_corrientes_con_cursiva(self):
        """La abreviatura va anclada a un guion, o «Times» y «Digital» casarían."""
        for fam in ("Times", "TimesNewRomanPSMT", "DigitalSans", "AdobeTextNYUP"):
            self.assertFalse(px.es_cursiva(fam), fam)

    def test_negrita(self):
        self.assertTrue(px.es_negrita("Minion-Bold"))
        self.assertTrue(px.es_negrita("SomeFont-SemiBold"))
        self.assertFalse(px.es_negrita("AdobeTextNYUP"))


class Tokens(unittest.TestCase):
    def test_el_estilo_sale_de_la_familia_aunque_no_haya_etiquetas(self):
        """Muchas maquetas no emiten `<i>`: solo cambian de fuente."""
        tok = px.tokens(XML)[0]["toks"]
        self.assertFalse(tok[0]["ital"])
        self.assertTrue(tok[1]["ital"])

    def test_conserva_posicion_y_tamaño(self):
        tok = px.tokens(XML)[0]["toks"][1]
        self.assertEqual((tok["top"], tok["left"]), (130, 50))
        self.assertEqual(tok["size"], 23.0)


if __name__ == "__main__":
    unittest.main()
