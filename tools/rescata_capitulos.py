#!/usr/bin/env python3
"""
rescata_capitulos.py — devuelve al CUERPO los capítulos que acabaron dentro del aparato.

DEFECTO (medido en §7, la séptima casa): 25 «definiciones de nota» no son notas, sino el
texto de un capítulo entero, con su título y su autoridad. Y de esos capítulos, **23 no
están en el cuerpo en absoluto**: ni su encabezado ni su texto. Es decir, 23 capítulos de
la sección se imprimirían como notas al pie al final, en vez de en su lugar.

No lo ve ningún control de los habituales: el balance de notas cuadra (son definiciones
válidas), el recuento de encabezados cuadra (nunca hubo encabezado que perder) y el ratio
de palabras cuadra (el texto está, solo que en el sitio equivocado).

CÓMO SE RECONOCEN
  · Arranque: la definición empieza por `§7.N: Título—Autoridad`.
  · Continuación: las definiciones SIGUIENTES cuyo texto abre en MINÚSCULA son la
    continuación del capítulo partida por el salto de página. La primera que abre como
    nota de verdad (mayúscula, cursiva, «Cf.», o el número del volado) cierra el bloque.

QUÉ HACE
  Ensambla cada bloque, lo convierte en `## §7.N: Título—Autoridad` + su prosa, y lo
  INSERTA en el cuerpo en su posición numérica (entre §7.N-1 y §7.N+1). Quita del aparato
  las definiciones consumidas.

LÍMITE HONESTO: algunos bloques traen, pegada al final, una nota de verdad del aparato
(«Leyendo X con Robert…»). Separarla con certeza exige cotejar la imagen, así que aquí se
CONSERVA dentro del bloque y se REPORTA, en vez de recortarla a ciegas. Es preferible una
nota que quede como prosa al final del capítulo a perderla.

Sirve para `en/` y para `es/` porque se ancla en `§7.N:`, que la traducción preserva.
Dry-run por defecto.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

DEF = re.compile(r"^\[\^([\d-]+)\]: (.*)$", re.M)
CAP = re.compile(r"^§(\d+)\.(\d+):\s*(.*)$")
# una nota de verdad abre en mayúscula, cursiva, comilla, paréntesis o con el nº del volado
NOTA = re.compile(r'^[\s]*(?:[*"“(\[¡¿A-ZÁÉÍÓÚÑ0-9]|[|lT](?=\s))')
# la nota que abre con un número suelto es el volado que el OCR sí leyó
COLA_NOTA = re.compile(r"^\s*\d{1,3}\s+\S")


def separa(txt: str) -> tuple[str, str]:
    m = DEF.search(txt)
    return (txt[:m.start()], txt[m.start():]) if m else (txt, "")


def bloques(aparato: str) -> tuple[list[dict], set[str]]:
    defs = DEF.findall(aparato)
    encontrados, consumidas = [], set()
    for i, (lab, cont) in enumerate(defs):
        m = CAP.match(cont)
        if not m:
            continue
        piezas, usadas = [m.group(3)], [lab]
        for lab2, cont2 in defs[i + 1:]:
            if NOTA.match(cont2) or COLA_NOTA.match(cont2):
                break
            piezas.append(cont2)
            usadas.append(lab2)
        encontrados.append({
            "seccion": m.group(1), "num": int(m.group(2)),
            "texto": " ".join(piezas), "labels": usadas,
        })
        consumidas.update(usadas)
    return encontrados, consumidas


def inserta(cuerpo: str, caps: list[dict]) -> tuple[str, list[str]]:
    lineas = cuerpo.split("\n")
    avisos = []
    for c in sorted(caps, key=lambda x: -x["num"]):        # de mayor a menor: no desplaza
        titulo, _, resto = c["texto"].partition(" ")
        # el título va hasta la autoridad («—Autor»); el resto es prosa del capítulo
        m = re.match(r"(.*?—\s*\S+?)\s+(.*)$", c["texto"], re.S)
        cabeza, prosa = (m.group(1), m.group(2)) if m else (c["texto"][:70], c["texto"][70:])
        enc = f"## §{c['seccion']}.{c['num']}: {cabeza}"
        # posición: antes del primer capítulo con número MAYOR
        pos = len(lineas)
        for i, l in enumerate(lineas):
            mm = re.match(rf"^## §{c['seccion']}\.(\d+):", l)
            if mm and int(mm.group(1)) > c["num"]:
                pos = i
                break
        lineas[pos:pos] = [enc, "", prosa.strip(), ""]
        if len(c["labels"]) > 1:
            avisos.append(f"§{c['seccion']}.{c['num']}: reunido de "
                          f"{len(c['labels'])} etiquetas ({', '.join(c['labels'])})")
    return "\n".join(lineas), avisos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("md", type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    txt = a.md.read_text(encoding="utf-8")
    cuerpo, aparato = separa(txt)
    caps, consumidas = bloques(aparato)
    if not caps:
        print("no hay capítulos atrapados en el aparato")
        return

    # avisar de las etiquetas consumidas que TIENEN llamada en el cuerpo
    con_llamada = [l for l in consumidas if re.search(r"\[\^" + re.escape(l) + r"\](?!:)", cuerpo)]
    nuevo_cuerpo, avisos = inserta(cuerpo, caps)
    nuevo_ap = "\n".join(l for l in aparato.split("\n")
                         if not (DEF.match(l) and DEF.match(l).group(1) in consumidas))
    # las líneas huérfanas de una definición consumida (continuaciones ya absorbidas)
    print(f"capítulos rescatados: {len(caps)} · definiciones consumidas: {len(consumidas)}")
    for c in sorted(caps, key=lambda x: x["num"]):
        print(f"   §{c['seccion']}.{c['num']:<4} ← {len(c['labels'])} etiq · "
              f"{len(c['texto'].split()):>4} palabras")
    for x in avisos:
        print("   · " + x)
    if con_llamada:
        print(f"\n   OJO: {len(con_llamada)} etiquetas consumidas tenían llamada en el cuerpo: "
              f"{sorted(con_llamada)[:8]}")
        print("        esas llamadas quedarán sin definición → hay que quitarlas o rehacerlas")
    if a.apply:
        a.md.write_text(nuevo_cuerpo.rstrip() + "\n\n" + nuevo_ap.strip() + "\n",
                        encoding="utf-8")
        print("\naplicado.")
    else:
        print("\n(dry-run: usa --apply)")


if __name__ == "__main__":
    main()
