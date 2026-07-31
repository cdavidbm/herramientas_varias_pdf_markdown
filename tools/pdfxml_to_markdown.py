#!/usr/bin/env python3
"""pdfxml_to_markdown.py — bisturí para PDF digitales cuya capa de texto está
INCOMPLETA aunque el PDF sea nativo: se apoya en `pdftohtml -xml` (poppler) y
reconstruye lo que la extracción normal pierde EN SILENCIO.

Cuándo usarlo (en vez de `pdf_rich_to_markdown.py` o Docling)
--------------------------------------------------------------
Cuando `pdftotext`/`mutool` dan prosa legible PERO:

* **Las llamadas de nota desaparecen.** Los volados van en una fuente sin
  `ToUnicode`, así que se extraen como cadena VACÍA: en el texto solo queda un
  doble espacio. El aparato entero se pierde sin que ningún control lo note.
  Aquí se recuperan por GEOMETRÍA: cada glifo volado deja su posición y su
  ancho, los glifos contiguos se agrupan en una llamada y las llamadas se
  numeran en orden de lectura (`--first-note` fija el arranque). El número no
  se lee: se CUENTA — igual que en un escaneo (ver CLAUDE.md, §3c).
* **Los diacríticos se pierden o se parten.** Las tipografías académicas
  resuelven el punto suscrito con una fuente aparte (`…DotUnder…`): el carácter
  se extrae como la letra base (`h`, `t`, `d`, `s`) y el punto no existe en la
  capa de texto, de modo que `al-Qurṭubī` sale `al-Qurtubī` — una errata
  invisible en una transliteración. La familia de la fuente ES el dato: se le
  añade U+0323 y se normaliza a NFC.
* **Ligaduras mal mapeadas**: `Th` sale como `°`, y `ﬁ ﬂ ﬀ ﬅ` como glifos
  sueltos. Con `°e` → `The` el texto se lee bien pero está corrupto.

Además saca las CURSIVAS (por familia de fuente, que `pdftotext` no ve) y es
~200× más rápido que el bisturí de pdfminer en PDF con fuentes Type 3, donde
aquél tarda minutos POR PÁGINA.

Trampas conocidas (medidas)
---------------------------
* Los `<fontspec>` de `pdftohtml` son GLOBALES y se declaran donde la fuente
  aparece por primera vez: hay que acumularlos entre páginas o el grueso del
  texto queda sin estilo (aquí, 33 de 34 páginas).
* Un volado de dos cifras son DOS glifos vacíos contiguos: contarlos sin
  agrupar da casi el doble de notas de las que hay.
* El titulillo puede venir en una fuente de versalitas sin `ToUnicode` y
  extraerse como basura (`´²¶·¸¹º»¶´¸²`); se descarta por posición.
* **LÍMITE CONOCIDO — palabras con punto suscrito partidas.** `pdftohtml` emite
  los glifos de la fuente `…DotUnder…` FUERA del orden horizontal de su palabra,
  así que a veces queda un espacio dentro de la transliteración (`al-Ḥ akīm` por
  `al-Ḥakīm`). No se arregla por geometría —el token vecino ya trae su propio
  espacio—, y unir «letra con punto + espacio + minúscula» a ciegas es peligroso
  (`Ṣaliḥ ibn …` es legítimo). Se revisa a mano tras convertir; son pocos casos
  y se localizan así:
      grep -o '.\{20\}[ḥṭḍṣḤṬḌṢ] [a-zāīū].\{10\}' salida.md | sort | uniq -c

Uso
---
    python3 pdfxml_to_markdown.py libro.pdf --first 14 --last 49 --out intro.md
    python3 pdfxml_to_markdown.py libro.pdf --first 14 --last 49 --first-note 1
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET

DOT_BELOW = "̣"

LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}

# Proporción del cuerpo por debajo de la cual un glifo es un volado. 0.75 separa
# las dos poblaciones sin tocar las notas compuestas en cuerpo algo menor
# (misma constante que pdf_rich_to_markdown.py).
RAISED = 0.75

# Marca interna de salto de COLUMNA dentro de una línea (filas de tabla).
CELL = "\x00"


def run_pdftohtml(pdf: Path, first: int | None, last: int | None) -> str:
    cmd = ["pdftohtml", "-xml", "-stdout"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd.append(str(pdf))
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"pdftohtml falló: {r.stderr.decode('utf-8', 'replace')[:400]}")
    return r.stdout.decode("utf-8", "replace")


def parse_pages(xml: str) -> list[dict]:
    """[{num, width, height, toks:[{top,left,w,h,size,fam,txt,bold,ital}]}]"""
    root = ET.fromstring(xml)
    specs: dict[str, tuple[float, str]] = {}   # acumulativo — ver trampa arriba
    pages = []
    for pg in root.iter("page"):
        for fs in pg.iter("fontspec"):
            specs[fs.get("id")] = (float(fs.get("size") or 0), fs.get("family") or "")
        toks = []
        for t in pg.iter("text"):
            size, fam = specs.get(t.get("font") or "", (0.0, ""))
            tags = {c.tag for c in t.iter() if c is not t}
            low = fam.lower()
            toks.append(dict(
                top=int(t.get("top") or 0), left=int(t.get("left") or 0),
                w=int(t.get("width") or 0), h=int(t.get("height") or 0),
                size=size, fam=fam, txt="".join(t.itertext()),
                bold=("b" in tags) or "bold" in low or "semibold" in low,
                ital=("i" in tags) or "italic" in low or re.search(r"-it|ita", low) is not None,
            ))
        pages.append(dict(num=int(pg.get("number") or 0), toks=toks,
                          width=float(pg.get("width") or 0),
                          height=float(pg.get("height") or 0)))
    return pages


def body_size(pages: list[dict]) -> float:
    c: collections.Counter = collections.Counter()
    for p in pages:
        for t in p["toks"]:
            if t["txt"].strip():
                c[t["size"]] += len(t["txt"])
    return c.most_common(1)[0][0] if c else 0.0


CHARMAP: dict[str, str] = {}


def clean_text(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    for k, v in CHARMAP.items():
        s = s.replace(k, v)
    # «°» es la ligadura Th mal mapeada: solo al abrir palabra y ante minúscula,
    # para no tocar los grados (27°, 15° 30').
    s = re.sub(r"(?<![0-9])°(?=[a-z])", "Th", s)
    return s


def apply_dot_under(txt: str) -> str:
    """La FAMILIA de la fuente dice que estas letras llevan punto suscrito."""
    return unicodedata.normalize("NFC", "".join(ch + DOT_BELOW if ch.isalpha() else ch
                                                for ch in txt))


def group_lines(toks: list[dict]) -> list[list[dict]]:
    """Agrupa tokens en líneas por su coordenada vertical."""
    lines: list[list[dict]] = []
    for t in sorted(toks, key=lambda t: (t["top"], t["left"])):
        if lines and abs(t["top"] - lines[-1][0]["top"]) <= max(3, t["h"] * 0.4):
            lines[-1].append(t)
        else:
            lines.append([t])
    for ln in lines:
        ln.sort(key=lambda t: t["left"])
    return lines


def is_running_head(line: list[dict], first_of_page: bool) -> bool:
    """Titulillo/folio: PRIMERA línea de la página, corta y que no es prosa.

    El texto suele ser ilegible (versalitas sin `ToUnicode`: `´²¶·¸¹º»¶´¸²`),
    así que no se puede casar por contenido. Se exige que la línea sea la
    primera, breve, y que NO parezca texto latino: solo dígitos (el folio) o
    mayoría de caracteres fuera del repertorio normal. La guarda importa: en un
    libro cualquiera hay encabezados legítimos que abren página, y descartar
    «toda primera línea corta» se come contenido real.
    """
    if not first_of_page or not line:
        return False
    txt = "".join(t["txt"] for t in line).strip()
    if not txt:
        return True
    if len(txt) > 70:
        return False
    core = re.sub(r"[\s\d]", "", txt)
    if not core:
        return True                       # solo el folio
    normal = sum(1 for ch in core if ch.isascii() and (ch.isalpha() or ch in ".,;:'\"-–—()"))
    return normal / len(core) < 0.7       # mayoría de basura => titulillo


def _is_pua(s: str) -> bool:
    """Glifo sin ToUnicode: cae en el Área de Uso Privado."""
    return s != "" and all(0xE000 <= ord(c) <= 0xF8FF for c in s)


def line_baseline(line: list[dict], body: float) -> int:
    """Línea base del renglón = borde inferior de los tokens en cuerpo normal."""
    bases = [t["top"] + t["h"] for t in line
             if t["txt"].strip() and (not body or t["size"] > body * RAISED)]
    return max(bases) if bases else max(t["top"] + t["h"] for t in line)


def render_line(line: list[dict], body: float, counter: dict,
                cell_gap: float = 1e9) -> str:
    """Línea -> markdown, con cursivas, punto suscrito y llamadas de nota."""
    out: list[str] = []
    open_i = False
    prev_raised_right: int | None = None
    prev_right: int | None = None
    base = line_baseline(line, body)
    for t in line:
        txt = t["txt"].replace("\xa0", " ")
        # `pdftohtml` NO emite un token de espacio entre cada par de palabras:
        # el espacio se deduce del HUECO. Sin esto, al cerrar una cursiva las
        # palabras se pegan («*Picatrix*stand»).
        if prev_right is not None and txt and not txt[:1].isspace():
            gap = t["left"] - prev_right
            if gap >= cell_gap:
                out.append(CELL)          # salto de COLUMNA, no de palabra
            elif gap >= 2 and out and not out[-1].endswith((" ", "*", CELL)):
                out.append(" ")
        prev_right = t["left"] + t["w"]
        # El tamaño NO basta para reconocer un volado: los DÍGITOS
        # ELZEVIRIANOS del cuerpo también vienen en caja menor y sin
        # ToUnicode (medido: 260 glifos así frente a 77 volados reales). La
        # señal robusta es la LÍNEA BASE ALZADA — el glifo termina bastante
        # por encima de la base de su renglón —, igual que en un escaneo.
        raised = (bool(body) and t["size"] <= body * RAISED
                  and t["top"] + t["h"] <= base - body * 0.20)
        # Un volado sin ToUnicode se extrae como cadena vacía o como PUA; un
        # espacio (`\xa0`) NO es un volado aunque venga en cuerpo menor.
        if raised and (txt == "" or _is_pua(txt)):
            # Glifo volado sin ToUnicode = una CIFRA de una llamada. Los glifos
            # contiguos son la misma llamada (una nota de dos dígitos son dos).
            digits = clean_text(txt) if _is_pua(txt) else ""
            if prev_raised_right is not None and t["left"] - prev_raised_right <= max(4, t["w"]):
                if digits.isdigit() and counter["read"]:
                    counter["read"][-1] += digits      # 2ª cifra de la misma llamada
                prev_raised_right = t["left"] + t["w"]
                continue
            if open_i:
                out.append("*"); open_i = False
            counter["n"] += 1
            # La etiqueta es el número CONTADO, no el leído: el conteo es la
            # señal completa (ningún volado se pierde), mientras que alguna
            # cifra suelta puede no llegar a mapearse. Lo leído se guarda para
            # COTEJARLO — dos señales independientes sobre el mismo dato.
            counter["read"].append(digits)
            out.append(f"[^{counter['n']}]")
            prev_raised_right = t["left"] + t["w"]
            continue
        prev_raised_right = None
        if "DotUnder" in t["fam"]:
            txt = apply_dot_under(txt)
        want_i = t["ital"] and txt.strip()
        if want_i and not open_i:
            out.append("*"); open_i = True
        elif open_i and not want_i and txt.strip():
            out.append("*"); open_i = False
        out.append(txt)
    if open_i:
        out.append("*")
    s = "".join(out)
    # Las ligaduras solo se ven una vez unidos los tokens: «The» viene partido
    # en el glifo «°» (Th) y una «e» aparte.
    s = clean_text(s)
    s = re.sub(r"\*(\s+)\*", r"\1", s)          # cursivas contiguas partidas
    s = re.sub(r"[ \t]+", " ", s)
    return fix_emphasis(s.strip())



def fix_emphasis(s: str) -> str:
    """Saca de la cursiva el espacio que la precede al cerrar: «*Picatrix *» .

    El token del espacio viene en la MISMA fuente cursiva, así que queda dentro
    del énfasis; pandoc entonces no reconoce el cierre y **imprime los asteriscos
    literales** (se ve en el PDF, no en el markdown). Hay que distinguir el
    asterisco que ABRE del que CIERRA —un `*` tras espacio puede ser cualquiera
    de los dos—, así que se recorre la línea llevando el estado, y las negritas
    `**` se dejan intactas (dos asteriscos adyacentes: tocarlos las destruye).
    """
    out: list[str] = []
    open_em = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "*":
            if i + 1 < len(s) and s[i + 1] == "*":      # negrita: se copia tal cual
                out.append("**"); i += 2; continue
            if open_em:
                # cierre: si venimos de espacios, el cierre va ANTES de ellos
                j = len(out)
                while j > 0 and out[j - 1] == " ":
                    j -= 1
                if j < len(out):
                    out.insert(j, "*")
                else:
                    out.append("*")
                open_em = False
            else:
                out.append("*"); open_em = True
            i += 1
            continue
        out.append(ch); i += 1
    if open_em:
        # Énfasis que la línea no llega a cerrar: pandoc imprimiría el asterisco
        # literal en el PDF (invisible en el markdown). Mejor perder la cursiva
        # que ensuciar la página.
        for k in range(len(out) - 1, -1, -1):
            if out[k] == "*":
                del out[k]
                break
    return "".join(out)


def page_markdown(page: dict, body: float, counter: dict, keep_heads: bool,
                  cell_gap: float = 1e9) -> list[str]:
    lines = group_lines(page["toks"])
    out: list[tuple[str, list[dict]]] = []
    for ln in lines:
        if not keep_heads and is_running_head(ln, ln is lines[0]):
            continue
        txt = render_line(ln, body, counter, cell_gap)
        if txt:
            out.append((txt, ln))
    return out


def assemble(all_lines: list[tuple[str, list[dict]]], body: float) -> str:
    """Cose las líneas en párrafos por la SANGRÍA (relativa al margen)."""
    if not all_lines:
        return ""
    margins = [ln[0]["left"] for _, ln in all_lines]
    margin = sorted(margins)[len(margins) // 2]
    paras: list[list[str]] = []
    for txt, ln in all_lines:
        first = ln[0]
        # Encabezado: línea breve MAYORITARIAMENTE en negrita. No vale exigirla
        # entera: los títulos académicos llevan el término técnico en CURSIVA
        # («A Prehistory of the Latin *Picatrix*»), y con `all()` se pierden.
        words = [t for t in ln if t["txt"].strip()]
        nbold = sum(1 for t in words if t["bold"])
        heading = bool(words) and nbold >= max(1, int(len(words) * 0.6)) and len(txt) < 90
        indented = first["left"] > margin + max(6, body * 0.4)
        if heading:
            paras.append([f"## {txt}"])
            paras.append([])
            continue
        if CELL in txt:
            paras.append([txt])          # fila de tabla: no se cose con la prosa
            paras.append([])
            continue
        if not paras or paras[-1] == [] or indented:
            paras.append([txt])
        else:
            prev = paras[-1][-1]
            if prev.endswith("-"):
                paras[-1][-1] = prev[:-1] + txt      # palabra partida por renglón
            else:
                paras[-1][-1] = prev + " " + txt
    chunks = [" ".join(p).strip() for p in paras if p and " ".join(p).strip()]
    return "\n\n".join(chunks) + "\n"


def tabulate(md: str) -> str:
    """Filas contiguas con salto de columna -> tabla markdown."""
    out: list[str] = []
    block: list[list[str]] = []

    def flush():
        if not block:
            return
        width = max(len(r) for r in block)
        rows = [r + [""] * (width - len(r)) for r in block]
        if width > 1 and len(rows) > 1:
            out.append("| " + " | ".join(rows[0]) + " |")
            out.append("|" + "|".join([" --- "] * width) + "|")
            for r in rows[1:]:
                out.append("| " + " | ".join(r) + " |")
        else:
            out.extend(" ".join(r).strip() for r in rows)
        out.append("")
        block.clear()

    for para in md.split("\n\n"):
        if CELL in para:
            block.append([c.strip() for c in para.split(CELL)])
        else:
            flush()
            out.append(para)
    flush()
    return "\n\n".join(x for x in "\n".join(out).split("\n\n"))


def extract_notes(paras: list[str], first: int, last: int) -> tuple[list[str], list[int]]:
    """Aparato de FINAL DE LIBRO -> definiciones `[^N]:`.

    Las definiciones abren con «N. » en cuerpo normal (los volados que no se
    leen son los del CUERPO, no los del aparato). Para no confundir una cifra
    del texto de una nota con el arranque de la siguiente, solo se acepta el
    número CONSECUTIVO esperado — la misma cadena que usa `footnote_chain.py`.
    """
    defs: dict[int, list[str]] = {}
    want = first
    cur: int | None = None
    for p in paras:
        m = re.match(rf"^{want}\.\s+(.*)$", p, re.S) if want <= last else None
        if m:
            cur = want
            defs[cur] = [m.group(1).strip()]
            want += 1
        elif cur is not None:
            # Pasado el último número, la sección siguiente del aparato reinicia
            # en «1.»: si se sigue acumulando, sus notas se cuelan dentro de la
            # última definición de ESTA sección.
            if want > last and re.match(r"^\d+\.\s", p):
                break
            defs[cur].append(p.strip())
    out = [f"[^{n}]: " + " ".join(defs[n]).strip() for n in sorted(defs)]
    missing = [n for n in range(first, last + 1) if n not in defs]
    return out, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--first", type=int, help="primera página (1-based)")
    ap.add_argument("--last", type=int, help="última página (1-based)")
    ap.add_argument("--out", help="markdown de salida (def. stdout)")
    ap.add_argument("--first-note", type=int, default=1,
                    help="número de la primera llamada reconstruida (def. 1)")
    ap.add_argument("--keep-running-heads", action="store_true",
                    help="no descartar titulillos/folios")
    ap.add_argument("--body-size", type=float, help="cuerpo en pt (def: se detecta)")
    ap.add_argument("--tables", action="store_true",
                    help="reconstruir como TABLA las filas con salto de columna "
                         "(si no, se aplanan a texto corrido)")
    ap.add_argument("--charmap", metavar="A=B,C=D",
                    help="glifos mal mapeados que hay que sustituir, verificados "
                         "contra la imagen (p. ej. «¾=Z» cuando las versalitas "
                         "pierden una letra en el ToUnicode)")
    ap.add_argument("--notes-pages", metavar="A-B",
                    help="páginas del aparato de FINAL DE LIBRO de esta sección; "
                         "sus definiciones se añaden como [^N]: al final")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise SystemExit(f"no existe: {pdf}")
    if args.charmap:
        for pair in args.charmap.split(","):
            k, _, v = pair.partition("=")
            if k.upper().startswith("U+"):          # U+F63A=2
                k = chr(int(k[2:], 16))
            if k:
                CHARMAP[k] = v
    pages = parse_pages(run_pdftohtml(pdf, args.first, args.last))
    body = args.body_size or body_size(pages)
    counter = {"n": args.first_note - 1, "read": []}
    all_lines: list[tuple[str, list[dict]]] = []
    for p in pages:
        cg = p["width"] * 0.06 if args.tables else 1e9
        all_lines += page_markdown(p, body, counter, args.keep_running_heads, cg)
    md = assemble(all_lines, body)
    md = tabulate(md) if args.tables else md.replace(CELL, " ")

    notes = counter["n"] - args.first_note + 1
    print(f"{len(pages)} páginas, cuerpo {body}pt, {notes} llamadas de nota "
          f"({args.first_note}–{counter['n']})", file=sys.stderr)
    # Cotejo: el número IMPRESO (si el charmap lo lee) contra el CONTADO. Una
    # discrepancia significa que se coló un falso volado o que falta uno.
    read = counter["read"]
    if any(read):
        bad = [(i + args.first_note, r) for i, r in enumerate(read)
               if r and int(r) != i + args.first_note]
        print(f"cotejo llamadas: {sum(1 for r in read if r)}/{len(read)} legibles; "
              + ("sin desfases" if not bad else f"DESFASES {bad[:8]}"), file=sys.stderr)

    if args.notes_pages:
        a, _, b = args.notes_pages.partition("-")
        npages = parse_pages(run_pdftohtml(pdf, int(a), int(b or a)))
        nbody = body_size(npages)
        nlines: list[tuple[str, list[dict]]] = []
        ncounter = {"n": 0, "read": []}
        for p in npages:
            nlines += page_markdown(p, nbody, ncounter, False)
        paras = [x.replace(CELL, " ") for x in assemble(nlines, nbody).split("\n\n") if x.strip()]
        defs, missing = extract_notes(paras, args.first_note, counter["n"])
        md = md.rstrip("\n") + "\n\n" + "\n".join(defs) + "\n"
        print(f"aparato: {len(defs)} definiciones"
              + (f"; FALTAN {missing}" if missing else "; sin huecos"), file=sys.stderr)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"-> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
