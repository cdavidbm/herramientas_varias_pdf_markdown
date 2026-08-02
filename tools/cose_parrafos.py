#!/usr/bin/env python3
"""cose_parrafos.py — une los párrafos que un bisturí PARTIÓ en el salto de página.

`pdf_rich_to_markdown.py` abre párrafo nuevo en cada cambio de página, así que un
párrafo que cruza de página sale roto A MEDIA FRASE:

    …subdividió el abanico de la cábala «aceptable» mucho más sutilmente. En numerosas

    ocasiones Idel ha argumentado, *contra* Scholem, que…

Se lee, pero no es markdown correcto: al maquetar salen dos párrafos con sangría
donde el libro tiene uno, y el corte cae a mitad de oración.

**La señal decisiva es que el párrafo anterior NO CIERRA FRASE.** Un párrafo
legítimo termina en `.`, `!`, `?`, `…`, `:` o `;` (admitiendo comillas, paréntesis
o una llamada de nota detrás). Si no termina así, está partido.

Exigir además que el siguiente ABRA EN MINÚSCULA —la primera versión de este
script— deja fuera dos casos muy frecuentes y medidos en Lehrich:

    …al tratar las imágenes y representaciones (el tipo A)
    en la magia *celeste*, mientras que…      ← el `)` fingía cierre de frase

    …es la forma ejemplar de magia natural para ambos pensadores, aunque
    Ficino, para defender ciertas prácticas…  ← continúa en MAYÚSCULA

Por eso el cierre de frase exige puntuación TERMINAL de verdad (un `)` o un `»`
sueltos no cierran nada), y se une también cuando el corte cae tras una **coma**
—ningún párrafo termina en coma— o tras una **palabra función abierta**
(conjunción, preposición, artículo, relativo), que no puede ser la última de un
párrafo aunque la siguiente empiece por mayúscula.

**Guardas.** No se cose alrededor de una CITA EN BLOQUE (ahí la interrupción es
del original: la frase del autor entra en la cita y sale de ella), ni con
encabezados, tablas, imágenes, listas ni definiciones de nota. Y se protege el
bloque que es UN SUBTÍTULO EN CURSIVA o una LEYENDA de figura: no cierran frase y
serían falsos positivos garantizados.

Uso:
    python3 cose_parrafos.py ./es/*.md            # dry-run, informa
    python3 cose_parrafos.py ./es/*.md --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Cierre de frase REAL: puntuación terminal, admitiendo comillas/paréntesis de
# cierre y una llamada de nota detrás. Un `)` o un `»` por sí solos NO cierran.
FIN = re.compile(r"""[.!?…:;]        # terminal de verdad
                     ['"»”’\)\]]*    # comillas o paréntesis de cierre
                     \s*(?:\[\^[^\]]+\])?   # llamada de nota
                     \s*['"»”’\)\]]*\s*$""", re.X)

NO_PROSA = ("#", "|", "!", ">", "[^", "---", "***", "- ", "* ", "+ ", "```")

# Palabra con la que NINGÚN párrafo puede terminar: si el corte cae ahí, continúa.
ABIERTAS = set("""
a al ante bajo cabe con contra de del desde durante en entre hacia hasta mediante
para por según sin so sobre tras versus vía
el la los las un una unos unas lo
y e o u ni que qué quien quienes cuyo cuya cuyos cuyas cual cuales donde cuando
como si pero mas aunque sino porque pues mientras aunque cuanto cuanta
su sus mi mis tu tus nuestro nuestra nuestros nuestras
se le les lo me te nos os
es son era eran fue fueron ser sido estar está están
the a an of in on at to for from by with without within into onto upon
and or nor but yet so although though while whereas because since unless until
that which who whom whose what where when how
his her its their our your my this these those such
is are was were be been being has have had do does did
""".split())
# NO van aquí los ADVERBIOS de enlace («además», «también», «finalmente», *also*,
# *furthermore*): sí pueden cerrar el renglón que ENTRA en una cita en bloque
# —«…su práctica mágica evita la idolatría. Además,» + la cita de Agripa—, y
# tratarlos como palabra abierta funde la entradilla con la cita.

# Un subtítulo en cursiva («*Caracteres planetarios*») o una leyenda de figura
# tampoco cierran frase, pero no están partidos: son bloques completos.
SOLO_CURSIVA = re.compile(r"^\*{1,2}[^*].*[^*]\*{1,2}$")
LEYENDA = re.compile(r"^\*?(Figura|Figure|Tabla|Table|Lámina)\s+\d+", re.I)


def es_prosa(p: str) -> bool:
    s = p.strip()
    return bool(s) and not s.startswith(NO_PROSA)


def puede_continuar(prev: str) -> bool:
    """¿El bloque anterior está PARTIDO (no es un bloque completo por sí mismo)?"""
    s = prev.strip()
    if not es_prosa(s) or FIN.search(s):
        return False
    if SOLO_CURSIVA.match(s) or LEYENDA.match(s):
        return False            # subtítulo o leyenda: completo aunque no cierre frase
    return True


def ultima_palabra(s: str) -> str:
    m = re.findall(r"[^\W\d_]+", s.strip("*_ \t"), re.UNICODE)
    return m[-1].lower() if m else ""


def motivo(prev: str, sig: str) -> str | None:
    """Devuelve por qué se unen, o None si no hay que unir.

    `DUDOSO:` marca el caso que NO se une: una coma o un conector seguidos de un
    bloque largo en mayúscula es casi siempre la ENTRADILLA de una cita en bloque
    («…su práctica mágica evita la idolatría. Además,» + la cita de Agripa), no un
    párrafo partido. Unirlas destruiría la cita, así que se reporta para mirarla.
    """
    if not puede_continuar(prev) or not es_prosa(sig):
        return None
    s = sig.strip()
    if SOLO_CURSIVA.match(s) or LEYENDA.match(s):
        return None
    p = prev.rstrip()
    if s[:1].islower() or s[:1].isdigit():
        return "minúscula"
    # Una preposición, conjunción o artículo NO puede ser la última palabra de un
    # párrafo: ahí no hay ambigüedad posible, aunque lo que siga vaya en mayúscula.
    if ultima_palabra(p) in ABIERTAS:
        return f"«{ultima_palabra(p)}»"
    # La coma sí es ambigua: puede ser un corte de página o la ENTRADILLA de una
    # cita en bloque que el bisturí no marcó («…evita la idolatría. Además,»).
    if p.endswith(","):
        return ("DUDOSO:coma" if len(s.split()) >= 45 else "coma")
    return None


def cose(md: str) -> tuple[str, int, list[str], list[str]]:
    partes = md.split("\n\n")
    out: list[str] = []
    n = 0
    detalle: list[str] = []
    dudosos: list[str] = []
    for p in partes:
        s = p.strip()
        if out:
            por = motivo(out[-1], s)
            if por and por.startswith("DUDOSO:"):
                dudosos.append(f"[{por[7:]}] …{out[-1].rstrip()[-46:]} ⟶ {s[:46]}…")
            elif por:
                detalle.append(f"[{por}] …{out[-1].rstrip()[-46:]} ⟶ {s[:46]}…")
                out[-1] = out[-1].rstrip() + " " + s
                n += 1
                continue
        out.append(p if not s else s)
    return "\n\n".join(out), n, detalle, dudosos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    ap.add_argument("--verbose", action="store_true", help="muestra cada unión")
    a = ap.parse_args()
    tot = toc = dud = 0
    for f in a.files:
        if not f.is_file():
            print(f"warning: no existe {f}", file=sys.stderr)
            continue
        orig = f.read_text(encoding="utf-8")
        nuevo, n, detalle, dudosos = cose(orig)
        nuevo = re.sub(r"\n{3,}", "\n\n", nuevo).rstrip() + "\n"
        dud += len(dudosos)
        if n or dudosos:
            toc += 1
            print(f"  {f.name}: {n} párrafo(s) cosido(s)"
                  + (f", {len(dudosos)} dudoso(s)" if dudosos else ""))
        if n:
            tot += n
            if a.apply:
                f.write_text(nuevo, encoding="utf-8")
            if a.verbose:
                for d in detalle:
                    print(f"      {d}")
        for d in dudosos:
            print(f"      DUDOSO (no unido, revísalo) {d}")
    print(f"\n{'APLICADO' if a.apply else 'DRY-RUN'} — {tot} uniones en {toc} archivo(s)"
          + (f"; {dud} caso(s) dudoso(s) SIN unir" if dud else ""))
    if not a.apply and tot:
        print("Revisa la lista y vuelve a lanzarlo con --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
