#!/usr/bin/env python3
"""apa_video_keys.py — genera la tabla de CLAVES DE CITA APA 7 de un corpus de vídeos transcritos (clases, conferencias, coloquios).

Un libro que cita un curso en vídeo cita decenas de clases del MISMO autor en el MISMO año:
APA 7 las distingue con una letra tras el año (Masdeu, 2021a, 2021b … 2021az, 2022ba…).
Asignarlas a mano es donde se cuelan los errores: en *El cielo de los Nombres* dos
capítulos citaban clases con la clave de OTRA clase (2021ad por 2021t; 2022bg por 2022bn)
hasta que la tabla se generó de forma determinista desde los metadatos. Esta herramienta
es esa tabla: una fila por vídeo con su clave, la forma de cita en el texto y la entrada
APA completa con URL, para pegar tal cual en las referencias.

Lee el frontmatter YAML de cada `.md` (o `.txt` con frontmatter) de una carpeta. Acepta
claves en español o en inglés:
    título|titulo|title · fecha|date (AAAA-MM-DD) · profesor|autor|author ·
    fuente|canal|channel («YouTube — Canal» → «Canal») · video_id|url · clase|numero|number

Letras: dentro de cada (autor, año) se asignan a, b … z, aa, ab … en el orden que pide
APA 7 para obras sin fecha distintiva, el ALFABÉTICO DEL TÍTULO (`--orden titulo`, por
defecto), o por fecha de publicación (`--orden fecha`). Elegido un criterio, NO lo cambies
a mitad de libro: todas las citas dependen de él.

Uso:
    python3 apa_video_keys.py carpeta_transcripciones/ > CLAVES.md
    python3 apa_video_keys.py carpeta/ --autor "Masdeu, A." --canal "Logos Astrológico"
    python3 apa_video_keys.py carpeta/ --orden fecha --json

Trampas:
- El autor «Albert Masdeu» se invierte a «Masdeu, A.»; con apellidos compuestos o
  partículas (al-, de la…) pásalo explícito con --autor.
- Un vídeo sin fecha en el frontmatter queda fuera y se avisa por stderr: no se le inventa
  una fecha (la clave cambiaría las letras de todos los demás del año).
- Los títulos se toman del frontmatter, no de YouTube: si difieren, manda el que se cite.
"""
from __future__ import annotations
import argparse, json, re, sys, unicodedata
from pathlib import Path

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).split("\n"):
        mm = re.match(r"^([\wáéíóúñ_]+):\s*(.*)$", line)
        if mm and mm.group(2).strip():
            out[mm.group(1).lower()] = mm.group(2).strip().strip('"').strip("'")
    return out


def pick(d: dict, *keys: str) -> str:
    for k in keys:
        if d.get(k):
            return d[k]
    return ""


def invert_name(name: str) -> str:
    """«Albert Masdeu» → «Masdeu, A.»; si ya viene invertido («Masdeu, A.»), igual."""
    name = name.strip()
    if "," in name or not name:
        return name
    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    initials = " ".join(p[0] + "." for p in parts[:-1])
    return f"{parts[-1]}, {initials}"


def letters(i: int) -> str:
    """0→a … 25→z, 26→aa, 27→ab … (como APA: sin límite de 26)."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(97 + r) + s
    return s


def sort_title(t: str) -> str:
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = re.sub(r"^(el|la|los|las|un|una|the|a|an)\s+", "", t)
    return re.sub(r"[^\w ]", "", t)


def spanish_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]}"


def build(folder: Path, autor: str | None, canal: str | None, orden: str) -> list[dict]:
    rows = []
    for f in sorted(list(folder.glob("*.md")) + list(folder.glob("*.txt"))):
        fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        fecha = pick(fm, "fecha", "date")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
            print(f"aviso: {f.name} sin fecha AAAA-MM-DD; se omite", file=sys.stderr)
            continue
        vid = pick(fm, "video_id", "url")
        url = vid if vid.startswith("http") else (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        fuente = pick(fm, "canal", "channel", "fuente")
        rows.append({
            "archivo": f.name,
            "numero": pick(fm, "clase", "numero", "number"),
            "titulo": pick(fm, "título", "titulo", "title") or f.stem,
            "fecha": fecha,
            "autor": autor or invert_name(pick(fm, "profesor", "autor", "author")),
            "canal": canal or fuente.split("—")[-1].strip(),
            "url": url,
        })
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["autor"], r["fecha"][:4]), []).append(r)
    for (au, y), g in groups.items():
        key = (lambda r: (sort_title(r["titulo"]), r["fecha"])) if orden == "titulo" \
            else (lambda r: (r["fecha"], sort_title(r["titulo"])))
        g.sort(key=key)
        solo = len(g) == 1
        for i, r in enumerate(g):
            r["clave"] = y + ("" if solo else letters(i))
    for r in rows:
        surname = r["autor"].split(",")[0]
        r["cita"] = f"({surname}, {r['clave']})"
        r["referencia"] = (f"{r['autor']} ({r['clave']}, {spanish_date(r['fecha'])}). "
                           f"*{r['titulo']}* [Video]. {r['canal']}. {r['url']}").rstrip(". ") + ""
    rows.sort(key=lambda r: (r["fecha"], r["numero"].zfill(4) if r["numero"].isdigit() else r["numero"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--autor", help="autor en forma APA («Apellido, I.»); por defecto, del frontmatter")
    ap.add_argument("--canal", help="canal o editor; por defecto, del frontmatter")
    ap.add_argument("--orden", choices=["titulo", "fecha"], default="titulo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = build(a.carpeta, a.autor, a.canal, a.orden)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"# Claves de cita APA 7 — {a.carpeta.name}\n")
    print(f"> Generado por `apa_video_keys.py` (orden de letras: {a.orden}). En el texto se cita la "
          "clave y, como localizador, el número de clase o el epígrafe: (Autor, 2021h, clase 11).\n")
    print("| N.º | Cita en el texto | Referencia APA 7 |\n|---:|---|---|")
    for r in rows:
        print(f"| {r['numero']} | {r['cita']} | {r['referencia']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
