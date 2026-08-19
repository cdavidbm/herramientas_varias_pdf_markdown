#!/usr/bin/env python3
"""aparato_lista_a_definiciones.py — convierte el bloque de notas de LISTA OCR a
definiciones `[^N]:` de pandoc, decidiendo el número por la CADENA, no a ojo.

Cuándo se usa
-------------
Cuando el conversor ya dejó el aparato separado bajo un encabezado (`## Notas`) y
el cuerpo ya tiene sus llamadas `[^N]`, pero las definiciones siguen siendo la
lista cruda del OCR. Mientras estén así, **pandoc no imprime ni una nota**: sólo
saca la nota si existe la definición `[^N]:`, y una entrada de lista no lo es.

El problema real: hay DOS números por entrada
---------------------------------------------
El markdown de la lista abre cada entrada con un **contador** que puso el propio
conversor (`1.`, `2.`, `3.`…) y detrás viene el **número real de la nota**, que es
el que importa y el que el OCR destroza (se come el primer dígito: 11 -> «1»,
115 -> «15»). Tomar el contador por el número de nota descoloca el aparato entero
en cuanto el libro tenga una definición ausente; tomar el número OCR a ciegas
descoloca donde el OCR falló.

Lo que decide es la CADENA, con tres señales que se cruzan:

1. **El conjunto de llamadas del cuerpo** dice qué números EXISTEN de verdad.
2. **El orden**: las entradas van en orden y la cadena nunca retrocede. Puede
   SALTAR (una definición ausente es normal), pero no volver atrás.
3. **El número OCR** de cada entrada, como evidencia — no como autoridad.

Un número que retrocede o que no está en el conjunto de llamadas no es un número
de nota: es un folio o una cifra del texto. Se ignora y el hueco se deduce por la
cadena, y sólo cuando la deducción es FORZADA (un único valor posible entre sus
vecinos). Si no lo es, la entrada se deja sin asignar y se informa: es preferible
una nota menos a una nota puesta en el sitio de otra.

Dos fallos del método, medidos
------------------------------
**(a) Un número alto falso envenena todo lo que viene detrás.** Si se recorre la
lista de izquierda a derecha aceptando el primer candidato que no retroceda, UNA
cifra alta espuria deja el listón por encima de las notas siguientes y todas se
rechazan en cascada. Medido en el cap. 3: 99 asignadas de 182, y las 83 perdidas
eran correlativas a partir del punto del error. La cadena hay que resolverla como
**subsecuencia creciente más larga**, que descarta el intruso en vez de rendirse
ante él.

**(b) Las entradas no siempre abren renglón.** Cuando el OCR aplasta el pie, las
notas de una página quedan CONCATENADAS en un párrafo, así que un partidor que
sólo mire el principio de línea encuentra una entrada donde hay treinta. Medido:
en el cap. 2 detectaba 3 de 268. Hay que buscar los números también dentro del
párrafo, y ahí es la cadena la que dice cuáles son notas y cuáles son cifras del
texto.

**(c) El OCR TRUNCA el número, y siempre los mismos.** Los que faltaban en tres
capítulos distintos eran 11, 31, 51, 61, 71, 81: números acabados en 1, a los que
el reconocimiento se come el último dígito y deja «1», «3», «5». Como esa cifra
retrocede, la cadena la rechaza —con razón— y la nota se pierde. Pero el hueco es
deducible: si entre dos notas consecutivas falta UNA y en ese tramo hay un número
que es el truncamiento de la que falta, ahí empieza. Se exige que el candidato
sea ÚNICO en el tramo; si hay dos, se deja el hueco y se informa.

La trampa que cuesta ver
------------------------
Una nota partida en dos renglones cuyo segundo renglón ARRANCA CON EL NÚMERO DE
PÁGINA de la cita («342.2]) and once in…», «207.9-11): …») es idéntica, para
cualquier partidor, a una entrada nueva. La cadena la rechaza —ese número no es
una nota— pero entonces hay que **coserla a la nota anterior CON su número**, que
es parte de la referencia: si se imprime aparte, la cita queda mutilada por los
dos lados. Se reconoce en que, quitado el número, el texto NO empieza como
empieza una nota (mayúscula, comilla o cursiva), sino a media frase.

Uso
---
    python3 aparato_lista_a_definiciones.py cap.md            # informe
    python3 aparato_lista_a_definiciones.py cap.md --apply
    python3 aparato_lista_a_definiciones.py cap.md --prefijo 7-   # etiquetas [^7-N]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

RE_ENTRADA = re.compile(r"^(\d{1,3})\.\s+(.*)$")
# Un número que abre nota: al principio de renglón o tras final de frase, y
# seguido de texto. La basura del volado («!5», «|12») va delante del dígito.
RE_CAND = re.compile(
    r"(?:(?<=^)|(?<=\n)|(?<=[.;:)\]”’»)])\s)[^\w\n]{0,3}(\d{1,3})[\.\)]?"
    r"(?:\s+(?=[^\s])|(?=[A-ZÀ-ÞΑ-Ω‘“«\"*_(]))", re.M)   # el nº puede ir PEGADO: «1S. Freud»
# El nº real abre el texto y el OCR lo deja sucio: «7», «!5», «|12», «l2».
RE_NUM_INICIAL = re.compile(r"^[^\w]{0,3}(\d{1,3})\b[\.\)]?\s*")


def bloque(texto: str, rotulo: str) -> tuple[str, str]:
    m = re.search(rf"^{rotulo}\s*$", texto, re.M)
    if not m:
        sys.exit(f"no encuentro el encabezado «{rotulo}»")
    return texto[:m.end()], texto[m.end():]


def llamadas(cuerpo: str, prefijo: str) -> list[int]:
    pat = re.escape(prefijo)
    return sorted({int(x) for x in re.findall(rf"\[\^{pat}(\d+)\]", cuerpo)})


def entradas(ap: str) -> list[tuple[int, str]]:
    """[(contador, texto)] en orden de aparición (una entrada por renglón)."""
    salida = []
    for linea in ap.split("\n"):
        m = RE_ENTRADA.match(linea.strip())
        if m:
            salida.append((int(m.group(1)), m.group(2).strip()))
    return salida


def creciente_mas_larga(valores: list[int]) -> list[int]:
    """Índices de la subsecuencia ESTRICTAMENTE creciente más larga.

    Es lo que hace que una sola cifra espuria no arrastre a las que vienen detrás.
    """
    if not valores:
        return []
    mejor: list[int] = []          # mejor[k] = índice del final de la mejor cadena de largo k+1
    previo = [-1] * len(valores)
    import bisect
    colas: list[int] = []          # colas[k] = valor final mínimo de esa longitud
    for i, v in enumerate(valores):
        k = bisect.bisect_left(colas, v)
        if k > 0:
            previo[i] = mejor[k - 1]
        if k == len(colas):
            colas.append(v)
            mejor.append(i)
        else:
            colas[k] = v
            mejor[k] = i
    salida, i = [], mejor[-1]
    while i >= 0:
        salida.append(i)
        i = previo[i]
    return salida[::-1]


def rellenar_huecos(ap: str, cands: list, elegidos: list[int], validos: set[int]) -> list[int]:
    """Recupera las notas cuyo número el OCR truncó (11 -> «1», 51 -> «5»).

    Sólo si el candidato es ÚNICO en el tramo entre las dos notas vecinas: una
    nota de menos es preferible a una nota partida por el sitio equivocado.
    """
    todos = [(m.start(), int(m.group(1)), m.end()) for m in RE_CAND.finditer(ap)]
    salida = list(elegidos)
    for j in range(len(elegidos)):
        num_a = cands[elegidos[j]][1]
        pos_a = cands[elegidos[j]][0]
        if j + 1 < len(elegidos):
            num_b, pos_b = cands[elegidos[j + 1]][1], cands[elegidos[j + 1]][0]
        else:
            num_b, pos_b = max(validos) + 1, len(ap)
        faltan = [n for n in sorted(validos) if num_a < n < num_b]
        desde = pos_a
        for m in faltan:
            posibles = [c for c in todos if desde < c[0] < pos_b
                        and c[1] != m
                        and (str(m).startswith(str(c[1])) or str(m).endswith(str(c[1])))]
            if len(posibles) != 1:
                continue          # ambiguo: mejor un hueco que una nota mal partida
            cands.append((posibles[0][0], m, posibles[0][2]))
            salida.append(len(cands) - 1)
            desde = posibles[0][0]
    return sorted(salida, key=lambda i: cands[i][0])


def trocear_por_cadena(ap: str, validos: set[int]) -> list[tuple[int, str]]:
    """Parte el bloque en (nº de nota, texto) usando la cadena de números.

    No exige que la entrada abra renglón: cuando el OCR aplasta el pie, las notas
    de una página van concatenadas en un párrafo.
    """
    cands = [(m.start(), int(m.group(1)), m.end()) for m in RE_CAND.finditer(ap)]
    cands = [c for c in cands if c[1] in validos]
    if not cands:
        return []
    elegidos = creciente_mas_larga([c[1] for c in cands])
    elegidos = rellenar_huecos(ap, cands, elegidos, validos)
    trozos = []
    for j, idx in enumerate(elegidos):
        _, num, fin = cands[idx]
        hasta = cands[elegidos[j + 1]][0] if j + 1 < len(elegidos) else len(ap)
        trozos.append((num, " ".join(ap[fin:hasta].split())))
    return trozos


def es_continuacion(texto: str) -> bool:
    """¿Esta «entrada» es en realidad el segundo renglón de la nota anterior?"""
    resto = RE_NUM_INICIAL.sub("", texto, count=1).lstrip()
    if not resto:
        return True
    return not (resto[0].isupper() or resto[0] in "‘“«\"'*_([")


def asignar(ents: list[tuple[int, str]], validos: set[int]) -> list[tuple[int | None, str]]:
    """Asigna a cada entrada su nº de nota. None = no se pudo decidir."""
    propuesto: list[int | None] = []
    minimo = 1
    for _, texto in ents:
        m = RE_NUM_INICIAL.match(texto)
        cand = int(m.group(1)) if m else None
        if cand is not None and cand in validos and cand >= minimo:
            propuesto.append(cand)
            minimo = cand + 1
        else:
            propuesto.append(None)

    # Deducir los huecos: sólo si entre los vecinos cabe UN único valor válido.
    for i, val in enumerate(propuesto):
        if val is not None:
            continue
        antes = next((v for v in reversed(propuesto[:i]) if v is not None), 0)
        despues = next((v for v in propuesto[i + 1:] if v is not None), max(validos) + 1)
        opciones = [n for n in validos if antes < n < despues]
        if len(opciones) == 1:
            propuesto[i] = opciones[0]

    return [(propuesto[i], ents[i][1]) for i in range(len(ents))]


def limpiar(texto: str) -> str:
    """Quita el nº real que abre el texto, con la basura que el OCR le pegó."""
    return RE_NUM_INICIAL.sub("", texto, count=1).strip()


def main() -> int:
    ap_cli = argparse.ArgumentParser()
    ap_cli.add_argument("archivo")
    ap_cli.add_argument("--rotulo", default="## Notas")
    ap_cli.add_argument("--prefijo", default="", help="p. ej. «7-» para etiquetas [^7-N]")
    ap_cli.add_argument("--apply", action="store_true")
    a = ap_cli.parse_args()

    p = pathlib.Path(a.archivo)
    t = p.read_text()
    cuerpo, bloque_ap = bloque(t, re.escape(a.rotulo))
    refs = llamadas(cuerpo, a.prefijo)
    if not refs:
        sys.exit("el cuerpo no tiene llamadas: ancla primero, o revisa --prefijo")
    asignadas = trocear_por_cadena(bloque_ap, set(refs))
    if not asignadas:
        sys.exit("no encuentro ninguna entrada: ¿es este el bloque correcto?")

    hechas = [n for n, _ in asignadas]
    sin_definir = [n for n in refs if n not in set(hechas)]
    repetidas = sorted({n for n in hechas if hechas.count(n) > 1})
    # Lo que queda ANTES de la primera nota es cola de la página anterior o el
    # asterisco de agradecimientos: no se tira, se avisa.
    cabecera = " ".join(bloque_ap[:RE_CAND.search(bloque_ap).start()].split())

    print(f"{p.name}: {len(refs)} llamadas · {len(asignadas)} notas troceadas")
    print(f"  sin definición : {len(sin_definir)}  {sin_definir[:20]}")
    if repetidas:
        print(f"  !! repetidas   : {repetidas}")
    if cabecera:
        print(f"  cabecera previa a la nota 1: {cabecera[:90]!r}")

    if not a.apply:
        print("  (informe: nada escrito; usa --apply)")
        return 0

    defs = [f"[^{a.prefijo}{n}]: {txt}" for n, txt in asignadas]
    sobras = [f"- {cabecera}"] if cabecera else []
    nuevo = cuerpo + "\n\n" + "\n\n".join(defs) + "\n"
    if sobras:
        # Nada se tira: lo que no se pudo numerar queda a la vista para decidirlo.
        nuevo += "\n### Entradas del aparato sin número seguro\n\n" + "\n\n".join(sobras) + "\n"
    p.write_text(nuevo)
    print(f"  -> escrito: {len(defs)} definiciones"
          + (f", {len(sobras)} entradas sin numerar al final" if sobras else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
