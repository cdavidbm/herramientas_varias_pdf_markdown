#!/usr/bin/env python3
"""md_to_pdf.py — Convierte markdown de estudio (suite La Forja) a un **PDF bello**,
con la misma tipografía clásica que las ediciones LaTeX de Valens/Doroteo: clase
`memoir`, estilo de capítulo *bringhurst*, `fontspec`+LuaLaTeX (Unicode, ordinales,
macrones, griego) y los **glifos astrológicos** (☉ ♄ ♈ △…) renderizados con la fuente
`starfont` vía `newunicodechar`.

Cada archivo `.md` se trata como un **capítulo** (su `#` de nivel 1 → `\\chapter`).
Pasa varios en el orden deseado para armar un libro; `##`, `###`, notas `[^N]`, citas
en verso, tablas, negritas e imágenes se preservan (vía pandoc).

Uso:
    python3 md_to_pdf.py salida.pdf cap01.md cap02.md ... \\
            [--title "Título"] [--author "Autor"] [--lang spanish] [--toc] [--keep-tex]

Requiere: pandoc, TeX Live con memoir, fontspec, starfont, wasysym, babel-<lang>,
newunicodechar; motor **lualatex**. Ver README/CLAUDE.md de La Forja.
"""
import argparse, pathlib, subprocess, sys, tempfile, shutil, re

# Glifos Unicode astrológicos -> comando starfont (inverso del SYM de latex_to_markdown)
UNI2CMD = {
    "☉":"Sun","☽":"Moon","☿":"Mercury","♀":"Venus","⊕":"Earth","♂":"Mars",
    "♃":"Jupiter","♄":"Saturn","♅":"Uranus","♆":"Neptune","♇":"Pluto",
    "♈":"Aries","♉":"Taurus","♊":"Gemini","♋":"Cancer","♌":"Leo","♍":"Virgo",
    "♎":"Libra","♏":"Scorpio","♐":"Sagittarius","♑":"Capricorn","♒":"Aquarius","♓":"Pisces",
    "☌":"Conjunction","☍":"Opposition","△":"Trine","□":"Square","⚹":"Sextile",
    "☊":"Ascnode","☋":"Descnode","℞":"Retrograde","⊗":"Fortune",
}
# starfont NO trae los nodos: la Cabeza (☊ U+260A) y la Cola (☋ U+260B) del Dragón se
# toman de wasysym (\ascnode/\descnode), que sí está cargado. (Sobrescribe por codepoint.)
UNI2CMD["☊"] = "ascnode"
UNI2CMD["☋"] = "descnode"

def latex_escape(s):
    """Escapa los metacaracteres de LaTeX en texto plano (título/autor de portada).
    Sin esto, un `&`, `%`, `_`, `#`, `$`, `~`, `^`, `{`, `}`, `\\` en el título
    rompe la compilación con un error críptico de LaTeX."""
    repl = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
            "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    # el backslash primero para no re-escapar los que introducimos
    out = s.replace("\\", "\x00")
    for k, v in repl.items():
        if k != "\\":
            out = out.replace(k, v)
    return out.replace("\x00", r"\textbackslash{}")

def footnote_numbering(mode: str) -> str:
    """LaTeX para numerar las notas al pie.

    `page` (def.) reinicia en cada página: bien para un libro de notas breves.
    `chapter` reinicia en cada capítulo: es lo que hace falta cuando el original
    numera por obra y se quiere CONSERVAR su numeración, para poder citar «*On
    Questions*, nota 115» y que cuadre con el impreso.
    `book` numera corrido de principio a fin.
    """
    if mode == "page":
        return r"\usepackage{perpage}\MakePerPage{footnote}"
    if mode == "chapter":
        return r"\counterwithin*{footnote}{chapter}"
    return ""                       # book: el contador de LaTeX ya es corrido


