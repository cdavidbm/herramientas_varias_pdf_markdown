"""forja.aparato — el aparato de notas de un libro, de principio a fin.

Por qué es UN módulo y no seis programas
----------------------------------------
`tools/` tenía seis herramientas alrededor de las notas —`footnote_chain`,
`footnotes_rebuild`, `footnotes_from_pdf`, `footnotes_redistribute`,
`coteja_aparato`, `aparato_volados_aplanados`— que no son seis problemas: son
**cinco etapas del mismo problema**, y cada una había reimplementado por su
cuenta las mismas primitivas (qué es una definición, qué es una llamada, cómo
se sigue una cadena de números) con criterios que habían divergido en silencio.

    separar → reconstruir → ANCLAR (varias estrategias) → repartir → auditar

Lo que aquí se comparte no es cosmético: son las decisiones que, mal tomadas,
**pierden texto sin que ningún control lo note**. Van todas como guarda con su
test en `tests/test_aparato.py`; ninguna vive solo en prosa.

Las cinco guardas que cuestan un libro si faltan
------------------------------------------------
1. **Una definición es la que ABRE RENGLÓN.** Nunca «un `[^N]` no seguido de dos
   puntos»: hay llamadas legítimas delante de un dos puntos («…la realidad[^23]:»).
   Ese error aparece siempre disfrazado de «nota huérfana».
2. **La cadena puede SALTAR, pero nunca retrocede.** Exigir que avance de uno en
   uno la rompe en el primer número ausente y tira en cascada todo lo que sigue
   (medido en Lehrich y en al-Tilimsānī: en ambos se partía tras la nota 25). Un
   número que va HACIA ATRÁS, en cambio, es una cifra del cuerpo.
3. **Nada de regex ASCII.** En este fondo la llamada va pegada a `ī`, `ā`, `ḥ`,
   `ʿ`… y `[a-zA-Z]` la deja fuera (`al-Baghawī26`, medido). Tampoco se puede
   excluir el asterisco: se pierden las que siguen a un cierre de cursiva
   (`.”*397`).
4. **Enmascarar las OTRAS series de números antes de buscar.** Un libro con
   numeración de párrafo al margen (`**131.3**`, estilo Library of Arabic
   Literature) tiene DOS series entrelazadas; sin enmascarar, la cadena se rompe
   enseguida y se culpa a «las muchas cifras de la prosa». El relleno debe medir
   LO MISMO que lo enmascarado, o los offsets dejan de servir para sustituir.
5. **Auditar en los DOS sentidos.** «Toda llamada tiene definición» no basta:
   una definición sin llamada **no la imprime pandoc, y la descarta en silencio**
   (medido en *Nine Judges*: 1.463 notas de 1.995 no salieron, con el log limpio).
   Y la cadena de cada sección debe ser 1..N completa: un número repetido o fuera
   de orden es una llamada mal etiquetada que apunta a otra nota.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Una DEFINICIÓN abre renglón. Guarda 1.
DEFINICION = re.compile(r"^\[\^([^\]\s]+)\]:", re.M)
# Entrada de aparato todavía sin convertir, estilo «**12.** texto» o «12 texto».
ENTRADA_NUMERADA = re.compile(r"^\*\*(\d+)\.\*\*\s*(.+)$", re.M)
# Una LLAMADA pegada al carácter anterior: el volado aplanado. Guarda 3: se
# admite cualquier carácter que no sea espacio ni dígito (incluidos los
# diacríticos de transliteración y el `*` de cierre de cursiva).
#
# El rechazo por delante NO puede ser «hay un dos puntos o una raya», porque
# **sí hay llamadas legítimas tras un dos puntos** —«…the meaning of
# liminality:217», medido en al-Tilimsānī— y esa regla las borra. Es la misma
# trampa de la guarda 1 disfrazada. Lo que distingue una referencia de una
# llamada es qué hay ANTES del signo: en «17:110» y «1:1–3» es un DÍGITO; en una
# llamada es una letra. Por detrás no puede seguir nada que convierta la cifra en
# parte de un número mayor o de un rango.
LLAMADA_PEGADA = re.compile(r"(?<=[^\s\d])(?<!\d[:–-])(\d{1,3})(?![\d.:–-])")
# Numeración de párrafo al margen (LAL y similares). Guarda 4.
SERIE_PARRAFO = r"\*\*\d+\.\d+\*\*"


def definiciones(md: str) -> dict[str, str]:
    """Etiqueta → texto de cada definición `[^N]:` del markdown."""
    out = {}
    for m in re.finditer(r"^\[\^([^\]\s]+)\]:[ \t]*(.*)$", md, re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def llamadas(md: str) -> set[str]:
    """Etiquetas llamadas desde el CUERPO.

    Se quitan primero las líneas de definición y se cuenta lo que queda. Restar
    el conjunto de definiciones al de referencias —el atajo evidente— borra
    justamente las llamadas que SÍ tienen definición y deja el balance a cero.
    """
    cuerpo = re.sub(r"^\[\^[^\]\s]+\]:.*$", "", md, flags=re.M)
    return set(re.findall(r"\[\^([^\]\s]+)\]", cuerpo))


def enmascarar(texto: str, patrones: list[str]) -> str:
    """Tapa otras series de números conservando la LONGITUD (guarda 4)."""
    for pat in patrones:
        texto = re.sub(pat, lambda m: "§" * len(m.group(0)), texto)
    return texto


def cadena_ascendente(candidatos, tope: int, salto: int = 6, desde: int = 1):
    """Filtra candidatos `(pos, valor)` dejando una cadena que sube (guarda 2).

    Salta huecos de hasta `salto`, nunca retrocede y nunca pasa de `tope`.

    `desde` es dónde está la numeración al entrar, y **hay que pasarlo cuando el
    libro va repartido en archivos**: la cadena de un capítulo no empieza en 1,
    sino donde la dejó el anterior. Sin esto, el primer volado de cada archivo
    queda a más de `salto` del arranque y se descarta la sección entera — que es
    justo el modo en que un aparato se pierde sin que el balance se queje,
    porque las definiciones no anclada se van con él.
    """
    ult, out = desde - 1, []
    for pos, val in candidatos:
        if val > tope or val <= ult or val - ult > salto:
            continue
        out.append((pos, val))
        ult = val
    return out


def candidatos_pegados(texto: str, patrones=(SERIE_PARRAFO,)):
    """Posiciones de los volados aplanados, ya descontadas las otras series."""
    mask = enmascarar(texto, list(patrones))
    return [(m.start(), m.end(), int(m.group(1))) for m in LLAMADA_PEGADA.finditer(mask)]


@dataclass
class Aparato:
    """Las definiciones de un libro, con lo que hay que saber de ellas."""

    notas: dict[int, str] = field(default_factory=dict)

    @classmethod
    def de_entradas(cls, md: str) -> "Aparato":
        return cls({int(m.group(1)): m.group(2).strip() for m in ENTRADA_NUMERADA.finditer(md)})

    @property
    def tope(self) -> int:
        return max(self.notas) if self.notas else 0

    def huecos(self) -> list[int]:
        return [n for n in range(1, self.tope + 1) if n not in self.notas]

    def sospecha_truncamiento(self, tope_cuerpo: int) -> list[str]:
        """Avisos de que el aparato está CORTADO aunque parezca íntegro.

        Medido en al-Tilimsānī: 1..544 seguidas y sin huecos —internamente
        coherente— mientras el cuerpo llegaba a la 591; las 47 restantes estaban
        glutinadas dentro de la «entrada 544», de 375 palabras frente a una
        mediana de 5. Ni el rango, ni el balance, ni el recuento de palabras lo
        delatan; sí lo delatan estas dos señales.
        """
        avisos = []
        if tope_cuerpo > self.tope:
            avisos.append(
                f"el cuerpo llega a {tope_cuerpo} y el aparato a {self.tope}: "
                f"faltan {tope_cuerpo - self.tope} notas")
        if len(self.notas) >= 8:
            largos = sorted(len(t.split()) for t in self.notas.values())
            mediana = largos[len(largos) // 2]
            # Solo la ÚLTIMA entrada, no «la más larga». Un aparato normal mezcla
            # referencias de tres palabras con notas de comentario de doscientas, y
            # avisar de cualquier entrada larga da un falso positivo en casi todos
            # los libros (medido: la nota 95 de al-Tilimsānī, 201 palabras, es
            # legítima). El truncamiento tiene una forma concreta: el partidor se
            # rinde y vuelca lo que queda DENTRO DE LA QUE TENÍA ENTRE MANOS, que
            # por definición es la última que llegó a crear.
            cola = len(self.notas[self.tope].split())
            if mediana and cola > max(40, mediana * 20):
                avisos.append(
                    f"la ÚLTIMA entrada ({self.tope}) tiene {cola} palabras frente a una "
                    f"mediana de {mediana}: puede haberse tragado las siguientes")
        return avisos


def anclar(texto: str, tope: int, *, etiqueta: str = "", salto: int = 6,
           desde: int = 1, patrones=(SERIE_PARRAFO,)) -> tuple[str, list[int]]:
    """Convierte los volados aplanados en `[^N]`. Devuelve (texto, ancladas).

    `desde`: por dónde va la numeración al entrar (ver `cadena_ascendente`).

    Sustituye de ATRÁS hacia delante: hacerlo al derecho invalida los offsets
    calculados y desplaza cada anclaje un poco más que el anterior.
    """
    cands = candidatos_pegados(texto, patrones)
    cadena = cadena_ascendente([(a, v) for a, _b, v in cands], tope, salto, desde)
    elegidos = {a: v for a, v in cadena}
    puestas = []
    for a, b, v in reversed(cands):
        if elegidos.get(a) != v:
            continue
        assert texto[a:b] == str(v), f"descuadre de offsets en la nota {v}"
        texto = texto[:a] + f"[^{etiqueta}{v}]" + texto[b:]
        puestas.append(v)
    return texto, sorted(puestas)


def auditar(md: str) -> list[str]:
    """Problemas del aparato de UN archivo, en los dos sentidos (guarda 5)."""
    defs, refs = definiciones(md), llamadas(md)
    problemas = []
    huerfanas = sorted(set(defs) - refs)
    if huerfanas:
        problemas.append(
            f"{len(huerfanas)} definición(es) SIN LLAMADA — pandoc no las imprime "
            f"y las descarta en silencio: {huerfanas[:10]}")
    sin_def = sorted(refs - set(defs))
    if sin_def:
        problemas.append(f"{len(sin_def)} llamada(s) sin definición: {sin_def[:10]}")
    nums = sorted(int(x) for x in defs if x.isdigit())
    if nums:
        faltan = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
        if faltan:
            problemas.append(
                f"la cadena no es completa entre {nums[0]} y {nums[-1]}: faltan {faltan[:10]}")
    return problemas
