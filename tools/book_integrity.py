#!/usr/bin/env python3
"""book_integrity.py — control de INTEGRIDAD de un libro escrito en markdown (varios .md).

Nace de escribir *El cielo de los Nombres* (86 000 palabras, 19 archivos, cuatro rondas
de edición con agentes en paralelo). Tras cada ronda había que comprobar a mano las mismas
cuatro cosas, y cada vez apareció algún fallo que ninguna lectura había visto:

1. **Notas al pie**: toda llamada `[^x]` con su definición y viceversa, sin duplicados.
   Un recorte de «repeticiones» borraba el párrafo con la llamada y dejaba la nota huérfana.
2. **Remisiones internas**: «véase el capítulo 4, §3.3.3» debe apuntar a una sección que
   EXISTE. Se resuelven contra los encabezados numerados (`## 3.`, `### 3.3`, `#### 3.3.3`)
   del archivo cuyo H1 es «Capítulo 4 …». También remisiones a divisiones sin número con
   secciones en romanos («véase el Excurso, §XIV» → el archivo cuyo H1 empieza por «Excurso»).
3. **Marcas de trabajo olvidadas**: «[pendiente», «verificar]», «TODO», rutas de trabajo
   (`01_plan/`, `scratchpad`…). Un agente las dejó en notas al pie del texto final.
4. **Cobertura de referencias** (APA autor-fecha): toda cita «(Autor, 2021a…)» del cuerpo
   tiene entrada en la lista de referencias del capítulo, y ninguna entrada queda sin citar.
   Al recortar texto desaparecían citas y sus entradas quedaban huérfanas; al restaurarlas
   se borró por error una entrada que SÍ se citaba en la cabecera de una tabla (medido): por
   eso el cotejo lo hace el script, no la vista.

Uso:
    python3 book_integrity.py carpeta_del_libro/            # todos los .md, en orden
    python3 book_integrity.py cap01.md cap02.md …
    python3 book_integrity.py libro/ --refs-heading "Referencias del capítulo" \\
            --global-refs libro/16_Apendice_F_Referencias.md --json

Sale con código 1 si hay errores DUROS (notas rotas, remisiones rotas, citas sin entrada).
Las entradas nunca citadas y las marcas de trabajo son AVISOS (código 0), porque a veces
son deliberadas (bibliografía de fuentes consultadas, p. ej.).

Trampas conocidas:
- La cita narrativa «Coullaut Cordero (2009)» y la de tabla «Masdeu (2021at, 2022k)» son
  citas válidas: el extractor reconoce autor + paréntesis con año, no solo «(Autor, año)».
- Los años del mismo autor separados por coma o punto y coma («2022w, clase 122; 2022ch»)
  heredan el autor anterior.
- Un archivo sin sección de referencias (índice, apéndice de referencias) no se coteja.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

NOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:", re.M)
NOTE_CALL = re.compile(r"\[\^([^\]]+)\](?!:)")
H1 = re.compile(r"^# (.+)$", re.M)
NUM_HEAD = re.compile(r"^#{2,6} (\d+(?:\.\d+)*)\.?\s", re.M)
ROMAN_HEAD = re.compile(r"^#{2,6} ([IVXLC]+)\.\s", re.M)
CHAP_H1 = re.compile(r"^(?:Cap[íi]tulo|Chapter)\s+(\d+)\b", re.I)
# «capítulo 4, §3.3.3» · «capítulos 2, §4» · «capítulo 12 (§5.1)» · «capítulo 3, nota 4» (no se resuelve)
REMIS_CHAP = re.compile(r"cap[íi]tulos?\s+(\d+)\s*(?:,\s*|\(\s*)§§?\s*(\d+(?:\.\d+)*)", re.I)
REMIS_NAMED = re.compile(r"\b([A-ZÁÉÍÓÚ][\wáéíóú]+),\s*§§?\s*([IVXLC]+)\b")
DEFAULT_MARKERS = [r"\[pendiente", r"verificar\]", r"\[verificar", r"por completar",
                   r"\bTODO\b", r"\bXXX\b", r"01_plan/", r"00_investigacion", r"scratchpad"]
YEAR = r"(?:(?:ca\.\s)?\d{3,4}/\d{4}[a-z]{0,2}|\d{4}[a-z]{0,2}|s\.\s?f\.)"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def split_body_refs(text: str, heading: str) -> tuple[str, str | None]:
    m = re.search(r"^#{1,6}\s+" + re.escape(heading) + r"\s*$", text, re.M)
    if not m:
        return text, None
    rest = text[m.end():]
    nxt = re.search(r"^#{1,2}\s", rest, re.M)
    return text[:m.start()], rest[:nxt.start()] if nxt else rest


def norm_year(y: str) -> str:
    """«ca. 1291/2023» y «1224/1996» (obra original/edición) → el año de la EDICIÓN,
    que es el de la entrada de referencias."""
    y = re.sub(r"\s", "", y)
    return y.split("/")[-1] if "/" in y else y.replace("ca.", "")


def surname_key(s: str) -> str:
    s = re.sub(r"^(?:al-|el-|Al-)", "", s.strip())
    return s.split(",")[0].split()[0].lower() if s else ""


def ref_entries(block: str) -> set[tuple[str, str]]:
    """(apellido del primer autor, año+letra) de cada entrada APA del bloque."""
    out = set()
    for e in re.split(r"\n\s*\n", block):
        e = e.strip()
        if not e or e.startswith((">", "|", "#")):
            continue
        m = re.match(r"^(.+?)\.?\s\((" + YEAR + r")", e)
        if m:
            out.add((surname_key(m.group(1)), norm_year(m.group(2))))
    return out


def body_citations(body: str) -> set[tuple[str, str]]:
    out = set()
    # (Autor, 2021a…; 2022k…)  ·  (Autor y Otro, 2023b)  ·  (Autor et al., 2011)
    for m in re.finditer(r"\(([^()]*\d{4}[^()]*)\)", body):
        inner = m.group(1)
        author = None
        for part in re.split(r";", inner):
            part = part.strip()
            am = re.match(r"^(?:véase\s+|cf\.\s+|citado en\s+)?([A-ZÁÉÍÓÚa-z][^,()]*?),\s*(" + YEAR + r")", part)
            if am and not re.match(r"^\d", am.group(1)):
                author = surname_key(re.split(r"\s+y\s+|\s+et al\.", am.group(1))[0])
                out.add((author, norm_year(am.group(2))))
                for y in re.findall(r",\s*(\d{4}[a-z]{1,2})\b", part[am.end():]):
                    out.add((author, y))
            elif author:
                ym = re.match(r"^(\d{4}[a-z]{0,2})\b", part)
                if ym:
                    out.add((author, ym.group(1)))
    # narrativa: Autor (2009) · Autor Cordero (2009) · Masdeu (2021at, 2022k)
    # «Raúl y Masdeu (2023e)»: cuenta el PRIMER autor, no el que precede al paréntesis
    for m in re.finditer(r"\b([A-ZÁÉÍÓÚ][\w-]+(?:\s(?:al-)?[ʿʾ]?[A-ZÁÉÍÓÚ][\w-]*)?)((?:,\s[A-ZÁÉÍÓÚ][\wáéíóúñ-]+)*\s(?:y|e)\s[A-ZÁÉÍÓÚ][\wáéíóúñ-]+)?\s\(((?:ca\.\s)?(?:\d{3,4}/)?\d{4}[a-z]{0,2}(?:,\s*\d{4}[a-z]{0,2})*)[,)]", body):
        # finditer avanza de izquierda a derecha: en «Raúl y Masdeu (2023e)» casa ANTES en
        # «Raúl». Con dos palabras en mayúscula («Según Masdeu», «Coullaut Cordero») no se
        # sabe cuál es el apellido: se registran ambas; la sobrante no tiene entrada y no
        # genera error (solo el cotejo «cita sin entrada» usa autores con entradas).
        toks = [surname_key(t) for t in m.group(1).split()]
        m_years = m.group(3)
        m_years = re.sub(r"(?:ca\.\s)?\d{3,4}/", "", m_years)   # original/edición → edición
        for y in re.findall(r"\d{4}[a-z]{0,2}", m_years):
            for a in toks:
                out.add((a, y))
    return out


def check(files: list[Path], refs_heading: str, markers: list[str],
          global_refs: Path | None) -> dict:
    texts = {f: read(f) for f in files}
    chap_secs: dict[int, set[str]] = {}
    named_secs: dict[str, set[str]] = {}
    for f, t in texts.items():
        h = H1.search(t)
        title = h.group(1) if h else ""
        cm = CHAP_H1.match(title)
        if cm:
            chap_secs[int(cm.group(1))] = set(NUM_HEAD.findall(t))
        romans = set(ROMAN_HEAD.findall(t))
        if romans and title:
            named_secs[title.split()[0].strip(".·:").lower()] = romans
    report = {"errores": [], "avisos": []}
    all_cited: set[tuple[str, str]] = set()
    for f, t in texts.items():
        name = f.name
        d = NOTE_DEF.findall(t); c = set(NOTE_CALL.findall(t))
        for x in sorted(set(d) - c):
            report["errores"].append(f"{name}: nota [^{x}] sin llamada")
        for x in sorted(c - set(d)):
            report["errores"].append(f"{name}: llamada [^{x}] sin nota")
        dup = {x for x in d if d.count(x) > 1}
        for x in sorted(dup):
            report["errores"].append(f"{name}: nota [^{x}] definida dos veces")
        for m in REMIS_CHAP.finditer(t):
            n, sec = int(m.group(1)), m.group(2).rstrip(".")
            if n in chap_secs and sec not in chap_secs[n]:
                report["errores"].append(f"{name}: remisión rota «{m.group(0)}» (el cap. {n} no tiene §{sec})")
        for m in REMIS_NAMED.finditer(t):
            key = m.group(1).lower()
            if key in named_secs and m.group(2) not in named_secs[key]:
                report["errores"].append(f"{name}: remisión rota «{m.group(0)}»")
        for pat in markers:
            for m in re.finditer(pat, t):
                ctx = t[max(0, m.start() - 40):m.end() + 30].replace("\n", " ")
                report["avisos"].append(f"{name}: marca de trabajo «{m.group(0)}» … {ctx}")
        body, refs = split_body_refs(t, refs_heading)
        cites = body_citations(body)
        all_cited |= cites
        if refs is not None:
            entries = ref_entries(refs)
            ent_auth = {a for a, _ in entries}
            for a, y in sorted(cites):
                if a in ent_auth and (a, y) not in entries:
                    report["errores"].append(f"{name}: cita ({a}, {y}) sin entrada en las referencias")
            for a, y in sorted(entries - cites):
                report["avisos"].append(f"{name}: entrada ({a}, {y}) nunca citada en el capítulo")
    if global_refs:
        g = ref_entries(read(global_refs))
        g_auth = {a for a, _ in g}
        for a, y in sorted(all_cited):
            if a in g_auth and (a, y) not in g:
                report["errores"].append(f"{global_refs.name}: falta la entrada ({a}, {y}) citada en el libro")
        for a, y in sorted(g - all_cited):
            report["avisos"].append(f"{global_refs.name}: entrada ({a}, {y}) no citada en ningún archivo")
    report["palabras"] = {f.name: len(t.split()) for f, t in texts.items()}
    report["palabras_total"] = sum(report["palabras"].values())
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="carpeta del libro o archivos .md")
    ap.add_argument("--refs-heading", default="Referencias del capítulo")
    ap.add_argument("--global-refs", type=Path, help="archivo de referencias general (apéndice)")
    ap.add_argument("--marker", action="append", help="regex extra de marca de trabajo (repetible)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files: list[Path] = []
    for p in map(Path, a.paths):
        files += sorted(p.glob("*.md")) if p.is_dir() else [p]
    rep = check(files, a.refs_heading, DEFAULT_MARKERS + (a.marker or []), a.global_refs)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for e in rep["errores"]:
            print("ERROR  " + e)
        for w in rep["avisos"]:
            print("aviso  " + w)
        print(f"{len(files)} archivos · {rep['palabras_total']} palabras · "
              f"{len(rep['errores'])} errores · {len(rep['avisos'])} avisos")
    return 1 if rep["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