def preamble(title, author, lang, toc, graphicspath="", fnmode="page", fallback=""):
    unichars = "\n".join(
        r"\newunicodechar{%s}{{\normalfont\%s}}" % (u, c) for u, c in UNI2CMD.items())
    gpath = (r"\graphicspath{%s}" % "".join("{%s/}" % d for d in graphicspath)
             if graphicspath else "")
    fn = footnote_numbering(fnmode)
    title = latex_escape(title) if title else title
    author = latex_escape(author) if author else author
    titleblock = ""
    if title:
        authorline = (r"{\small\scshape %s} \\" % author) if author else ""
        titleblock = (
            "\\begin{titlingpage}\n\\centering\n"
            "{\\Huge\\scshape \\textsl{%s}\\\\ [1in]}\n%s\n"
            "\\end{titlingpage}\n" % (title, authorline))
    # tocdepth=subsection: el índice incluye las tablas/subsecciones de apéndices
    # (que van «starred» pero con \addcontentsline), no solo los capítulos.
    toctex = "\\settocdepth{subsection}\n\\tableofcontents\\clearpage\n" if toc else ""
    return r"""\documentclass[extrafontsizes,ebook,12pt,oneside]{memoir}
\usepackage{fontspec}                                  %% LuaLaTeX: Unicode nativo (no inputenc/T1)
%(fallback)s
\usepackage[shorthands=off, greek, english, main=%(lang)s]{babel}
\usepackage{wasysym}
\usepackage{starfont}                                  %% glifos astrológicos
\usepackage{newunicodechar}                            %% mapea ☉♄♈ -> starfont
\usepackage{graphicx}
\usepackage[export]{adjustbox}                          %% claves max width/height en \includegraphics
%(gpath)s
\usepackage{pdflscape}                                  %% páginas apaisadas para tablas anchas
\usepackage{longtable,booktabs,array}                  %% tablas de pandoc
\usepackage{fvextra}                                   %% verbatim que ajusta líneas largas
\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines,breakanywhere,fontsize=\small}
\usepackage{amssymb}
%% --- geometría idéntica a las ediciones janegca (Valens/Doroteo) ---
\usepackage[top=2cm, bottom=2cm, outer=2.5cm, inner=2.5cm,
            heightrounded, marginparwidth=2.3cm, marginparsep=0.5cm]{geometry}
\usepackage[colorlinks=true, linkcolor=black, urlcolor=blue, unicode]{hyperref}
\usepackage{xurl}                                      %% parte URLs largas en cualquier carácter (no desbordan)

%% --- estilo de capítulo bringhurst (idéntico a Valens/Doroteo) ---
\makechapterstyle{bringhurst}{%%
  \renewcommand{\chapterheadstart}{}
  \renewcommand{\chaptername}{}
  \renewcommand{\printchaptername}{}
  \renewcommand{\chapternamenum}{}
  \renewcommand{\printchapternum}{}
  \renewcommand{\afterchapternum}{}
  \renewcommand{\printchaptertitle}[1]{\raggedright\larger\scshape\MakeLowercase{##1}}
  \renewcommand{\afterchaptertitle}{\vskip 0.3em \hrule\vskip\onelineskip}
}
\setsecheadstyle{\bfseries\raggedright}
\setsubsecheadstyle{\bfseries\raggedright}
\setsubsubsecheadstyle{\small\bfseries}
\nonzeroparskip
\setlength{\parindent}{1.5em}

%% --- titulillo: nombre del capítulo (con su nº) CENTRADO y pequeño; folio ABAJO ---
\makepagestyle{forja}
\makeoddhead{forja}{}{\footnotesize\scshape\rightmark}{}
\makeevenhead{forja}{}{\footnotesize\scshape\rightmark}{}
\makeoddfoot{forja}{}{\thepage}{}
\makeevenfoot{forja}{}{\thepage}{}
\makeheadrule{forja}{0pt}{0pt}
%% marca = «N. Título» (el nº solo si el capítulo está numerado); las secciones no pisan
\renewcommand{\chaptermark}[1]{\markboth
  {\ifnum\value{chapter}>0 \thechapter.\ \fi #1}{\ifnum\value{chapter}>0 \thechapter.\ \fi #1}}
\renewcommand{\sectionmark}[1]{}

%% notas al pie: la numeración la elige --footnotes (por página / obra / corrida)
%(fn)s
\renewcommand{\footnoterule}{\kern -3pt \hrule width 0.4\columnwidth \kern 2.6pt}

%% pandoc: helpers que a veces exige el fragmento LaTeX
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\passthrough}[1]{#1}

%% glifos astrológicos Unicode -> starfont
%(unichars)s

\begin{document}
\chapterstyle{bringhurst}
\pagestyle{forja}             %% titulillo centrado y pequeño; folio abajo
\frontmatter
\pagenumbering{gobble}
%(titleblock)s
\pagenumbering{roman}
%(toctex)s""" % dict(lang=lang, unichars=unichars, titleblock=titleblock,
                     toctex=toctex, gpath=gpath, fn=fn, fallback=fallback)

