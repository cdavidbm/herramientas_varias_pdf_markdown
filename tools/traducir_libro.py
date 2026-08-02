#!/usr/bin/env python3
"""traducir_libro.py — traduce un libro entero POR FASES, reanudable y verificado.

Por qué existe
--------------
Un libro grande no cabe en una sesión: *Three Books of Occult Philosophy* son
228.000 palabras y 214 archivos, ~18 horas de motor en serie. Hasta ahora eso se
orquestaba con un `for` en bash que se saltaba lo ya hecho mirando si el archivo
de salida existía — y esa comprobación es MALA: un archivo escrito a medias, o
uno que agy resumió, existe igual y se daba por bueno para siempre.

Aquí el criterio para dar un archivo por hecho no es que exista, sino que **pase
la verificación**: mismas `[^N]` (llamadas y definiciones), mismos encabezados,
mismas figuras y ratio de palabras en rango. El resultado se anota en un
**estado JSON tras CADA archivo**, así que una sesión interrumpida pierde como
mucho el archivo en curso, y relanzar sigue donde iba.

`--max N` traduce solo N archivos y para: son las «fases» pausables. `--fase`
(o `--desde/--hasta`) acota por slug para hacer un Libro cada vez.

El motor es `agy_retranslate_chunks.py`, que verifica CADA TROZO al vuelo (ver
la política de agy en el CLAUDE.md: el tamaño del archivo NO es un criterio
fiable, lo que protege es verificar por trozo).

Uso
---
    python3 traducir_libro.py en --out es --glosario glosario.md --prompt P.txt \\
        --desde 010 --hasta 084 --max 10 --parallel 2
    python3 traducir_libro.py en --out es --glosario g.md --prompt P.txt --estado   # solo informe
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REF = re.compile(r"\[\^([^\]]+)\](?!:)")
DEFLINE = re.compile(r"(?m)^\[\^([^\]]+)\]:")
HEAD = re.compile(r"(?m)^(#+) ")
IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

TOOL = Path(__file__).resolve().parent / "agy_retranslate_chunks.py"


def cuerpo(t: str) -> str:
    """Texto sin las definiciones de nota (para el ratio de prosa)."""
    return DEFLINE.sub("", t)


def verificar(en: str, es: str) -> list[str]:
    """Devuelve la lista de fallos; vacía = el archivo pasa."""
    fallos = []
    if not es.strip():
        return ["vacío"]
    r_en, r_es = sorted(set(REF.findall(en))), sorted(set(REF.findall(es)))
    d_en, d_es = sorted(set(DEFLINE.findall(en))), sorted(set(DEFLINE.findall(es)))
    if r_en != r_es:
        fallos.append(f"llamadas: faltan {sorted(set(r_en) - set(r_es))[:6]}")
    if d_en != d_es:
        fallos.append(f"definiciones: faltan {sorted(set(d_en) - set(d_es))[:6]}")
    if sorted(set(r_es)) != sorted(set(d_es)):
        fallos.append("el ES descuadra: llamadas ≠ definiciones")
    ratio = len(cuerpo(es).split()) / max(1, len(cuerpo(en).split()))
    if not 0.88 <= ratio <= 1.45:
        fallos.append(f"ratio {ratio:.2f}")
    if HEAD.findall(en) != HEAD.findall(es):
        fallos.append(f"encabezados {len(HEAD.findall(en))}≠{len(HEAD.findall(es))}")
    if IMG.findall(en) != IMG.findall(es):
        fallos.append("figuras distintas")
    # Una VALLA DE CÓDIGO en la salida del motor es demoledora y silenciosa: todo
    # lo que quede dentro se maqueta como texto literal, y las llamadas `[^N]` de
    # ahí dentro DEJAN DE SER llamadas, así que sus notas desaparecen del PDF sin
    # que nada lo delate —el recuento de encabezados incluso cuadra, porque el
    # regex de `#` casa igual dentro de la valla—. Medido en Agripa: un archivo
    # con medio capítulo encerrado en ```markdown y 6 notas perdidas.
    if re.search(r"(?m)^```", es) and not re.search(r"(?m)^```", en):
        fallos.append("VALLA DE CÓDIGO en la traducción (```) que el original no tiene")
    titulos = re.findall(r"(?m)^#+ (.+)$", es)
    if len(titulos) != len(set(titulos)):
        fallos.append("encabezado REPETIDO (agy reemitió un trozo)")
    fallos += verificar_tablas(en, es)
    fallos += verificar_notas_traducidas(en, es)
    sin = parrafos_sin_traducir(es)
    if sin:
        pal = sum(len(p.split()) for p in sin)
        fallos.append(f"{len(sin)} párrafo(s) SIN TRADUCIR ({pal} palabras): "
                      f"«{sin[0][:60]}…»")
    return fallos


def defs_texto(t: str) -> str:
    """El texto de TODAS las definiciones de nota, sin sus etiquetas."""
    return " ".join(re.findall(r"(?m)^\[\^[^\]]+\]:\s*(.+)$", t))


def verificar_notas_traducidas(en: str, es: str) -> list[str]:
    """El aparato puede quedarse ENTERO en el idioma origen sin que salte nada.

    Punto ciego medido en Agripa (32 archivos del Libro III): el cuerpo salía
    traducido y el bloque `## Notes` volvía intacto en inglés. No lo ve NINGÚN
    otro control: los `[^N]` cuadran, el ratio EXCLUYE las definiciones por
    diseño, y la comparación de encabezados mira los niveles `#`, no su texto.
    Aquí se compara el texto de las definiciones con el del original: si es
    prácticamente el mismo, no se tradujo.
    """
    # Señal barata y exacta que la guarda de tamaño no puede dar: el ENCABEZADO
    # del aparato. El conversor siempre escribe «## Notes», así que si sigue ahí
    # en la traducción, el bloque no se tocó — aunque sea corto y bibliográfico,
    # que es justo el caso donde la comparación de vocabulario se abstiene.
    fallos = []
    if re.search(r"(?m)^#+\s+Notes\s*$", en) and re.search(r"(?m)^#+\s+Notes\s*$", es):
        fallos.append("el encabezado «Notes» sigue sin traducir")

    # El discriminante NO puede ser el vocabulario ni las palabras funcionales: un
    # aparato de referencias es casi todo títulos y nombres propios —muchos en
    # INGLÉS de forma legítima—, y da 88 % de coincidencia estando perfectamente
    # traducido (medido en Lehrich). Lo que sí es concluyente es comparar CADA
    # definición con la SUYA: una nota traducida difiere de su original; una que
    # volvió intacta es idéntica carácter por carácter.
    dn = lambda t: {n: re.sub(r"\s+", " ", x).strip()
                    for n, x in re.findall(r"(?m)^\[\^([^\]]+)\]:\s*(.+)$", t)}
    A, B = dn(en), dn(es)
    # Solo cuentan las definiciones con PROSA suficiente: una nota que es una sola
    # palabra latina (*Westphaliae.*) es idéntica en los dos idiomas con toda
    # razón, y con tres así el archivo salía marcado sin motivo.
    comunes = [k for k in set(A) & set(B) if len(A[k].split()) >= 6]
    if len(comunes) < 3:
        return fallos
    iguales = sum(1 for k in comunes if A[k] == B[k])
    prop = iguales / len(comunes)
    if prop > 0.6:
        fallos.append(f"NOTAS SIN TRADUCIR ({iguales} de {len(comunes)} definiciones "
                      f"IDÉNTICAS al original)")
        return fallos

    # La proporción GLOBAL no basta, y falla justo donde más duele. Medido en
    # Lehrich: el capítulo 1 devolvió sin traducir las notas 54-102 y el 4 las
    # 98-124, y el archivo pasó con 57 % y 59 % —por debajo del umbral por un
    # pelo—, porque en un aparato bibliográfico MUCHAS notas son legítimamente
    # idénticas (una ficha con lugar y editorial en inglés lo es). Diluida entre
    # ellas, una tanda de notas de PROSA sin traducir no mueve el porcentaje.
    # El discriminante fino es la PROSA: una definición con varias palabras
    # función inglesas y ninguna diferencia respecto al original no se tradujo,
    # y basta UNA para reportarla. Una ficha pura no dispara: casi no tiene
    # palabras función («Yates, *Giordano Bruno* (Chicago: …, 1964), 130»).
    prosa = [k for k in comunes
             if A[k] == B[k] and len(A[k].split()) >= 8 and len(_ING.findall(A[k])) >= 3]
    if prosa:
        m = sorted(prosa, key=lambda s: (len(s), s))
        fallos.append(f"{len(prosa)} definición(es) de nota SIN TRADUCIR "
                      f"(idénticas al original y con prosa): {', '.join(m[:12])}"
                      + (" …" if len(m) > 12 else ""))
    return fallos


def tablas(t: str) -> list[list[int]]:
    """Cada tabla como la lista de nº de celdas de sus renglones."""
    out, cur = [], []
    for ln in t.split("\n"):
        if ln.lstrip().startswith("|"):
            cur.append(ln.count("|"))
        elif cur:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def verificar_tablas(en: str, es: str) -> list[str]:
    """Una tabla desmontada NO la ve ningún otro control.

    El ratio de palabras apenas se mueve si el motor funde dos columnas o se
    come un renglón, y el balance de notas ni se entera. En un libro cuyas
    tablas son el CONTENIDO —las Escalas de los números de Agripa son la obra
    misma— eso es pérdida grave e invisible. Aquí se compara la forma: mismo
    número de tablas, mismos renglones y mismas celdas por renglón.
    """
    a, b = tablas(en), tablas(es)
    if len(a) != len(b):
        return [f"TABLAS: {len(a)} en inglés, {len(b)} en español"]
    fallos = []
    for i, (x, y) in enumerate(zip(a, b), 1):
        if len(x) != len(y):
            fallos.append(f"tabla {i}: {len(x)} renglones ≠ {len(y)}")
        elif x != y:
            fallos.append(f"tabla {i}: columnas distintas en algún renglón")
    return fallos


def huella(texto: str) -> str:
    """Huella del archivo ORIGEN, guardada junto al resultado.

    Sin esto, «¿hay que retraducir este archivo?» se resuelve a mano, y a mano se
    falla: en Agripa cambié 78 archivos con una normalización de espacios que solo
    afectaba de verdad a 3, y di de baja 33 traducciones buenas. Con la huella, el
    propio programa sabe cuáles cambiaron. **Y nunca hace falta BORRAR el .md
    traducido**: el motor lo sobrescribe, así que borrarlo solo quita la red de
    seguridad si algo sale mal.
    """
    import hashlib
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


# Palabras funcionales: son las que de verdad marcan el idioma de un párrafo. Los
# sustantivos y nombres propios pueden coincidir (títulos, latín, transliteraciones),
# pero «the/of/and» frente a «el/de/y» no.
_ING = re.compile(r"\b(the|of|and|with|which|that|this|from|have|has|been|were|would|"
                  r"there|their|these|those|for|not|but|are|is|it|as|by|to|in|on|his|"
                  r"her|its|such|than|then|when|where|while|also|both|each|any)\b", re.I)
_ESP = re.compile(r"\b(el|la|los|las|de|del|y|con|que|para|por|una|un|unos|unas|se|es|"
                  r"son|su|sus|como|en|más|pero|no|al|lo|esta|este|estos|estas|ese|esa|"
                  r"cuando|donde|mientras|también|cada|entre|sobre|sin|desde)\b", re.I)


def parrafos_sin_traducir(es: str, min_pal: int = 5) -> list[str]:
    """Párrafos que volvieron en el IDIOMA ORIGEN.

    **El ratio de palabras NO ve esto**, y es su punto ciego más caro: un trozo sin
    traducir ocupa aproximadamente lo mismo que ocuparía traducido, así que el ratio
    sale perfecto. Medido en Lehrich: 13 párrafos seguidos —1.260 palabras— en inglés
    dentro de un archivo con ratio 1.073 que había pasado TODOS los demás controles.

    Se decide por PALABRAS FUNCIONALES, no por vocabulario: los nombres propios, los
    títulos y el latín coinciden en ambos idiomas, pero «the/of/and» frente a
    «el/de/y» no. Se ignoran las definiciones de nota (las juzga
    verificar_notas_traducidas) y los bloques cortos, donde la señal no es fiable.
    """
    malos = []
    for p in es.split("\n\n"):
        s = p.strip()
        if not s or s.startswith(("[^", "|", "!", "#")):
            continue
        cuerpo_p = re.sub(r"(?m)^>\s?", "", s)
        n_pal = len(cuerpo_p.split())
        if n_pal < min_pal:
            continue
        ni, ne = len(_ING.findall(cuerpo_p)), len(_ESP.findall(cuerpo_p))
        # En bloques CORTOS (títulos de sección, leyendas) basta una funcional
        # inglesa y ninguna española: «*Magic Squares and Figures*». En los largos
        # se exige mayoría, para no marcar prosa con muchos títulos citados.
        if (ni > ne) if n_pal >= 15 else (ni >= 1 and ne == 0):
            malos.append(s)
    return malos


def metricas(en: str, es: str) -> dict:
    return {"ratio": round(len(cuerpo(es).split()) / max(1, len(cuerpo(en).split())), 3),
            "llamadas": len(set(REF.findall(es))),
            "definiciones": len(set(DEFLINE.findall(es))),
            "palabras": len(es.split())}


def traducir_uno(src: Path, dst: Path, glosario: Path, prompt: Path,
                 workdir: Path, chunk_words: int, model: str) -> tuple[str, dict]:
    cmd = [sys.executable, str(TOOL), str(src), "--out", str(dst),
           "--glosario", str(glosario), "--prompt", str(prompt),
           "--workdir", str(workdir), "--chunk-words", str(chunk_words)]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    en = src.read_text(encoding="utf-8")
    es = dst.read_text(encoding="utf-8") if dst.is_file() else ""
    fallos = verificar(en, es)
    info = metricas(en, es) if es else {}
    info["min"] = round((time.time() - t0) / 60, 1)
    if p.returncode != 0 and not es:
        fallos.append(f"el motor salió con código {p.returncode}")
    info["fallos"] = fallos
    info["estado"] = "ok" if not fallos else "fallo"
    info["huella_en"] = huella(en)
    return src.name, info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src_dir", type=Path, help="carpeta con los .md del idioma origen")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glosario", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/_forja_work"))
    ap.add_argument("--estado", type=Path, default=None,
                    help="JSON de estado (por defecto OUT/_estado_traduccion.json)")
    ap.add_argument("--desde", default="", help="procesar desde este prefijo de nombre")
    ap.add_argument("--hasta", default="", help="… hasta este prefijo (incluido)")
    ap.add_argument("--max", type=int, default=0, help="traducir como mucho N archivos y parar")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--chunk-words", type=int, default=700)
    ap.add_argument("--model", default="")
    ap.add_argument("--rehacer", action="store_true",
                    help="reintentar también los que quedaron en fallo")
    ap.add_argument("--informe", action="store_true", help="solo mostrar el estado y salir")
    a = ap.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)
    a.workdir.mkdir(parents=True, exist_ok=True)
    estado_p = a.estado or (a.out / "_estado_traduccion.json")
    estado = json.loads(estado_p.read_text()) if estado_p.is_file() else {}

    todos = sorted(a.src_dir.glob("*.md"))
    if a.desde:
        todos = [f for f in todos if f.name >= a.desde]
    if a.hasta:
        todos = [f for f in todos if f.name[:len(a.hasta)] <= a.hasta]

    # Un archivo hecho cuyo ORIGEN ha cambiado desde entonces vuelve a la cola,
    # sin tocar el .md traducido (el motor lo sobrescribe cuando le toque).
    rehacer_por_cambio = []
    for f in todos:
        e = estado.get(f.name, {})
        if e.get("estado") == "ok" and e.get("huella_en") and \
                e["huella_en"] != huella(f.read_text(encoding="utf-8")):
            rehacer_por_cambio.append(f.name)
            e["estado"] = "origen_cambiado"
    if rehacer_por_cambio:
        print(f"aviso: {len(rehacer_por_cambio)} archivo(s) con el ORIGEN cambiado "
              f"vuelven a la cola: {', '.join(n[:28] for n in rehacer_por_cambio[:5])}"
              + (" …" if len(rehacer_por_cambio) > 5 else ""))

    hechos = [f for f in todos if estado.get(f.name, {}).get("estado") == "ok"]
    fallidos = [f for f in todos if estado.get(f.name, {}).get("estado") == "fallo"]
    pend = [f for f in todos
            if estado.get(f.name, {}).get("estado") != "ok"
            and (a.rehacer or estado.get(f.name, {}).get("estado") != "fallo")]

    print(f"ámbito: {len(todos)} archivo(s) | hechos {len(hechos)} | "
          f"en fallo {len(fallidos)} | pendientes {len(pend)}")
    if a.informe:
        for f in todos:
            e = estado.get(f.name, {})
            if e.get("estado") == "ok":
                continue
            print(f"  {f.name}: {e.get('estado','(sin tocar)')} {e.get('fallos','')}")
        return 0

    if a.max:
        pend = pend[:a.max]
    if not pend:
        print("nada que hacer.")
        return 0
    print(f"a traducir ahora: {len(pend)}  (~{sum(len(f.read_text().split()) for f in pend):,} palabras)")

    def tarea(f):
        return traducir_uno(f, a.out / f.name, a.glosario, a.prompt,
                            a.workdir, a.chunk_words, a.model)

    hechos_ahora = fallos_ahora = 0
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as ex:
        for nombre, info in ex.map(tarea, pend):
            estado[nombre] = info
            # Se escribe tras CADA archivo: una sesión cortada pierde uno como mucho.
            estado_p.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
            if info["estado"] == "ok":
                hechos_ahora += 1
                print(f"  ✓ {nombre}  ratio {info['ratio']} · "
                      f"{info['definiciones']} notas · {info['min']} min", flush=True)
            else:
                fallos_ahora += 1
                print(f"  ✗ {nombre}  {info['fallos']}", flush=True)

    print(f"\nfase terminada: {hechos_ahora} bien, {fallos_ahora} en fallo. "
          f"Estado en {estado_p}")
    print("Relanza el mismo comando para continuar; los ✓ no se repiten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
