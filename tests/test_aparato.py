"""Las lecciones del aparato de notas, como código ejecutable.

Cada test de aquí es una advertencia que hasta ahora solo vivía en prosa dentro
del CLAUDE.md, con su libro y su cifra. Están escritos al revés de lo habitual:
no comprueban que la función «funcione», sino que **sigue viva la guarda cuya
ausencia costó un libro**. Si alguien simplifica una de estas expresiones por
parecerle enrevesada, aquí se entera.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forja import aparato as ap  # noqa: E402


class Primitivas(unittest.TestCase):
    """Qué es una definición y qué es una llamada."""

    def test_llamada_ante_dos_puntos_no_es_definicion(self):
        """Guarda 1. El atajo «un [^N] no seguido de dos puntos» es FALSO.

        Hay llamadas legítimas delante de un dos puntos. Contarlas como
        definición produce siempre el mismo espejismo: una «nota huérfana».
        """
        md = "…la verdadera naturaleza de la realidad[^23]:\n\n[^23]: La nota.\n"
        self.assertEqual(ap.llamadas(md), {"23"})
        self.assertEqual(set(ap.definiciones(md)), {"23"})
        self.assertEqual(ap.auditar(md), [])

    def test_llamadas_no_se_calculan_restando_las_definiciones(self):
        """Restar defs a refs borra justo las llamadas que SÍ tienen definición.

        Era un fallo real de un verificador escrito a mano: daba 0 llamadas y
        N definiciones, y por tanto N «huérfanas» inexistentes.
        """
        md = "Texto con nota.[^1] Y otra.[^2]\n\n[^1]: una\n\n[^2]: otra\n"
        self.assertEqual(ap.llamadas(md), {"1", "2"})
        self.assertEqual(ap.auditar(md), [])

    def test_definicion_solo_si_abre_renglon(self):
        md = "Una frase que menciona [^7]: y sigue.\n\n[^7]: la definición\n"
        self.assertEqual(set(ap.definiciones(md)), {"7"})


class Cadena(unittest.TestCase):
    """Cómo se sigue la numeración."""

    def test_la_cadena_puede_saltar_un_hueco(self):
        """Guarda 2, la más cara. Medido en Lehrich y en al-Tilimsānī.

        La nota 26 no tiene llamada en el original. Exigir que la cadena avance
        de uno en uno la corta ahí y **invalida en cascada todo lo que viene
        detrás** (en Lehrich, 120 llamadas buenas).
        """
        cands = [(0, 24), (10, 25), (20, 27), (30, 28)]     # falta la 26
        got = [v for _, v in ap.cadena_ascendente(cands, tope=100, desde=24)]
        self.assertEqual(got, [24, 25, 27, 28])

    def test_la_cadena_nunca_retrocede(self):
        """Un número que va hacia atrás es una cifra del cuerpo, no una llamada.

        Medido en Lehrich: el capítulo de los cuadrados mágicos tiene 89 notas y
        salían llamadas hasta la 947.
        """
        cands = [(0, 10), (10, 3), (20, 11)]
        self.assertEqual([v for _, v in ap.cadena_ascendente(cands, tope=100, desde=10)], [10, 11])

    def test_la_cadena_no_pasa_del_tope(self):
        cands = [(0, 1), (10, 592), (20, 2)]
        self.assertEqual([v for _, v in ap.cadena_ascendente(cands, tope=591)], [1, 2])


class VoladosAplanados(unittest.TestCase):
    """El caso al-Tilimsānī: superíndices aplanados por un reprocesador."""

    def test_la_transliteracion_no_puede_quedar_fuera(self):
        """Guarda 3. `[a-zA-Z]` no cubre `ī`, y ahí va pegada la llamada.

        Medido: `al-Baghawī26` se perdía entero con la clase ASCII.
        """
        txt = "según al-Baghawī26 en su antología"
        out, puestas = ap.anclar(txt, tope=30, desde=26)
        self.assertEqual(puestas, [26])
        self.assertIn("al-Baghawī[^26]", out)

    def test_el_cierre_de_cursiva_cuenta_como_caracter_anterior(self):
        """Guarda 3 (segunda mitad). Excluir el `*` pierde `.”*397`."""
        txt = 'dijo el Profeta, *“con Tú, nos refugiamos.”*397 Y sigue'
        out, puestas = ap.anclar(txt, tope=400, desde=397)
        self.assertEqual(puestas, [397])
        self.assertIn("[^397]", out)

    def test_la_numeracion_de_parrafo_no_se_confunde_con_las_notas(self):
        """Guarda 4. Dos series entrelazadas: sin enmascarar, la cadena muere.

        Era la causa REAL de que el primer intento anclara 13 de 544, y no «las
        muchas cifras de la prosa» a las que se culpó.
        """
        txt = ("**1.1** El primer párrafo acaba aquí.1 Sigue el cuerpo.\n\n"
               "**1.2** Y el segundo también.2\n")
        out, puestas = ap.anclar(txt, tope=10)
        self.assertEqual(puestas, [1, 2])
        self.assertIn("**1.1**", out)      # la numeración de párrafo, intacta
        self.assertIn("**1.2**", out)
        self.assertIn("aquí.[^1]", out)
        self.assertIn("también.[^2]", out)

    def test_no_toca_las_referencias_coranicas(self):
        """«Q Isrāʾ 17:110» y «1:1–3» no son llamadas."""
        txt = "cita de Q Isrāʾ 17:110 y de Fātiḥah 1:1–3 sin notas"
        _out, puestas = ap.anclar(txt, tope=200)
        self.assertEqual(puestas, [])

    def test_si_hay_llamadas_legitimas_tras_dos_puntos(self):
        """La trampa de la guarda 1, disfrazada de otra cosa.

        Al excluir el dos puntos para no tragarse «17:110» se pierde la llamada
        real de «…the meaning of liminality:217» — medido en al-Tilimsānī, donde
        costó exactamente una nota. Lo que distingue a una referencia no es el
        signo, sino que ANTES de él haya un dígito.
        """
        txt = "verses concerning the meaning of liminality:217 y sigue"
        out, puestas = ap.anclar(txt, tope=300, desde=217)
        self.assertEqual(puestas, [217])
        self.assertIn("liminality:[^217]", out)

    def test_el_cuerpo_conserva_todas_sus_palabras(self):
        """El control que prueba que no se comió prosa al sustituir."""
        txt = "Primera frase.1 Segunda frase.2 Tercera frase.3"
        out, _ = ap.anclar(txt, tope=10)
        limpio = out.replace("[^1]", "").replace("[^2]", "").replace("[^3]", "")
        self.assertEqual(limpio.split(),
                         txt.replace("1", "").replace("2", "").replace("3", "").split())


class Truncamiento(unittest.TestCase):
    """El aparato cortado que parece íntegro."""

    def test_detecta_que_el_cuerpo_llega_mas_lejos(self):
        a = ap.Aparato({n: "Q Fātiḥah 1:1." for n in range(1, 545)})
        self.assertEqual(a.huecos(), [])                       # parece perfecto
        avisos = a.sospecha_truncamiento(tope_cuerpo=591)
        self.assertTrue(any("faltan 47" in x for x in avisos))

    def test_detecta_la_entrada_que_se_tragó_las_siguientes(self):
        """375 palabras frente a una mediana de 5: la señal barata."""
        notas = {n: "Q Fātiḥah 1:1." for n in range(1, 20)}
        notas[19] = " ".join(["palabra"] * 375)
        avisos = ap.Aparato(notas).sospecha_truncamiento(tope_cuerpo=19)
        self.assertTrue(any("tragado" in x for x in avisos))

    def test_una_nota_de_comentario_larga_EN_MEDIO_no_es_truncamiento(self):
        """El falso positivo que hacía inútil el aviso.

        Un aparato normal mezcla referencias de tres palabras con notas de
        comentario de doscientas. Avisar de «la entrada más larga» dispara en casi
        cualquier libro: medido en al-Tilimsānī, la nota 95 tiene 201 palabras
        frente a una mediana de 3 y es perfectamente legítima. El truncamiento
        tiene una forma concreta —el partidor vuelca el resto en la ÚLTIMA que
        alcanzó a crear—, y solo esa posición cuenta.
        """
        notas = {n: "Q Fātiḥah 1:1." for n in range(1, 200)}
        notas[95] = " ".join(["palabra"] * 201)
        self.assertEqual(ap.Aparato(notas).sospecha_truncamiento(tope_cuerpo=199), [])


class Auditoria(unittest.TestCase):
    """Los dos sentidos, no solo uno."""

    def test_definicion_sin_llamada_se_denuncia(self):
        """Guarda 5. pandoc la descarta EN SILENCIO.

        Medido en *Nine Judges*: 1.463 notas de 1.995 no se imprimieron, con el
        log limpio y el balance «llamadas ⊆ definiciones» dando bien.
        """
        md = "Cuerpo con una nota.[^1]\n\n[^1]: primera\n\n[^2]: esta no se imprime\n"
        problemas = ap.auditar(md)
        self.assertTrue(any("SIN LLAMADA" in p for p in problemas))

    def test_la_cadena_incompleta_se_denuncia(self):
        """`1, 2, 3, 8` es un agujero, no una numeración rara."""
        md = ("a[^1] b[^2] c[^3] d[^8]\n\n[^1]: x\n\n[^2]: x\n\n[^3]: x\n\n[^8]: x\n")
        self.assertTrue(any("no es completa" in p for p in ap.auditar(md)))

    def test_un_aparato_sano_no_da_problemas(self):
        md = "a[^1] b[^2]\n\n[^1]: x\n\n[^2]: y\n"
        self.assertEqual(ap.auditar(md), [])


if __name__ == "__main__":
    unittest.main()


class CadenaSeparaAparato(unittest.TestCase):
    """`separar_por_cadena`: el bloque de notas cuando la sangría no sirve."""

    def test_la_proximidad_es_parte_de_la_señal(self):
        """Una llamada suelta cerca del cuerpo NO debe abrir el aparato.

        Sin exigir contigüidad, un «132» que el OCR dejó flotando bajo un título
        empareja con la nota «133» del pie cuarenta líneas más abajo y el bloque
        arranca donde no es: se llevaría media página de prosa al aparato.
        """
        lineas = (["132"] + ["prosa del cuerpo."] * 30 +
                  ["133 La nota de verdad.", "134 Y la siguiente."])
        cuerpo, apar = ap.separar_por_cadena(lineas)
        self.assertEqual(len(apar), 2)
        self.assertIn("prosa del cuerpo.", cuerpo)

    def test_un_numero_no_consecutivo_es_continuacion(self):
        """«128 below» dentro de una nota no abre nota nueva ni rompe la cadena.

        Es el mismo principio que la guarda 2, en la otra punta del proceso: si
        cualquier cifra abriera nota, una remisión interna o el folio del pie
        partiría la nota en dos y correría toda la numeración.
        """
        lineas = ["12 Primera nota.", "128 below, dice el texto.", "13 Segunda nota."]
        notas = ap.notas_por_cadena(lineas)
        self.assertEqual(sorted(notas), [12, 13])
        self.assertIn("128 below", notas[12])

    def test_el_cursor_no_ancla_hacia_atras(self):
        """`anclar_por_cursor`: cada llamada se busca tras la anterior.

        Sin cursor, la nota 2 se ancla sobre el «2» de una cifra de prosa que
        está páginas antes, y la nota acaba en otra frase sin que al leer se note.
        """
        txt = "En 2 lugares dijo algo,1 y luego lo repitió,2 según consta."
        out = ap.anclar_por_cursor(txt, [1, 2])
        self.assertIn("algo,[^1]", out)
        self.assertIn("repitió,[^2]", out)
        self.assertTrue(out.startswith("En 2 lugares"))   # la cifra de prosa, intacta


class Reparto(unittest.TestCase):
    """`repartir`: cada definición al final de la sección que la invoca."""

    def test_cada_definicion_va_con_su_capitulo(self):
        md = ("## Uno\n\ntexto[^1]\n\n## Dos\n\ntexto[^2]\n\n"
              "## Notes\n\n[^1]: una\n\n[^2]: otra\n")
        out, st = ap.repartir(md, level=2)
        self.assertEqual(st["moved"], 2)
        uno = out.index("## Uno")
        dos = out.index("## Dos")
        self.assertLess(uno, out.index("[^1]: una"))
        self.assertLess(out.index("[^1]: una"), dos)      # la 1 se queda en «Uno»

    def test_una_definicion_sin_llamada_no_se_borra(self):
        """Perderla es peor que dejarla descolocada: se conserva y se reporta."""
        md = "## Uno\n\ntexto[^1]\n\n## Notes\n\n[^1]: una\n\n[^9]: huérfana\n"
        out, st = ap.repartir(md, level=2)
        self.assertEqual(st["orphan_defs"], ["9"])
        self.assertIn("[^9]: huérfana", out)