# Detección del prefijo de capítulo numerado en el H1: «Capítulo N —», «Chapter N —»
# o simplemente «NN —» (numeración por dígitos, p. ej. «# 05 — La Luna»).
CHAP_RE = re.compile(
    r"^#\s+(?:(?:Cap[íi]tulo|Chapter)\s+\S+|\d{1,3})\s*(?:—|–|-{1,3}|\.)", re.I)
PREF_RE = re.compile(
    r"^\s*(?:(?:Cap[íi]tulo|Chapter)\s+\S+|\d{1,3})\s*(?:—|–|-{1,3}|\.)\s*", re.I)
# Títulos H1 de front-matter (para libros SIN «Capítulo N», organizados por Partes)
FRONT_RE = re.compile(
    r"^#\s+(prefacio|preface|pr[oó]logo|proemio|introducci[oó]n|introduction|"
    r"agradecimientos|acknowledg\w*|dedicatoria|nota\s+(?:preliminar|del|de)\b)", re.I)

def classify_roles(files):
    """Reparte los archivos según su encabezado H1.

    · Si el libro tiene capítulos «Capítulo/Chapter N»: esos son los numerados;
      lo anterior al primero = front-matter; lo no-numerado posterior = apéndices.
      Así memoir numera solo los capítulos reales (1..N).
    · Si NO hay «Capítulo N» (libro por Partes/Apéndices): el front-matter es el
      tramo inicial de archivos sin H1 o con título de front (portada, prefacio,
      introducción, agradecimientos…); todo lo demás son divisiones sin numerar,
      auto-rotuladas (Parte 1, Apéndice A, Glosario, Bibliografía, Índice)."""
    h1s = []
    for f in files:
        h1s.append(next((ln for ln in pathlib.Path(f).read_text(encoding="utf-8",
                   errors="replace").splitlines() if ln.startswith("# ")), ""))
    numbered = [bool(CHAP_RE.match(h)) for h in h1s]
    if any(numbered):
        fi = numbered.index(True)
        return ["front" if i < fi else ("chapter" if n else "appendix")
                for i, n in enumerate(numbered)]
    roles, in_front = [], True
    for h in h1s:
        if in_front and (not h or FRONT_RE.match(h)):
            roles.append("front")
        else:
            in_front = False
            roles.append("appendix")
    return roles

def make_unnumbered(tex):
    """Convierte el primer \\chapter de un fragmento en \\chapter* (sin número) pero
    lo mantiene en el índice y en el titulillo. Para apéndices."""
    m = re.search(r"\\chapter(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}", tex)
    if not m: return tex
    t = m.group(1)
    repl = (r"\chapter*{%s}\addcontentsline{toc}{chapter}{%s}\markboth{%s}{%s}"
            % (t, t, t, t))
    return tex[:m.start()] + repl + tex[m.end():]

