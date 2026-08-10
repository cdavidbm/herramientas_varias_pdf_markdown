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


# ─────────────────────────────────────────────────────────────────────────────
# Estrategia «cadena»: separar cuerpo y aparato cuando la sangría no sirve
# ─────────────────────────────────────────────────────────────────────────────
# Marcador en la MISMA línea; admite el número PEGADO a una mayúscula («25P
# gives»), porque el OCR se come el espacio.
FN_MISMA_LINEA = re.compile(r"^ {0,6}(\d{1,3})(?:\s+|(?=[A-Z]))(\S.*)$")
# Marcador SOLO en su renglón, con el texto debajo (estilo Flowers/Dykes).
FN_SOLO_NUMERO = re.compile(r"^\s*(\d{1,3})\s*$")
NUM_PAGINA = re.compile(r"^\s*\d{1,4}\s*$")


def _fn_re(numero_solo: bool):
    return FN_SOLO_NUMERO if numero_solo else FN_MISMA_LINEA


def separar_por_cadena(lineas, numero_solo=False, max_hueco=15):
    """(cuerpo, aparato) de una página cuando la ÚNICA señal fiable es que los
    números de nota corren consecutivos.

    La detección habitual —«las continuaciones van sangradas»— falla cuando se
    recortó una columna (el recorte reinicia el origen X) o el OCR aplastó la
    sangría. Aquí el aparato es el primer arranque cuyos números forman cadena de
    ≥2 **y están CONTIGUOS**: sin la proximidad, una llamada volada que el OCR
    dejó suelta cerca del cuerpo abre el bloque cuarenta líneas antes de donde
    empieza de verdad.
    """
    fn = _fn_re(numero_solo)
    marcas = [(i, int(fn.match(l).group(1))) for i, l in enumerate(lineas) if fn.match(l)]
    for si, (i0, n0) in enumerate(marcas):
        ult_i, ult_n, cuenta = i0, n0, 1
        for i, n in marcas[si + 1:]:
            if n == ult_n + 1:
                if i - ult_i <= max_hueco:
                    ult_i, ult_n, cuenta = i, n, cuenta + 1
                else:
                    break
            # un número no consecutivo es continuación: ni suma ni rompe
        if cuenta >= 2:
            return lineas[:i0], lineas[i0:]
    for i, ln in enumerate(lineas):
        if fn.match(ln) and i >= len(lineas) * 2 // 3:
            return lineas[:i], lineas[i:]
    return lineas, []


def notas_por_cadena(lineas_fn, numero_solo=False, corte=None) -> dict[int, str]:
    """Texto de cada nota. Solo abre nota nueva si el número es «anterior+1».

    Cualquier otra línea —incluida una que empiece por una cifra NO consecutiva:
    una remisión «128 below», un «3.3 above», el folio del pie— se acumula como
    continuación. Sin esa regla, una referencia de página parte la nota en dos y
    desde ahí toda la numeración se corre.
    """
    fn = _fn_re(numero_solo)
    notas, act = {}, None
    for ln in lineas_fn:
        if corte and corte.search(ln):
            break
        m = fn.match(ln)
        if m and (act is None or int(m.group(1)) == act + 1):
            act = int(m.group(1))
            notas[act] = "" if numero_solo else m.group(2).strip()
        elif act is not None and ln.strip() and not NUM_PAGINA.match(ln):
            notas[act] = (notas[act] + " " + ln.strip()).strip()
    return {n: t for n, t in notas.items() if t}


def anclar_por_cursor(texto: str, numeros) -> str:
    """Ancla llamadas aplastadas («voice,9») con un cursor que solo avanza.

    Las llamadas salen en el mismo orden que las notas, así que cada número se
    busca A PARTIR de donde se ancló el anterior. Sin el cursor se ancla sobre la
    primera cifra que coincida —casi siempre una de la prosa, páginas antes—, y
    ese anclaje falso mueve la nota a otra frase sin que al leer se note.
    """
    cursor = 0
    for n in sorted(numeros):
        pegado = re.compile(rf"(?<=[A-Za-z\)\.\,\;\'’]){n}(?![0-9])")
        suelto = re.compile(rf"(?<=[A-Za-z\)\.\,\;\'’]) {n}(?![0-9])")
        m = pegado.search(texto, cursor) or suelto.search(texto, cursor)
        if m:
            texto = texto[:m.start()] + f"[^{n}]" + texto[m.end():]
            cursor = m.start() + len(f"[^{n}]")
    return texto


def procesar_pagina(texto_pagina: str, numero_solo=False, corte=None) -> str:
    """Separa cuerpo/aparato de UNA página, ancla y emite markdown con `[^N]`."""
    lineas = texto_pagina.split("\n")
    cuerpo_l, fn_l = separar_por_cadena(lineas, numero_solo)
    notas = notas_por_cadena(fn_l, numero_solo, corte)
    cuerpo = "\n".join(cuerpo_l).strip()
    if notas:
        cuerpo = anclar_por_cursor(cuerpo, notas.keys())
        cuerpo += "\n\n" + "\n".join(f"[^{n}]: {notas[n]}" for n in sorted(notas))
    return cuerpo


