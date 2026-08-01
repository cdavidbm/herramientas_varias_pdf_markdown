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


DEFAULT_GEOMETRY = ("top=2cm, bottom=2cm, outer=2.5cm, inner=2.5cm, "
                    "heightrounded, marginparwidth=2.3cm, marginparsep=0.5cm")

# Tamaño de fuente para las tablas «normales» (≤4 col no densas). Lo fija --table-size
# en main(); las tablas anchas siguen su propia lógica (footnotesize / apaisado 7pt).
TABLE_SIZE = "normal"
# Libros cuyos encabezados YA traen su propia numeración («## Capítulo 10.1: …», al estilo
# de Dykes): la numeración automática de memoir se DUPLICA con ella («10.1. Capítulo 10.1:»)
# y, peor, puede DIVERGIR —basta un subapartado sin numerar intercalado para que el contador
# se adelante—, con lo que las remisiones del texto («véase el Cap. 20.6») dejarían de casar.
OWN_SEC_NUMS = False
# Imprimir la leyenda de `![…](img)` bajo la imagen (ver split_image_captions).
FIG_CAPTIONS = False
_TABLE_SIZE_CMD = {"normal": "", "small": r"\small",
                   "footnotesize": r"\footnotesize", "scriptsize": r"\scriptsize"}