_SEC_CMDS = ("subsubsection", "subsection", "section", "paragraph")

def star_sections(tex):
    """Vuelve sin numerar las secciones de un fragmento (front-matter/apéndices), para
    que no arrastren el contador de capítulo (p.ej. «25.11» en un apéndice sin número),
    PERO las mantiene en el índice general con su nº de página (`\\addcontentsline`) —
    si no, `--toc` de un libro de apéndices salía casi vacío.

    Escáner de llaves (no regex) para ser robusto al `\\footnote{...}` ANIDADO que
    pandoc mete en el título cuando el encabezado markdown lleva una NOTA
    (`## Cap 30 …10.ª casa[^164]`): en ese caso pandoc emite `\\section[corto]{largo\\footnote{…}}`
    y usamos el título CORTO (sin la nota) para el índice, dejando que la nota se
    imprima UNA sola vez en el cuerpo. Sin la forma corta, el título va tal cual al índice."""
    out, i, n = [], 0, len(tex)
    while i < n:
        cmd = None
        if tex[i] == "\\":
            for c in _SEC_CMDS:
                j = i + 1 + len(c)
                if tex.startswith("\\" + c, i) and j < n and tex[j] in "[{":
                    cmd = c
                    break
        if cmd is None:
            out.append(tex[i]); i += 1; continue
        j = i + 1 + len(cmd)
        short = None
        if tex[j] == "[":                        # título corto opcional (sin llaves anidadas)
            k = tex.find("]", j)
            if k == -1:
                out.append(tex[i]); i += 1; continue
            short = tex[j + 1:k]; j = k + 1
        if j >= n or tex[j] != "{":              # no era una sección con argumento
            out.append(tex[i]); i += 1; continue
        depth, k = 0, j                          # busca la llave de cierre equilibrada
        while k < n:
            if tex[k] == "{": depth += 1
            elif tex[k] == "}":
                depth -= 1
                if depth == 0: break
            k += 1
        title = tex[j + 1:k]
        toctext = short if short is not None else title
        if cmd == "paragraph":
            out.append(r"\%s*{%s}" % (cmd, title))
        else:
            out.append(r"\%s*{%s}\addcontentsline{toc}{%s}{%s}" % (cmd, title, cmd, toctext))
        i = k + 1
    return "".join(out)

_COLALIGN = {"l": r"\raggedright", "c": r"\centering", "r": r"\raggedleft"}

def wrap_table_columns(tex):
    """Hace que las columnas de ancho natural de pandoc (`{@{}ll@{}}`) envuelvan al
    ancho de página, repartiéndolo por igual. Evita que las tablas anchas (glosarios)
    se salgan del margen. Solo toca las de tipo l/c/r (no las que ya llevan p{}).
    Respeta la alineación por columna del markdown (`:-:` centro, `--:` derecha)."""
    def repl(m):
        letters = m.group(1)
        n = len(letters)
        w = r"\dimexpr(\linewidth-%d\tabcolsep)/%d\relax" % (2 * n, n)
        cols = "".join(r">{%s\arraybackslash}p{%s}" % (_COLALIGN[c], w) for c in letters)
        return r"\begin{longtable}[]{@{}" + cols + r"@{}}"
    return re.sub(r"\\begin\{longtable\}\[\]\{@\{\}([lcr]+)@\{\}\}", repl, tex)

def center_images(tex, maxw=r"0.72\linewidth"):
    """Centra cada imagen y le fija un tamaño máximo para que NO desborde el margen.
    Con `adjustbox[export]` la clave `max width` debe ir en las opciones de cada
    `\\includegraphics` (un `\\setkeys{Gin}{max width=...}` global NO se aplica). `max
    width`/`max height` solo reducen: las imágenes pequeñas conservan su tamaño natural."""
    def repl(m):
        path = m.group(1)
        return (r"\begin{center}\includegraphics[max width=%s,"
                r"max height=0.8\textheight,keepaspectratio]{%s}\end{center}"
                % (maxw, path))
    return re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", repl, tex)

