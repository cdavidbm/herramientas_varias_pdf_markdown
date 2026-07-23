#!/usr/bin/env python3
"""
pdf_restore_digits.py — Restaura las CIFRAS que la extracción borró en silencio
(«Arc of Direction = RA °'"» → «Arc of Direction = RA 307°06'49"»).

Por qué importa
---------------
Algunos PDF (sobre todo cursos y manuales maquetados con fuentes de símbolos)
tienen los dígitos en un recurso tipográfico que los bisturíes de texto pierden.
El resultado es DEVASTADOR y a la vez invisible: el párrafo se lee bien, el ratio
de palabras no se mueve, la ortografía está impecable… y sin embargo los cálculos
trabajados han quedado vacíos. En un capítulo de direcciones primarias, de horas
planetarias o de revoluciones solares, eso deja el texto sin su contenido real.
Ningún control de los habituales (§3d) lo detecta: hay que medirlo contra el PDF.

Medido en el «Diploma Course in Medieval Astrology» de Zoller: 610 cifras perdidas,
355 de ellas en una sola lección (todos los cálculos de direcciones primarias).

La idea clave
-------------
La línea dañada es EXACTAMENTE el texto del PDF con los dígitos suprimidos. Eso da
una clave de alineación que no requiere adivinar nada: si a ambos textos se les
quitan los dígitos, deben coincidir carácter a carácter. Cuando coinciden, el PDF
dice cuáles eran las cifras y dónde iban, y se reinsertan RECORRIENDO las dos
cadenas en paralelo, de modo que negritas, cursivas y anclajes `[^N]` no se tocan.

`pdftotext -layout` sí extrae esos dígitos correctamente: el fallo está en el
bisturí que produjo el markdown, no en el PDF. Por eso el PDF sirve de patrón.

Guardas (para no romper texto sano)
-----------------------------------
  * El tramo del PDF se VERIFICA: al quitarle los dígitos debe reproducir la línea.
    Si no, se descarta (se prueban desfases de ±2 caracteres antes de rendirse).
  * Solo se acepta la coincidencia ÚNICA en todo el PDF; si el texto aparece dos
    veces, no se toca.
  * `[^N]` se trata como los dígitos que representa: una llamada de nota bien puesta
    NO cuenta como cifra perdida.
  * La reinserción aborta la línea entera ante el menor desajuste: mejor dejar una
    cifra ausente que colocarla donde no va.
  * Nunca se deja una cifra suelta pegada a una palabra (sería una llamada de nota
    mal puesta, peor que la cifra ausente): esa línea se omite y se reporta.

Uso
---
    # una sección
    python3 pdf_restore_digits.py cap.md --pdf cap.pdf            # simulacro
    python3 pdf_restore_digits.py cap.md --pdf cap.pdf --apply

    # un libro entero: pares markdown → PDF en un JSON {"cap.md": "cap.pdf", ...}
    python3 pdf_restore_digits.py --pairs pares.json --apply

Deja `digitos_perdidos.json` junto al primer markdown con el detalle de lo hallado.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

MARK = re.compile(r"\*{1,3}|^#+ |^> |^- |^\| ")
NOTA = re.compile(r"\[\^(\d+)\]")
ANCLA = re.compile(r"\[\^\d+\]")


def plano(s: str) -> str:
    """markdown → texto plano comparable con el del PDF."""
    s = NOTA.sub(r"\1", s)          # [^7] → 7 : el PDF lo trae como volado, no es pérdida
    return re.sub(r"\s+", " ", MARK.sub("", s)).strip()


def sindig(s: str) -> str:
    return re.sub(r"[0-9]", "", s)


def texto_pdf(pdf: pathlib.Path) -> str:
    r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0 and not r.stdout:
        sys.exit(f"error: pdftotext no pudo leer {pdf}")
    return re.sub(r"\s+", " ", r.stdout)


def detectar(md: pathlib.Path, pdf: pathlib.Path) -> list[dict]:
    """Líneas del markdown a las que les faltan dígitos respecto al PDF."""
    pnorm = texto_pdf(pdf)
    pnd = sindig(pnorm)
    idx = [j for j, ch in enumerate(pnorm) if not ch.isdigit()] + [len(pnorm)]

    out = []
    for i, linea in enumerate(md.read_text(encoding="utf-8").split("\n"), 1):
        p = plano(linea)
        if len(p) < 30 or linea.lstrip().startswith(("|", "![", "#")):
            continue
        key = sindig(p)
        pos = pnd.find(key)
        if pos < 0 or pnd.find(key, pos + 1) >= 0:       # ausente o no único
            continue
        bueno = None
        for off in (0, -1, 1, -2, 2):                    # corrige desfases de 1-2 chars
            a = pos + off
            if a < 0 or a + len(key) >= len(idx):
                continue
            cand = pnorm[idx[a]:idx[a + len(key)]].strip()
            if sindig(re.sub(r"\s+", " ", cand)).strip() == key.strip():
                bueno = cand
                break
        if bueno is None:
            continue
        faltan = sum(c.isdigit() for c in bueno) - sum(c.isdigit() for c in p)
        if faltan > 0:
            out.append({"md": md.name, "linea": i, "faltan": faltan,
                        "malo": linea, "bueno": bueno})
    return out


CIERRES = r"[\*\)\]”’\"']*"        # OJO: sin \s — la llamada va PEGADA a la palabra


def es_llamada(cola: str) -> bool:
    """¿La cifra que viene a continuación está en posición de LLAMADA de nota?

    Dos condiciones, y las dos hacen falta:

      * va PEGADA a la palabra («conjunction.²», «Part One.²»). Con un espacio de
        por medio es texto corriente: «RA MC 259°56’41”», «= July 31».
      * lo que precede es una PALABRA de verdad, no la cola alfabética de un dato
        alfanumérico: en «(tan 19s05)» la «s» es la marca de declinación sur y en
        «07°n30» la «n» es la de latitud norte — ninguna de las dos es palabra, y
        esos 05 y 30 no son notas. De ahí que una letra suelta pegada a un símbolo
        no valga: hace falta una palabra de dos letras o que empiece tras espacio.

    Sin esto, la reparación convierte segundos de arco y declinaciones en notas al
    pie, que es peor que dejar la cifra ausente.
    """
    c = re.sub(CIERRES + r"$", "", cola)
    c = re.sub(r"[.,;:!?]$", "", c)
    c = re.sub(CIERRES + r"$", "", c)
    m = re.search(r"([A-Za-z]+)$", c)
    if not m:
        return False
    previo = c[:m.start(1)]
    if previo and previo[-1].isdigit():
        return False
    if len(m.group(1)) == 1 and previo and not previo[-1].isspace():
        return False
    return True


def reinsertar(linea: str, bueno: str, notas: set[int],
               definidas: frozenset[int] = frozenset()) -> str | None:
    """Recorre línea y texto correcto EN PARALELO insertando los dígitos ausentes.

    Devuelve None si la correspondencia no es perfecta: entonces no se toca nada.
    Los dígitos que son llamada de una nota huérfana se insertan como `[^N]`.

    `notas` = huérfanas (se anclan);  `definidas` = todas las del archivo. La cifra
    en posición de llamada solo bloquea la línea si además es una nota REAL: si no,
    es notación corriente («°06’49”», «12/6») y se inserta sin más.
    """
    prot = [(m.start(), m.end()) for m in ANCLA.finditer(linea)]

    def en_ancla(k):
        return any(a <= k < b for a, b in prot)

    out, i, j = [], 0, 0
    while i < len(linea) and j < len(bueno):
        if en_ancla(i):                                  # copiar el ancla entera
            fin = next(b for a, b in prot if a <= i < b)
            out.append(linea[i:fin])
            i = fin
            continue
        ci, cj = linea[i], bueno[j]
        if ci == cj:
            out.append(ci); i += 1; j += 1
        elif ci == "*" and cj.isdigit():
            out.append(ci); i += 1                       # cerrar cursiva ANTES del dígito
        elif cj.isdigit():
            k = j
            while k < len(bueno) and bueno[k].isdigit():
                k += 1
            num = bueno[j:k]
            n = int(num)
            llamada = (es_llamada("".join(out[-8:]))
                       and (k >= len(bueno) or not bueno[k].isalnum()))
            if llamada and n in notas:
                out.append(f"[^{n}]")
            elif llamada and n in definidas:
                return None                              # llamada de nota que no se puede anclar
            else:
                out.append(num)
            j = k
        elif ci.isspace() and cj.isspace():
            out.append(ci); i += 1; j += 1
        elif ci.isspace():
            out.append(ci); i += 1
        elif cj.isspace():
            j += 1
        elif ci == "*":
            out.append(ci); i += 1
        else:
            return None
    if i < len(linea):
        if any(not c.isspace() and c != "*" and not en_ancla(k)
               for k, c in enumerate(linea[i:], i)):
            return None
        out.append(linea[i:])
    resto = bueno[j:]
    if resto.strip():
        if not all(c.isdigit() or c.isspace() for c in resto):
            return None
        n = int(resto.strip())
        out.append(f"[^{n}]" if n in notas else resto.rstrip())
    return "".join(out)


def huerfanas(txt: str) -> set[int]:
    """Notas definidas al pie que aún no tienen llamada en el cuerpo."""
    d = {int(m.group(1)) for m in re.finditer(r"^\[\^(\d+)\]:", txt, re.M)}
    r = {int(m.group(1)) for m in re.finditer(r"\[\^(\d+)\](?!:)", txt)}
    return d - r


def sueltas(s: str) -> int:
    """Cifras que quedan en posición de LLAMADA sin ser `[^N]`.

    Comparte criterio con `es_llamada`: si la reparación crea alguna de más, la
    línea se descarta, porque una llamada de nota mal puesta es peor que una cifra
    ausente. Los segundos de arco («°06’49”») no cuentan: van tras un dígito.
    """
    return sum(1 for m in re.finditer(r"\d{1,3}(?![0-9A-Za-z])", s)
               if es_llamada(s[max(0, m.start() - 12):m.start()]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md", nargs="*", type=pathlib.Path, help="markdown a reparar")
    ap.add_argument("--pdf", type=pathlib.Path, help="PDF de origen de esos markdown")
    ap.add_argument("--pairs", type=pathlib.Path,
                    help='JSON {"cap.md": "cap.pdf", ...} para un libro entero')
    ap.add_argument("--apply", action="store_true", help="escribir (por defecto: simulacro)")
    a = ap.parse_args()

    if a.pairs:
        crudo = json.loads(a.pairs.read_text(encoding="utf-8"))
        base = a.pairs.parent
        pares = [(base / k if not pathlib.Path(k).is_absolute() else pathlib.Path(k),
                  base / v if not pathlib.Path(v).is_absolute() else pathlib.Path(v))
                 for k, v in crudo.items()]
    elif a.md and a.pdf:
        pares = [(m, a.pdf) for m in a.md]
    else:
        ap.error("indica MD --pdf PDF, o bien --pairs pares.json")

    informe, ok, fallo = [], 0, 0
    for md, pdf in pares:
        if not md.exists() or not pdf.exists():
            print(f"  ! falta {md if not md.exists() else pdf}", file=sys.stderr)
            continue
        hallado = detectar(md, pdf)
        if not hallado:
            continue
        informe += hallado
        txt = md.read_text(encoding="utf-8")
        notas = huerfanas(txt)
        definidas = frozenset(int(m.group(1)) for m in re.finditer(r"^\[\^(\d+)\]:", txt, re.M))
        ls = txt.split("\n")
        tocado, n_ok = False, 0
        for r in hallado:
            i = r["linea"] - 1
            if ls[i] != r["malo"]:
                fallo += 1
                continue
            nueva = reinsertar(r["malo"], r["bueno"], notas, definidas)
            if nueva is None or sueltas(nueva) > sueltas(r["malo"]):
                fallo += 1
                continue
            for m in ANCLA.finditer(nueva):
                notas.discard(int(m.group(0)[2:-1]))
            ls[i] = nueva
            tocado = True
            n_ok += 1
            ok += 1
        print(f"{md.name:24s} cifras perdidas={sum(r['faltan'] for r in hallado):4d}  "
              f"líneas reparadas={n_ok:3d}")
        if tocado and a.apply:
            md.write_text("\n".join(ls), encoding="utf-8")

    if informe:
        destino = pares[0][0].parent / "digitos_perdidos.json"
        destino.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\ndetalle en {destino}")
    print(f"{'APLICADO' if a.apply else 'SIMULACRO'}: {ok} líneas reparadas, "
          f"{fallo} descartadas por seguridad")


if __name__ == "__main__":
    main()