def preamble(title, author, lang, toc, graphicspath="", fnmode="page", fallback="",
             fontsize=12, geometry=DEFAULT_GEOMETRY, tocdepth="subsection",
             chapstyle="bringhurst", arabfont="", short_headers=False, leading=None,
             subtitles=()):
    unichars = "\n".join(
        r"\newunicodechar{%s}{{\normalfont\%s}}" % (u, c) for u, c in UNI2CMD.items())
    gpath = (r"\graphicspath{%s}" % "".join("{%s/}" % d for d in graphicspath)
             if graphicspath else "")
    fn = footnote_numbering(fnmode)
    leadingtex = (r"\linespread{%s}" % leading) if leading else ""
    title = latex_escape(title) if title else title
    author = latex_escape(author) if author else author
    titleblock = ""
    if title:
        authorline = (r"{\small\scshape %s} \\" % author) if author else ""
        # Subtítulos escalonados bajo el título (transliteración, título en la
        # lengua del lector, mención de edición…). El primero va destacado y el
        # resto en cuerpo menor, con un filete entre el bloque y el pie.
        subs = ""
        sizes = [r"\LARGE", r"\large", r"\large"]
        for i, s in enumerate([latex_escape(x) for x in subtitles]):
            # El subtítulo admite el énfasis de markdown: un título de obra
            # («*De Imaginibus*») pide cursiva, y sin esto los asteriscos se
            # IMPRIMEN tal cual en la portada.
            s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
            s = re.sub(r"\*(.+?)\*", r"\\emph{\1}", s)
            subs += "{%s %s\\\\[0.45in]}\n" % (sizes[min(i, len(sizes) - 1)], s)
        gap = "[0.9in]" if subs else "[1in]"
        titleblock = (
            "\\begin{titlingpage}\n\\centering\n\\vspace*{1.2in}\n"
            "{\\Huge\\scshape \\textsl{%s}\\\\ %s}\n%s"
            "\\vfill\n%s\n"
            "\\end{titlingpage}\n" % (title, gap, subs, authorline))
    # tocdepth=subsection: el índice incluye las tablas/subsecciones de apéndices
    # (que van «starred» pero con \addcontentsline), no solo los capítulos.
    # \clearpage ANTES y después: el índice abre siempre en página propia, aunque lo
    # preceda la portada o cualquier otro material. Y `\tableofcontents*` (forma ESTRELLADA
    # de memoir) para que el índice NO se liste a sí mismo como primera entrada.
    toctex = ("\\clearpage\n\\settocdepth{%s}\n\\tableofcontents*\\clearpage\n"
              % tocdepth) if toc else ""
    # titulillo de página: por defecto «N. Título»; con --short-headers, solo «Capítulo N»
    # (útil cuando los títulos son largos y se pegan al cuerpo). Los capítulos SIN número
    # (front-matter: Introducción…) siguen mostrando su título en ambos casos.
    if short_headers:
        # \rhchapname = el «Capítulo/Chapter» de babel, capturado ANTES de que el estilo de
        # capítulo vacíe \chaptername (los estilos hacen \renewcommand{\chaptername}{}).
        # En los capítulos SIN numerar el titulillo repetía el título ENTERO, y en
        # este fondo son larguísimos («Libro Uno, Capítulo Siete: En qué grado
        # existe todo en el universo, y muchas otras cosas…»): desbordaban el
        # encabezado hasta pegarse al cuerpo. \forjacorto recorta por los dos
        # puntos —donde acaba el rótulo— y deja intacto el título sin ellos.
        chaptermark = (
            "\\makeatletter\n"
            "\\def\\forja@corta#1:#2\\forja@fin{#1}\n"
            "\\newcommand{\\forjacorto}[1]{\\forja@corta#1:\\forja@fin}\n"
            "\\makeatother\n"
            r"\renewcommand{\chaptermark}[1]{\markboth"
            r"{\ifnum\value{chapter}>0 \rhchapname\ \thechapter\else \forjacorto{#1}\fi}"
            r"{\ifnum\value{chapter}>0 \rhchapname\ \thechapter\else \forjacorto{#1}\fi}}")
    else:
        chaptermark = (r"\renewcommand{\chaptermark}[1]{\markboth"
                       r"{\ifnum\value{chapter}>0 \thechapter.\ \fi #1}"
                       r"{\ifnum\value{chapter}>0 \thechapter.\ \fi #1}}")
    return r"""\documentclass[extrafontsizes,ebook,%(fontsize)spt,oneside]{memoir}
\usepackage{fontspec}                                  %% LuaLaTeX: Unicode nativo (no inputenc/T1)
%(fallback)s
%% bidi=basic: LuaTeX reordena de DERECHA A IZQUIERDA la escritura árabe/hebrea.
%% Sin esto el árabe sale con las letras sueltas y en orden invertido (el fallback de
%% fuente da los glifos, pero NO el shaping contextual ni el sentido de lectura).
\usepackage[shorthands=off, greek, english, bidi=basic, main=%(lang)s]{babel}
%(arabic)s
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
%% --- geometría (por defecto = ediciones janegca Valens/Doroteo; override con --geometry) ---
\usepackage[%(geometry)s]{geometry}
%(leading)s
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
%% --- estilo alternativo «mayuscula»: título de capítulo MÁS GRANDE, EN NEGRITA y en MAYÚSCULAS ---
\makechapterstyle{mayuscula}{%%
  \renewcommand{\chapterheadstart}{}
  \renewcommand{\chaptername}{}
  \renewcommand{\printchaptername}{}
  \renewcommand{\chapternamenum}{}
  \renewcommand{\printchapternum}{}
  \renewcommand{\afterchapternum}{}
  \renewcommand{\printchaptertitle}[1]{\raggedright\LARGE\bfseries\MakeUppercase{##1}}
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
%% marca de titulillo (según --short-headers); las secciones no pisan
%(chaptermark)s
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
\newcommand{\rhchapname}{}\let\rhchapname\chaptername   %% guarda «Capítulo» antes de que el estilo lo vacíe
\chapterstyle{%(chapstyle)s}
\pagestyle{forja}             %% titulillo centrado y pequeño; folio abajo
\frontmatter
\pagenumbering{gobble}
%(titleblock)s
\pagenumbering{roman}
%(toctex)s""" % dict(lang=lang, unichars=unichars, titleblock=titleblock,
                     toctex=toctex, gpath=gpath, fn=fn, fallback=fallback,
                     fontsize=fontsize, geometry=geometry, chapstyle=chapstyle,
                     arabic=arabfont, chaptermark=chaptermark, leading=leadingtex)