def typeset_wide_tables(tex, min_cols=6):
    """Ajusta la densidad de cada tabla por su nº de columnas:
      · ≥ min_cols (6) columnas → página APAISADA (`landscape`) a ~7 pt: las tablas de
        muchas cifras (ascensiones, términos, faces, monomoiria) no caben legibles en
        vertical —los encabezados «Término N» se hifenan («Tér-mino») en columna
        estrecha aunque se achique la fuente, así que se rotan.
      · 5 columnas → vertical pero a `\\footnotesize` (compacta sin hifenar).
      · ≤4 columnas → tamaño normal (Lotes, combustión: caben cómodas vertical).
    Corre DESPUÉS de wrap_table_columns (que reparte el ancho): en apaisado
    `\\linewidth` es mayor, así que las columnas se ensanchan solas."""
    def _wrap(m):
        tbl = m.group(0)
        head = tbl.split("\n", 1)[0]
        ncol = head.count(r"\arraybackslash}p{")            # tablas ya envueltas
        if ncol == 0:                                        # spec cruda {@{}llll@{}}
            spec = re.search(r"\{@\{\}(.*?)@\{\}\}", head)
            ncol = len(re.findall(r"[lcrp]", spec.group(1))) if spec else 0
        if ncol >= min_cols:
            return ("\\begin{landscape}\n{\\fontsize{7pt}{8.4pt}\\selectfont\n"
                    + tbl + "\n}\n\\end{landscape}")
        if ncol >= 5:
            return "{\\footnotesize\n" + tbl + "\n}"
        # 4 columnas pero MUCHAS filas densas (p. ej. faces/decanos, 12 signos con
        # glifo+rango de grados por celda) → también compacta a footnotesize.
        if ncol == 4 and tbl.count(r"\tabularnewline") >= 10:
            return "{\\footnotesize\n" + tbl + "\n}"
        return tbl
    return re.sub(r"\\begin\{longtable\}.*?\\end\{longtable\}", _wrap, tex, flags=re.S)

def _attachable(line):
    """¿Se puede colgar una nota reubicada al final de esta línea? Sí en prosa o verso;
    NO en encabezados, tablas, código NI en definiciones de nota/enlace `[^x]:`/`[x]:`
    (colgarla ahí crearía una nota autorreferente -> \\footnote recursivo -> bucle)."""
    s = line.strip()
    if not s or s[0] in "#|`": return False
    if s.startswith("["): return False           # definición de nota o de enlace
    return True

def relocate_heading_footnotes(text):
    """Una nota `[^x]` en una línea de encabezado rompe LaTeX (\\footnote dentro de
    \\chapter/\\section + hyperref). La reubica a la primera línea de prosa/verso
    siguiente; si no hay ninguna antes de las definiciones, la deja en el título."""
    fnref = re.compile(r"\[\^[^\]]+\]")
    out, pending = [], []
    for line in text.split("\n"):
        m = re.match(r"^(#{1,6}\s+.*?)\s*((?:\[\^[^\]]+\])+)\s*$", line)
        if m:                                    # encabezado con nota(s) al final
            out.append(m.group(1)); pending += fnref.findall(m.group(2))
        elif pending and _attachable(line):
            out.append(line.rstrip() + "".join(pending)); pending = []
        else:
            out.append(line)
    if pending:                                  # nunca hubo dónde colgarla: al último encabezado
        for i in range(len(out) - 1, -1, -1):
            if out[i].startswith("#"):
                out[i] = out[i].rstrip() + " " + "".join(pending); break
    return "\n".join(out)

_NOTE_HEAD_RE = re.compile(r"^#{1,6}\s+(Notes|Notas)\s*$", re.I)