# ─────────────────────────────────────────────────────────────────────────────
# Reparto: cada definición al final de la sección donde está su llamada
# ─────────────────────────────────────────────────────────────────────────────
# Va ANTES de trocear por capítulos. Si el aparato vive junto al final del
# archivo, el troceo se lleva TODAS las definiciones al último trozo y los
# capítulos anteriores quedan con las llamadas huérfanas — que pandoc descarta
# en silencio. El balance del archivo sin trocear no lo ve.
DEFINICION_LINEA = re.compile(r"^\[\^([^\]]+)\]:")
REFERENCIA = re.compile(r"\[\^([^\]]+)\]")
ENCABEZADO = re.compile(r"^(#{1,6})\s+(.*)$")
VALLA = re.compile(r"^\s*(```|~~~)")


def _marca_vallas(lines: list[str]) -> list[bool]:
    """Por línea, si está dentro de un bloque de código cercado."""
    inside = False
    out: list[bool] = []
    for ln in lines:
        if VALLA.match(ln):
            out.append(True)
            inside = not inside
            continue
        out.append(inside)
    return out


def repartir(text: str, level: int) -> tuple[str, dict]:
    lines = text.split("\n")
    fenced = _marca_vallas(lines)

    # 1. Localizar las definiciones (fuera de código).
    def_idx: dict[str, int] = {}
    def_lines: set[int] = set()
    for i, ln in enumerate(lines):
        if fenced[i]:
            continue
        m = DEFINICION_LINEA.match(ln)
        if m and m.group(1) not in def_idx:
            def_idx[m.group(1)] = i
            def_lines.add(i)

    stats = {"defs": len(def_idx), "moved": 0, "orphan_defs": [], "unresolved_refs": []}
    if not def_idx:
        return text, stats

    # 2. Trocear el cuerpo en secciones del nivel pedido.
    #    bounds[k] = (inicio, fin_exclusivo) de la sección k; la 0 es el preámbulo.
    starts = [0]
    for i, ln in enumerate(lines):
        if fenced[i] or i in def_lines:
            continue
        m = ENCABEZADO.match(ln)
        if m and len(m.group(1)) == level:
            starts.append(i)
    starts = sorted(set(starts))
    bounds = [(s, starts[k + 1] if k + 1 < len(starts) else len(lines))
              for k, s in enumerate(starts)]

    # 3. Sección de la PRIMERA llamada de cada etiqueta.
    target: dict[str, int] = {}
    for k, (s, e) in enumerate(bounds):
        for i in range(s, e):
            if fenced[i] or i in def_lines:
                continue
            for label in REFERENCIA.findall(lines[i]):
                if label in def_idx and label not in target:
                    target[label] = k

    for label in def_idx:
        if label not in target:
            stats["orphan_defs"].append(label)

    # Llamadas sin definición (solo informativo).
    seen_refs: set[str] = set()
    for i, ln in enumerate(lines):
        if fenced[i] or i in def_lines:
            continue
        seen_refs.update(REFERENCIA.findall(ln))
    stats["unresolved_refs"] = sorted(seen_refs - set(def_idx))

    # 4. Reconstruir: las definiciones reubicadas salen de su sitio y se
    #    reinyectan al final de su sección (en orden de etiqueta original).
    moved = {lab for lab in def_idx if lab in target}
    stats["moved"] = len(moved)

    per_section: dict[int, list[str]] = {}
    for lab, k in target.items():
        per_section.setdefault(k, []).append(lab)
    for k in per_section:
        per_section[k].sort(key=lambda lab: def_idx[lab])

    # El encabezado que precede al bloque de notas se borra si se queda sin
    # ninguna definición debajo.
    first_def = min(def_idx.values())
    heading_to_drop = None
    if not stats["orphan_defs"]:
        for i in range(first_def - 1, -1, -1):
            if lines[i].strip() == "":
                continue
            if ENCABEZADO.match(lines[i]) and not fenced[i]:
                heading_to_drop = i
            break

    out: list[str] = []
    for k, (s, e) in enumerate(bounds):
        body: list[str] = []
        for i in range(s, e):
            if i == heading_to_drop:
                continue
            if i in def_lines:
                lab = DEFINICION_LINEA.match(lines[i]).group(1)  # type: ignore[union-attr]
                if lab in moved:
                    continue  # se reinyecta en su sección
            body.append(lines[i])
        while body and body[-1].strip() == "":
            body.pop()
        if per_section.get(k):
            if body:
                body.append("")
            body.extend(lines[def_idx[lab]] for lab in per_section[k])
        out.extend(body)
        out.append("")

    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n", stats


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
