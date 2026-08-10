"""Encabezados y subtítulos: defectos que el ratio global no ve.

Los tres comparten firma: el markdown se lee bien y el recuento de palabras del
archivo cuadra, mientras el libro pierde su estructura o mil palabras de texto.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forja import estructura as es  # noqa: E402


class TitulosPartidos(unittest.TestCase):
    def test_un_titulo_en_minuscula_delata_que_esta_partido(self):
        """La señal barata. Un título no empieza en minúscula por gusto."""
        md = "## del consultante\n\ntexto\n\n## Capítulo entero\n\notro\n"
        self.assertEqual(es.titulos_en_minuscula(md), ["## del consultante"])

    def test_el_huerfano_bajo_el_titulo_se_detecta(self):
        md = "## De la significación\n\ndel señor del ascendente\n\nAquí empieza la prosa.\n"
        part = es.encabezados_partidos(md)
        self.assertEqual(len(part), 1)
        self.assertEqual(part[0][1], "del señor del ascendente")

    def test_un_parrafo_largo_en_minuscula_no_es_un_huerfano(self):
        """Guarda: el huérfano de un título es CORTO."""
        largo = "y aquí sigue una frase de cuerpo que continúa el párrafo anterior " \
                "con bastantes más palabras de las que cabrían en un título centrado."
        md = f"## Un título\n\n{largo}\n"
        self.assertEqual(es.encabezados_partidos(md), [])


class SubtitulosFundidos(unittest.TestCase):
    def test_detecta_el_apartado_pegado_a_su_parrafo(self):
        """Medido en Lehrich: 86 por idioma, invisibles al leer el markdown."""
        md = "*Planetary Characters* The construction of these figures depends on…\n"
        got = es.subtitulos_fundidos(md)
        self.assertEqual(got[0][0], "Planetary Characters")

    def test_NO_promueve_una_leyenda_de_figura(self):
        """Una regla de «bloque en cursiva» las convertiría en encabezado.

        Cinco por idioma en Lehrich. Una leyenda no es un apartado.
        """
        md = "*Figura 3: el sello de Saturno según Agripa* y su explicación sigue aquí.\n"
        self.assertEqual(es.subtitulos_fundidos(md), [])

    def test_no_dispara_si_el_parrafo_arranca_con_OTRA_cursiva(self):
        """`*Character and Hieroglyph* *DOP* does not…`: ahí no se puede decidir."""
        md = "*Character and Hieroglyph* *DOP* does not settle the question at all.\n"
        self.assertEqual(es.subtitulos_fundidos(md), [])

    def test_un_bloque_entero_en_cursiva_tampoco(self):
        md = "*Toda la línea va en cursiva y no abre ningún párrafo*\n"
        self.assertEqual(es.subtitulos_fundidos(md), [])


class RatioPorCapitulo(unittest.TestCase):
    def test_el_ratio_global_esconde_la_laguna_de_un_capitulo(self):
        """Medido en Ficino: global 0,98 y el capítulo perdido en 0,62.

        Es la razón de que la completitud de una traducción se mida POR CAPÍTULO
        y no por libro: promediando, 1.484 palabras perdidas desaparecen.
        """
        buenos = [(f"cap{i}.md", "palabra " * 1000, "palabra " * 1000) for i in range(9)]
        malo = [("cap12.md", "palabra " * 1000, "palabra " * 620)]
        pares = buenos + malo
        global_ = sum(len(c.split()) for _, _, c in pares) / \
            sum(len(a.split()) for _, a, _ in pares)
        self.assertGreater(global_, 0.95)                      # el global no se entera
        self.assertEqual(es.capitulos_con_deficit(pares), [("cap12.md", 0.62)])

    def test_ignora_los_capitulos_muy_cortos(self):
        """Con pocas palabras el ratio es ruido, no señal."""
        self.assertEqual(es.capitulos_con_deficit([("x.md", "una dos tres", "una")]), [])


if __name__ == "__main__":
    unittest.main()