def strip_empty_note_heading(text):
    """Quita un encabezado «## Notas»/«## Notes» cuyo contenido son SOLO definiciones de
    nota `[^x]:` (y líneas en blanco). En md_to_pdf las notas se imprimen al PIE de página,
    así que ese encabezado queda VACÍO en el PDF (título huérfano en el índice y al final del
    capítulo). Se CONSERVAN las definiciones (pandoc las necesita para el pie); solo se borra
    la línea del título. Conservador: si bajo el encabezado hay cualquier otra cosa (prosa,
    tabla…), NO lo toca."""
    lines = text.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        if _NOTE_HEAD_RE.match(lines[i]):
            j, droppable = i + 1, True
            while j < n and not re.match(r"^#{1,6}\s", lines[j]):
                s = lines[j].strip()
                if s and not re.match(r"^\[\^[^\]]+\]:", s):
                    droppable = False; break
                j += 1
            if droppable:                        # solo definiciones (o nada) debajo -> fuera el título
                i += 1; continue
        out.append(lines[i]); i += 1
    return "\n".join(out)

def md_to_latex(mdfile, role):
    """Un .md -> fragmento LaTeX vía pandoc, según su rol (front/chapter/appendix).
    En capítulos numerados quita el literal «Capítulo N —» del título (memoir pone el
    número); en apéndices convierte el \\chapter en \\chapter* (sin número)."""
    src = strip_empty_note_heading(
        relocate_heading_footnotes(pathlib.Path(mdfile).read_text(encoding="utf-8")))
    if role == "chapter":                    # memoir numera; quitar el prefijo literal
        lines = src.split("\n")
        for i, ln in enumerate(lines):
            if ln.startswith("# "):
                lines[i] = "# " + PREF_RE.sub("", ln[2:]); break
        src = "\n".join(lines)
    r = subprocess.run(
        ["pandoc", "-f", "gfm+raw_attribute", "-t", "latex", "--top-level-division=chapter", "--wrap=none"],
        input=src, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"pandoc falló en {mdfile}:\n{r.stderr[:1500]}\n"); sys.exit(1)
    tex = r.stdout
    if role == "appendix":                   # capítulo sin nº + secciones sin nº
        tex = star_sections(make_unnumbered(tex))
    elif role == "front":                    # secciones sin nº
        tex = star_sections(tex)
    # las tablas se reparten al ancho de página en TODOS los roles (también capítulos):
    # antes solo se envolvían en front/apéndices y las de los capítulos desbordaban.
    tex = wrap_table_columns(tex)
    return typeset_wide_tables(center_images(tex))   # imágenes centradas/acotadas; tablas anchas apaisadas