# Detección del prefijo de capítulo numerado en el H1: «Capítulo N —», «Chapter N —»,
# «Capítulo N: …» o simplemente «NN —» (numeración por dígitos, p. ej. «# 05 — La Luna»).
# Los DOS PUNTOS son separador tan común como el guion (medido en al-Kindī, «The Forty
# Chapters»: todos los H1 son «Capítulo N: …»). Sin reconocerlos, classify_roles no ve
# capítulos numerados, los manda todos a `appendix` (\chapter*) y entonces
# `--footnotes chapter` NO reinicia las notas, porque el contador de capítulo no avanza.
CHAP_RE = re.compile(
    r"^#\s+(?:(?:Cap[íi]tulo|Chapter)\s+\S+|\d{1,3})\s*(?:—|–|-{1,3}|\.|:)", re.I)
PREF_RE = re.compile(
    r"^\s*(?:(?:Cap[íi]tulo|Chapter)\s+\S+|\d{1,3})\s*(?:—|–|-{1,3}|\.|:)\s*", re.I)
# Títulos H1 de front-matter (para libros SIN «Capítulo N», organizados por Partes)
FRONT_RE = re.compile(
    r"^#\s+(prefacio|preface|pr[oó]logo|proemio|introducci[oó]n|introduction|"
    r"agradecimientos|acknowledg\w*|dedicatoria|nota\s+(?:preliminar|del|de)\b)", re.I)

