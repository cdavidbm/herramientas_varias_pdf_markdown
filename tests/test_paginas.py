"""Folios, titulillos y unión de renglones: las decisiones que BORRAN texto.

Estos tests existen porque las mismas funciones vivían duplicadas en dos
conversores y habían divergido en un solo carácter cada una, con el resultado de
que el mismo libro salía distinto según cuál lo hubiera tocado.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forja import paginas as pg  # noqa: E402


class Folios(unittest.TestCase):
    def test_un_folio_sangrado_sigue_siendo_un_folio(self):
        """La divergencia del `.strip()`.

        Sin normalizar antes de comparar, el folio de las páginas pares —que en
        muchas maquetas va sangrado— no se reconoce y acaba impreso a media
        página en el markdown.
        """
        self.assertTrue(pg.es_numero_pagina("   57   "))
        self.assertTrue(pg.es_numero_pagina("57"))
        self.assertTrue(pg.es_numero_pagina("  · xiv ·  "))

    def test_una_cifra_dentro_de_una_frase_no_es_folio(self):
        self.assertFalse(pg.es_numero_pagina("57 nombres divinos se comentan aquí"))
        self.assertFalse(pg.es_numero_pagina("El capítulo 12 trata de esto."))


class Titulillos(unittest.TestCase):
    """El filtro que más texto ha destruido de toda la suite."""

    PATRONES = [re.compile(r"THE DIVINE NAMES"), re.compile(r"CHAPTER \w+")]

    def test_borra_el_titulillo_de_verdad(self):
        self.assertTrue(pg.es_titulillo("THE DIVINE NAMES 57", self.PATRONES))
        self.assertTrue(pg.es_titulillo("  CHAPTER FOUR  ", self.PATRONES))

    def test_NO_borra_la_prosa_que_menciona_el_titulo(self):
        """La divergencia `search` vs `match`, que es la cara.

        Con `search`, cualquier renglón que contenga el patrón desaparece. Una
        frase del cuerpo que cite el título de la obra o el rótulo del capítulo
        se borra entera, y esa pérdida **no deja rastro**: el markdown se lee sin
        sobresaltos y el hueco solo aparece cotejando contra el PDF. Medido en
        Kaske & Clark: 14 páginas y 194 palabras, siempre a mitad de frase.
        """
        linea = "as he argues in THE DIVINE NAMES, the question is older"
        self.assertFalse(pg.es_titulillo(linea, self.PATRONES))

    def test_una_linea_vacia_no_es_titulillo(self):
        self.assertFalse(pg.es_titulillo("   ", self.PATRONES))


class UnionDeRenglones(unittest.TestCase):
    def test_el_guion_suave_se_absorbe_siempre(self):
        self.assertEqual(pg.une_renglones(["consi­", "deración"]), "consideración")

    def test_el_guion_normal_solo_ante_minuscula(self):
        """En `al-Rijāl` el guion es parte del nombre, no un corte de palabra.

        Absorberlo destruye la transliteración, que en este fondo es el objeto
        del libro y no un adorno.
        """
        self.assertEqual(pg.une_renglones(["exten-", "der"]), "extender")
        self.assertEqual(pg.une_renglones(["al-", "Rijāl"]), "al- Rijāl")

    def test_une_parrafo_deshace_el_corte_pero_no_junta_palabras(self):
        self.assertEqual(pg.une_parrafo("exten-\nder la obra"), "extender la obra")
        self.assertEqual(pg.une_parrafo("una frase\ny la siguiente"),
                         "una frase y la siguiente")


if __name__ == "__main__":
    unittest.main()
