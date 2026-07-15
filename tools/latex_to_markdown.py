#!/usr/bin/env python3
"""latex_to_markdown.py — Convierte un libro en LaTeX a markdown de estudio (para
NotebookLM, traducción, lectura), pensado para ediciones LaTeX de clásicos —típicamente
astrológicos— que usan un `.tex` maestro con `\\input{parte/seccion}` por capítulo.

Qué hace:
- Expande los `\\input{...}` del maestro en orden (un `.md` por libro/capítulo).
- Mapea los símbolos de la fuente **starfont/wasysym** (`\\Sun`, `\\Saturn`, `\\Aries`,
  `\\Trine`…) a sus caracteres **Unicode** (☉ ♄ ♈ △…) — así se ven en markdown/NotebookLM.
- Reencamina las figuras `\\includegraphics{charts/NAME}` a imágenes rasterizadas
  (`--imgdir/NAME.png`); convierte antes los PDF/EPS de cartas con `pdftoppm`.
- Limpia la maquetación que no aporta al estudio: `\\index`, `\\marginnote`/`\\mn`,
  `\\secbr`, `\\hl` (conserva el texto), `\\S`, envoltorios `figure/wrapfigure/center`.
- Pasa el resultado a **pandoc** (`-f latex -t gfm`) y des-escapa los `<...>`/`[...]`
  de restitución del traductor.

Uso:
    python3 latex_to_markdown.py bookNN.tex --root <dir_latex> --out bookNN.md \\
            [--imgdir ../imagenes/charts]

`--root` = carpeta donde resolver los `\\input`. `--imgdir` = ruta (relativa al .md) de
las PNG de las figuras. Genérico: si un libro usa otros símbolos/comandos, amplía SYM o
la lista de comandos a limpiar. Ver README/CLAUDE.md de La Forja.
"""
import re, sys, subprocess, argparse, pathlib

# --- símbolos starfont/wasysym -> Unicode astronómico/astrológico ---
SYM = {
    "Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Earth":"⊕","Mars":"♂",
    "Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇",
    "Aries":"♈","Taurus":"♉","Gemini":"♊","Cancer":"♋","Leo":"♌","Virgo":"♍",
    "Libra":"♎","Scorpio":"♏","Sagittarius":"♐","Capricorn":"♑","Aquarius":"♒","Pisces":"♓",
    "Conjunction":"☌","Opposition":"☍","Trine":"△","Square":"□","Sextile":"⚹",
    "AscNode":"☊","DescNode":"☋","Ascnode":"☊","Descnode":"☋","Retrograde":"℞",
    "Ascendant":"Asc","Fortune":"⊗",
}

def strip_balanced(s, cmd):
    """Elimina \\cmd{...} (y un [..] opcional siguiente) manejando llaves anidadas."""
    out = []; i = 0; token = "\\"+cmd
    while i < len(s):
        if s.startswith(token, i) and (i+len(token)==len(s) or not s[i+len(token)].isalpha()):
            j = i + len(token)
            while j < len(s) and s[j] in " \t": j += 1
            if j < len(s) and s[j] == "{":
                depth = 0
                while j < len(s):
                    if s[j] == "{": depth += 1
                    elif s[j] == "}":
                        depth -= 1
                        if depth == 0: j += 1; break
                    j += 1
                while j < len(s) and s[j] in " \t": j += 1
                if j < len(s) and s[j] == "[":
                    while j < len(s) and s[j] != "]": j += 1
                    if j < len(s): j += 1
                i = j; continue
        out.append(s[i]); i += 1
    return "".join(out)