def classify_roles(files, front_matter: int = 0):
    """Reparte los archivos según su encabezado H1.

    · Si el libro tiene capítulos «Capítulo/Chapter N»: esos son los numerados;
      lo anterior al primero = front-matter; lo no-numerado posterior = apéndices.
      Así memoir numera solo los capítulos reales (1..N).
    · Si NO hay «Capítulo N» (libro por Partes/Apéndices): el front-matter es el
      tramo inicial de archivos sin H1 o con título de front (portada, prefacio,
      introducción, agradecimientos…); todo lo demás son divisiones sin numerar,
      auto-rotuladas (Parte 1, Apéndice A, Glosario, Bibliografía, Índice)."""
    if front_matter:
        # Reparto EXPLÍCITO: los N primeros archivos son front-matter (numeración
        # romana). Se usa cuando la heurística de títulos no acierta —p. ej. un
        # «Estudio introductorio» ajeno, o capítulos rotulados «Libro Uno,
        # Capítulo Uno» que no casan con «Capítulo N»— y evita arrastrar al
        # front-matter secciones que SÍ son parte de la obra (el Prólogo).
        return ["front" if i < front_matter else "appendix"
                for i in range(len(files))]
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
    lo mantiene en el índice y en el titulillo. Para apéndices.

    Escáner de llaves (no regex): el título puede llevar anidamiento de VARIOS niveles
    —pandoc envuelve un `\\chapter` cuyo título tiene ÉNFASIS en
    `\\chapter{\\texorpdfstring{…\\emph{…}…}{…}}` (2 niveles)—; un regex de un solo nivel
    NO lo captura y el capítulo se queda NUMERADO (bug: la Traducción de las Flowers salía
    como «1 …» mientras el resto de apéndices iban sin número). El escáner es robusto a
    cualquier profundidad. Para el índice/titulillo se usa la 2.ª rama de
    `\\texorpdfstring{pdf}{tex}` si está (texto plano, sin `\\emph`), o el título tal cual."""
    m = re.search(r"\\chapter(\[[^\]]*\])?\{", tex)
    if not m:
        return tex
    open_brace = m.end() - 1
    depth, i, n = 0, open_brace, len(tex)
    while i < n:
        if tex[i] == "{":
            depth += 1
        elif tex[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    title = tex[open_brace + 1:i]                       # contenido completo de \chapter{…}
    # título para índice/titulillo: la rama TeX de \texorpdfstring{pdf}{tex} si existe
    tm = re.match(r"\\texorpdfstring\{", title)
    toc_title = title
    if tm:
        d, k = 0, tm.end() - 1
        while k < len(title):                          # saltar la 1.ª rama {pdf}
            if title[k] == "{": d += 1
            elif title[k] == "}":
                d -= 1
                if d == 0: break
            k += 1
        m2 = re.match(r"\{", title[k + 1:])
        if m2:                                         # 2.ª rama {tex}
            d, s = 0, k + 1
            for j in range(k + 1, len(title)):
                if title[j] == "{": d += 1
                elif title[j] == "}":
                    d -= 1
                    if d == 0:
                        toc_title = title[s + 1:j]; break
    repl = (r"\chapter*{%s}\addcontentsline{toc}{chapter}{%s}\markboth{%s}{%s}"
            % (title, toc_title, toc_title, toc_title))
    return tex[:m.start()] + repl + tex[i + 1:]

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
            # Titulillo: en un capítulo SIN numerar, memoir repite el título
            # entero, y los de este fondo son larguísimos («Libro Uno, Capítulo
            # Siete: En qué grado existe todo en el universo, y muchas otras
            # cosas…»): desbordan el encabezado y se pegan al cuerpo. Se recorta
            # por los dos puntos, que es justo donde acaba el rótulo.
            mark = ""
            if cmd == "chapter" and SHORT_MARKS:
                corto = title.split(":")[0].strip()
                if corto and corto != title:
                    mark = r"\chaptermark{%s}" % title
            out.append(r"\%s*{%s}%s\addcontentsline{toc}{%s}{%s}"
                       % (cmd, title, mark, cmd, toctext))
        i = k + 1
    return "".join(out)

SHORT_MARKS = False   # --short-headers: recorta el titulillo por los dos puntos

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
        # `scale` en vez de `max width` cuando el JPEG miente sobre su densidad:
        # ver check_image_density(). Aquí basta con emitir siempre lo mismo.
        return (r"\begin{center}\includegraphics[max width=%s,"
                r"max height=0.8\textheight,keepaspectratio]{%s}\end{center}"
                % (maxw, path))
    return re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", repl, tex)


def check_image_density(paths, fix=True, dpi=96):
    """Corrige (o denuncia) los JPEG cuya densidad JFIF es absurda (0 o 1 dpi).

    **Fallo SILENCIOSO y caro de encontrar.** A 1 dpi, una imagen de 653 px de
    ancho mide 653 PULGADAS; eso desborda la aritmética de dimensiones de TeX
    (`arithmetic number too big`), `adjustbox` no puede calcular la escala y
    lualatex **descarta la imagen dejando la leyenda impresa**. El PDF se genera
    sin error, el recuento de figuras del markdown cuadra y el log de este script
    no dice nada: solo se ve contando las imágenes del PDF con `pdfimages -list`
    o mirando la página. Medido en *Astral High Magic*: 3 de 4 cartas
    astrológicas desaparecieron así.

    El arreglo son 5 bytes del segmento APP0 —unidades + Xdensity + Ydensity—,
    así que NO recomprime: los píxeles quedan intactos.
    """
    import struct
    tocadas = []
    for p in paths:
        p = pathlib.Path(p)
        if p.suffix.lower() not in (".jpg", ".jpeg") or not p.is_file():
            continue
        b = bytearray(p.read_bytes())
        if b[:2] != b"\xff\xd8":
            continue
        i = 2
        while i < len(b) - 4 and b[i] == 0xFF:
            seg = struct.unpack(">H", b[i + 2:i + 4])[0]
            if b[i + 1] == 0xE0 and b[i + 4:i + 9] == b"JFIF\x00":
                o = i + 4 + 5 + 2          # tras 'JFIF\0' y la versión (2 bytes)
                units = b[o]
                xd = struct.unpack(">H", b[o + 1:o + 3])[0]
                yd = struct.unpack(">H", b[o + 3:o + 5])[0]
                if units == 0 or xd <= 1 or yd <= 1:
                    tocadas.append((p, units, xd, yd))
                    if fix:
                        b[o] = 1
                        b[o + 1:o + 3] = struct.pack(">H", dpi)
                        b[o + 3:o + 5] = struct.pack(">H", dpi)
                        p.write_bytes(bytes(b))
                break
            i += 2 + seg
    for p, u, x, y in tocadas:
        print(f"  {'corregida' if fix else 'AVISO'}: densidad JFIF {x}x{y} "
              f"(unidades={u}) en {p.name} → {dpi} dpi"
              + ("" if fix else "  ← lualatex la DESCARTARÍA en silencio"))
    return tocadas

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
        # tablas «normales» (≤4 col no densas): tamaño base según --table-size
        cmd = _TABLE_SIZE_CMD.get(TABLE_SIZE, "")
        if cmd:
            return "{" + cmd + "\n" + tbl + "\n}"
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

IMG_CAP_RE = re.compile(r"^!\[(?P<alt>.+?)\]\((?P<path>[^)]+)\)(?P<cola>.*)$")

def split_image_captions(src):
    """`![Leyenda](img.png)` -> imagen SOLA + su leyenda impresa debajo, centrada.

    Sin esto la leyenda se PIERDE: el lector `gfm` de pandoc no tiene `implicit_figures`,
    así que el texto alternativo no llega al LaTeX y la imagen sale muda. En un libro
    traducido eso es grave —el pie del diagrama solo existiría en el markdown—.

    Se emite como bloque centrado NO flotante (`raw_attribute`), no como `figure`: los
    textos de este taller dicen «véase la figura de abajo», así que la imagen debe
    quedarse donde el autor la puso y no irse a flotar a otra página. La leyenda pasa
    por pandoc como markdown normal, de modo que conserva cursivas y notas `[^N]` —y la
    nota que cuelga de la línea de la imagen deja de imprimirse como un número suelto."""
    out = []
    for ln in src.split("\n"):
        m = IMG_CAP_RE.match(ln)
        if not m:
            out.append(ln); continue
        alt, path, cola = m.group("alt"), m.group("path"), m.group("cola")
        out.append("![](%s)" % path)
        out.append("")
        out.append("`\\begin{center}\\small\\bfseries `{=latex}%s%s`\\end{center}`{=latex}"
                   % (alt, cola))
    return "\n".join(out)

def md_to_latex(mdfile, role):
    """Un .md -> fragmento LaTeX vía pandoc, según su rol (front/chapter/appendix).
    En capítulos numerados quita el literal «Capítulo N —» del título (memoir pone el
    número); en apéndices convierte el \\chapter en \\chapter* (sin número)."""
    src = strip_empty_note_heading(
        relocate_heading_footnotes(pathlib.Path(mdfile).read_text(encoding="utf-8")))
    if FIG_CAPTIONS:
        src = split_image_captions(src)
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
    elif role == "chapter" and OWN_SEC_NUMS:  # el propio título ya numera: no duplicar
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
    ap.add_argument("--font-fallback", metavar="FUENTE", action="append", default=[],
                    help="fuente de reserva para caracteres que la principal (Latin Modern) no tenga "
                         "—p. ej. 'Noto Naskh Arabic' para escritura árabe, 'Noto Sans CJK SC' para CJK—. "
                         "Opt-in: sin esta bandera, nada cambia. Requiere la fuente instalada (fc-list).")
    ap.add_argument("--footnotes", choices=("page", "chapter", "book"), default="page",
                    metavar="MODO",
                    help="numeración de las notas: page = reinicia en cada página (def.); "
                         "chapter = reinicia en cada capítulo, para CONSERVAR la del "
                         "original cuando numera por obra; book = corrida de principio a fin")
    ap.add_argument("--fontsize", type=int, default=12, metavar="PT",
                    help="tamaño de letra base en puntos (def: 12). 11 compacta el libro.")
    ap.add_argument("--geometry", default=DEFAULT_GEOMETRY, metavar="OPTS",
                    help="opciones del paquete geometry (márgenes). Por defecto = estilo "
                         "janegca. Ej. compacto: 'top=1.6cm, bottom=1.6cm, outer=1.8cm, "
                         "inner=1.8cm, heightrounded'.")
    ap.add_argument("--hebrew-font", metavar="FUENTE", default="",
                    help="activa escritura HEBREA correcta (de derecha a izquierda) "
                         "declarando el locale de babel con esta fuente, p. ej. "
                         "'Noto Serif Hebrew'. Sin ella, el hebreo se pierde EN "
                         "SILENCIO: Latin Modern no lo tiene y el log no avisa.")
    ap.add_argument("--arabic-font", metavar="FUENTE", default="",
                    help="activa escritura ÁRABE correcta (ligada y de derecha a izquierda) "
                         "declarando el locale de babel con esta fuente, p.ej. 'Noto Naskh Arabic'. "
                         "Sin esto el árabe sale con letras sueltas y en orden invertido.")
    ap.add_argument("--chapter-style", choices=("bringhurst", "mayuscula"),
                    default="bringhurst", metavar="ESTILO",
                    help="estilo del título de capítulo: bringhurst (versalitas, def.) "
                         "o mayuscula (más grande, negrita, MAYÚSCULAS)")
    ap.add_argument("--toc-depth", choices=("chapter", "section", "subsection"),
                    default="subsection", metavar="NIVEL",
                    help="profundidad del índice (def: subsection). chapter = un solo nivel.")
    ap.add_argument("--short-headers", action="store_true",
                    help="titulillo de página = solo «Capítulo N» (útil si los títulos son "
                         "largos y se pegan al cuerpo); por defecto muestra «N. Título».")
    ap.add_argument("--leading", type=float, default=None, metavar="FACTOR",
                    help="interlineado: factor de \\linespread (def: sin cambio, ~1.0). "
                         "<1 compacta (p. ej. 0.97 aprieta un poco sin agobiar), >1 airea.")
    ap.add_argument("--table-size", choices=("normal", "small", "footnotesize", "scriptsize"),
                    default="normal", metavar="TAM",
                    help="tamaño de letra de las tablas «normales» (≤4 col no densas), p. ej. "
                         "las tablas maestras 2-col (def: normal). small/footnotesize las "
                         "compactan; las tablas anchas ya se achican/apaisan solas.")
    ap.add_argument("--figure-captions", action="store_true",
                    help="imprime el texto alternativo de las imágenes como PIE de figura "
                         "centrado bajo cada una. Sin esto se pierde: el lector gfm de "
                         "pandoc no pasa el alt al LaTeX y la imagen sale muda.")
    ap.add_argument("--own-section-numbers", action="store_true",
                    help="los encabezados de sección YA traen su numeración en el texto "
                         "(«## Capítulo 10.1: …», estilo Dykes): no numerarlas también con "
                         "memoir. Evita el «10.1. Capítulo 10.1:» duplicado y, sobre todo, "
                         "que la numeración automática DIVERJA de la del autor cuando hay "
                         "subapartados sin numerar intercalados (rompería las remisiones). "
                         "Siguen apareciendo en el índice con su página.")
    ap.add_argument("--no-fix-density", action="store_true",
                    help="no corregir la densidad JFIF absurda (0/1 dpi) de los "
                         "JPEG: solo avisar. Sin corregir, lualatex DESCARTA esas "
                         "imágenes en silencio y deja la leyenda impresa.")
    ap.add_argument("--subtitle", action="append", default=[], metavar="TEXTO",
                    help="línea(s) bajo el título de portada (repetible): "
                         "transliteración, título traducido, mención de edición…")
    ap.add_argument("--front-matter", type=int, default=0, metavar="N",
                    help="los N primeros archivos son front-matter (numeración "
                         "ROMANA): úsalo cuando la heurística de títulos no acierte")
    ap.add_argument("--start-chapter", type=int, default=None, metavar="N",
                    help="arranca la numeración de capítulos en N (def: 1). Para obras "
                         "MULTIVOLUMEN cuyo tomo continúa la numeración del anterior "
                         "(p. ej. --start-chapter 61 para un Vol. II que empieza en el cap. 61).")
    a = ap.parse_args()

    global TABLE_SIZE, OWN_SEC_NUMS, FIG_CAPTIONS
    TABLE_SIZE = a.table_size
    OWN_SEC_NUMS = a.own_section_numbers
    FIG_CAPTIONS = a.figure_captions

    # graphicspath = carpetas de imágenes indicadas + carpeta de cada .md (rutas absolutas)
    gdirs = [str(pathlib.Path(d).resolve()) for d in a.image_dir]
    for m in a.md:
        d = str(pathlib.Path(m).resolve().parent)
        if d not in gdirs: gdirs.append(d)

    # Un JPEG con densidad JFIF de 0/1 dpi desaparece del PDF EN SILENCIO
    # (ver check_image_density). Se revisa antes de compilar.
    _jpegs = [q for d in gdirs for q in pathlib.Path(d).rglob("*.jp*g")]
    check_image_density(_jpegs, fix=not a.no_fix_density)

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

    global SHORT_MARKS
    SHORT_MARKS = a.short_headers
    roles = classify_roles(a.md, a.front_matter)
    texs = [md_to_latex(m, r) for m, r in zip(a.md, roles)]
    front = "\n\n".join(t for t, r in zip(texs, roles) if r == "front")
    mainb = "\n\n".join(t for t, r in zip(texs, roles) if r != "front")
    fallback = ""
    if a.font_fallback:
        # LuaLaTeX: los glifos que Latin Modern no tenga (árabe, CJK…) caen a la
        # fuente de reserva, con shaping HarfBuzz (mode=harf) para la escritura árabe.
        # REPETIBLE: se pueden encadenar varias reservas (p.ej. árabe + griego).
        lista = ", ".join('"%s:mode=harf;"' % fnt for fnt in a.font_fallback)
        fallback = (r"\usepackage{luaotfload}" "\n"
                    r'\directlua{luaotfload.add_fallback("forjafb", {%s})}' "\n"
                    r"\setmainfont{Latin Modern Roman}[RawFeature={fallback=forjafb}]") % lista
    arabtex = ""
    if a.arabic_font:
        # onchar=ids fonts -> babel detecta los caracteres árabes y les aplica SOLO a
        # ellos la lengua y la fuente árabes; Script=Arabic activa el shaping contextual
        # (las letras se ligan). Sin onchar el texto queda en Latin Modern (invisible) y
        # sin Script=Arabic las letras salen sueltas.
        arabtex = ("\\babelprovide[import=ar, onchar=ids fonts]{arabic}\n"
                   "\\babelfont[arabic]{rm}[Script=Arabic]{%s}" % a.arabic_font)
    if a.hebrew_font:
        # Mismo mecanismo para el HEBREO, que también es de derecha a izquierda
        # (`bidi=basic` ya está en el preámbulo). Imprescindible en el fondo
        # cabalístico: sin esto los nombres divinos y las tablas de Agripa salen
        # como huecos, y el log de lualatex no dice nada.
        if arabtex:
            arabtex += "\n"
        arabtex += ("\\babelprovide[import=he, onchar=ids fonts]{hebrew}\n"
                    "\\babelfont[hebrew]{rm}[Script=Hebrew]{%s}" % a.hebrew_font)
    # --start-chapter N: arranca la numeración de capítulos en N (obras multivolumen,
    # p. ej. el Vol. II que continúa en el cap. 61). setcounter a N-1 antes del 1er \chapter.
    mainstart = "\n\\mainmatter\n"
    if a.start_chapter:
        mainstart += "\\setcounter{chapter}{%d}\n" % (a.start_chapter - 1)
    doc = (preamble(a.title, a.author, a.lang, a.toc, gdirs, a.footnotes, fallback,
                    a.fontsize, a.geometry, a.toc_depth, a.chapter_style, arabtex,
                    short_headers=a.short_headers, leading=a.leading,
                    subtitles=a.subtitle)
           + front + mainstart + mainb + "\n\\end{document}\n")

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