def main():
    ap = argparse.ArgumentParser(description="markdown de estudio -> PDF bello (memoir/starfont)")
    ap.add_argument("out", help="PDF de salida")
    ap.add_argument("md", nargs="+", help="archivos .md, en el orden del libro (un capítulo c/u)")
    ap.add_argument("--title", default="", help="título de portada (si se omite, sin portada)")
    ap.add_argument("--author", default="", help="autor/traductor para la portada")
    ap.add_argument("--lang", default="spanish", help="idioma babel principal (def: spanish)")
    ap.add_argument("--toc", action="store_true", help="incluir índice general")
    ap.add_argument("--image-dir", action="append", default=[], metavar="DIR",
                    help="carpeta donde buscar las imágenes (repetible); se añaden al graphicspath")
    ap.add_argument("--keep-tex", action="store_true", help="conservar el .tex intermedio junto al PDF")
    ap.add_argument("--font-fallback", metavar="FUENTE", default="",
                    help="fuente de reserva para caracteres que la principal (Latin Modern) no tenga "
                         "—p. ej. 'Noto Naskh Arabic' para escritura árabe, 'Noto Sans CJK SC' para CJK—. "
                         "Opt-in: sin esta bandera, nada cambia. Requiere la fuente instalada (fc-list).")
    ap.add_argument("--footnotes", choices=("page", "chapter", "book"), default="page",
                    metavar="MODO",
                    help="numeración de las notas: page = reinicia en cada página (def.); "
                         "chapter = reinicia en cada capítulo, para CONSERVAR la del "
                         "original cuando numera por obra; book = corrida de principio a fin")
    a = ap.parse_args()

    # graphicspath = carpetas de imágenes indicadas + carpeta de cada .md (rutas absolutas)
    gdirs = [str(pathlib.Path(d).resolve()) for d in a.image_dir]
    for m in a.md:
        d = str(pathlib.Path(m).resolve().parent)
        if d not in gdirs: gdirs.append(d)

    # AVISO: el griego POLITÓNICO (U+1F00–1FFF: espíritus/acentos, ᾳ) NO está en Latin
    # Modern y se pierde EN SILENCIO sin --font-fallback (el básico en MAYÚSCULAS sí sale,
    # lo que engaña). Medido en Brennan: el griego del horóscopo salió como huecos.
    if not a.font_fallback:
        poly = re.compile("[ἀ-῿]")
        hit = next((m for m in a.md if poly.search(pathlib.Path(m).read_text(encoding="utf-8"))), None)
        if hit:
            sys.stderr.write(
                f"AVISO: griego politónico en «{pathlib.Path(hit).name}» y sin --font-fallback; "
                "Latin Modern lo descarta en silencio. Usa --font-fallback \"GFS Artemisia\".\n")

    roles = classify_roles(a.md)
    texs = [md_to_latex(m, r) for m, r in zip(a.md, roles)]
    front = "\n\n".join(t for t, r in zip(texs, roles) if r == "front")
    mainb = "\n\n".join(t for t, r in zip(texs, roles) if r != "front")
    fallback = ""
    if a.font_fallback:
        # LuaLaTeX: los glifos que Latin Modern no tenga (árabe, CJK…) caen a la
        # fuente de reserva, con shaping HarfBuzz (mode=harf) para la escritura árabe.
        fallback = (r"\usepackage{luaotfload}" "\n"
                    r'\directlua{luaotfload.add_fallback("forjafb", {"%s:mode=harf;"})}' "\n"
                    r"\setmainfont{Latin Modern Roman}[RawFeature={fallback=forjafb}]") % a.font_fallback
    doc = (preamble(a.title, a.author, a.lang, a.toc, gdirs, a.footnotes, fallback)
           + front + "\n\\mainmatter\n" + mainb + "\n\\end{document}\n")

    out = pathlib.Path(a.out).resolve()
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        tex = td / (out.stem + ".tex")
        tex.write_text(doc, encoding="utf-8")
        for i in (1, 2):                       # 2 pasadas: TOC/refs
            try:
                r = subprocess.run(["lualatex", "-interaction=nonstopmode", tex.name],
                                   cwd=td, capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:  # red de seguridad: aborta un posible bucle
                sys.stderr.write("lualatex superó 300s (posible bucle en el markdown: "
                                 "¿nota autorreferente, tabla o bloque irrompible?). Abortado.\n")
                if a.keep_tex: shutil.copy(tex, out.with_suffix(".tex"))
                sys.exit(2)
        pdf = td / (out.stem + ".pdf")
        if not pdf.exists():
            tail = "\n".join(l for l in r.stdout.splitlines() if l.startswith("!"))[:2000]
            sys.stderr.write(f"lualatex no produjo PDF. Errores:\n{tail or r.stdout[-1500:]}\n")
            if a.keep_tex: shutil.copy(tex, out.with_suffix(".tex"))
            sys.exit(1)
        shutil.copy(pdf, out)
        if a.keep_tex: shutil.copy(tex, out.with_suffix(".tex"))
    info = subprocess.run(["pdfinfo", str(out)], capture_output=True, text=True).stdout
    pages = next((l.split()[-1] for l in info.splitlines() if l.startswith("Pages")), "?")
    print(f"  {out.name}: {pages} páginas ({len(a.md)} capítulos)")

if __name__ == "__main__":
    main()