def preprocess(tex, imgdir):
    # símbolos: \Sun\xspace , \Sun\, , \Sun{} , \Sun<no-alpha>
    for name, ch in SYM.items():
        tex = re.sub(r"\\"+name+r"(?:\\xspace|\\,|\\ |\{\})?(?![A-Za-z])", ch, tex)
    # figuras: \includegraphics[..]{DIR/NAME} -> imgdir/NAME.png (cualquier subcarpeta:
    # charts/, diagrams/…; tolera espacios y saltos de línea dentro de las llaves)
    def _img(m):
        name = m.group(1).strip().split("/")[-1]                 # basename
        name = re.sub(r"\.(pdf|png|eps|jpe?g)$", "", name, flags=re.I)  # quita extensión
        return r"\includegraphics{"+imgdir+"/"+name+r".png}"
    tex = re.sub(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{\s*([^}]+?)\s*\}", _img, tex)
    # envoltorios de figura que pandoc no entiende (dejar el includegraphics dentro)
    tex = re.sub(r"\\begin\{wrapfigure\}(\[[^\]]*\])?\{[^}]*\}\{[^}]*\}", "", tex)
    tex = re.sub(r"\\end\{wrapfigure\}", "", tex)
    tex = re.sub(r"\\begin\{(figure|center)\}(\[[^\]]*\])?", "", tex)
    tex = re.sub(r"\\end\{(figure|center)\}", "", tex)
    tex = re.sub(r"\\centering\b", "", tex)
    # highlight: desenvolver (mantener el contenido)
    tex = re.sub(r"\\hl\{([^{}]*)\}", r"\1", tex)
    # borrar comandos de maquetación con argumento balanceado (incl. notas al margen)
    for cmd in ("index","marginnote","mn","label","caption","captionsetup"):
        tex = strip_balanced(tex, cmd)
    # reglas de tabla que pandoc no necesita (dejan celdas basura tipo "2-4")
    tex = re.sub(r"\\(Xhline|cline)\{[^}]*\}", "", tex)
    tex = re.sub(r"\\approx\b", "≈", tex)
    # símbolo de sección  \S{8.6} / \S6.6 -> §…
    tex = re.sub(r"\\S\{([^}]*)\}", r"§\1", tex)
    tex = re.sub(r"\\S(?![A-Za-z{])", "§", tex)
    tex = re.sub(r"\\deg\b", "°", tex)
    # comandos sueltos sin argumento (notas al margen abreviadas, separadores)
    tex = re.sub(r"\\(secbr|starbreak|partialsecbr|mndl|mnbm|mnmb|mned|mnt|mnm)\b", "", tex)
    tex = re.sub(r"\\xspace\b", " ", tex)
    tex = re.sub(r"\\newpage\b|\\clearpage\b|\\cleardoublepage\b", "", tex)
    return tex

def expand_inputs(bookfile, root):
    """Devuelve el .tex del maestro con los \\input{...} expandidos en orden."""
    text = bookfile.read_text(encoding="utf-8", errors="replace")
    missing = []
    def repl(m):
        rel = m.group(1).strip()
        p = (root/rel)
        if p.suffix != ".tex": p = p.with_suffix(".tex")
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
        # Un \input que no resuelve descartaba SILENCIOSAMENTE un capítulo entero.
        # Registrarlo y avisar: casi siempre es --root mal puesto o un typo de ruta.
        missing.append(rel)
        return ""
    for _ in range(3):                       # \input no anidan hondo aquí
        new = re.sub(r"\\input\{([^}]+)\}", repl, text)
        if new == text: break
        text = new
    if missing:
        uniq = list(dict.fromkeys(missing))
        sys.stderr.write(
            f"AVISO: {len(uniq)} \\input NO resuelto(s) — se DESCARTAN (posible "
            f"pérdida de capítulos). Revisa --root='{root}':\n")
        for rel in uniq:
            sys.stderr.write(f"  - {rel}\n")
    return text

def main():
    ap = argparse.ArgumentParser(description="LaTeX (maestro con \\input) -> markdown de estudio")
    ap.add_argument("book", help="archivo maestro .tex (con los \\input de secciones)")
    ap.add_argument("--root", required=True, help="carpeta donde resolver los \\input")
    ap.add_argument("--out", required=True, help="archivo .md de salida")
    ap.add_argument("--imgdir", default="imagenes/charts",
                    help="ruta (relativa al .md) de las PNG de figuras (def: imagenes/charts)")
    a = ap.parse_args()
    tex = preprocess(expand_inputs(pathlib.Path(a.book), pathlib.Path(a.root)), a.imgdir)
    doc = "\\documentclass{article}\\begin{document}\n"+tex+"\n\\end{document}\n"
    r = subprocess.run(["pandoc","-f","latex","-t","gfm","--wrap=none"],
                       input=doc, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[:2000]); sys.exit(1)
    md = r.stdout
    for esc, rep in ((r"\[","["),(r"\]","]"),(r"\<","<"),(r"\>",">")):
        md = md.replace(esc, rep)     # des-escapar <...>/[...] de restitución del traductor
    md = re.sub(r"\n{3,}", "\n\n", md).strip()+"\n"
    pathlib.Path(a.out).write_text(md, encoding="utf-8")
    print(f"  {a.out}: {len(md.split())} palabras, {md.count(chr(10)+'#')} encabezados, "
          f"{md.count('![')} imágenes")

if __name__ == "__main__":
    main()
