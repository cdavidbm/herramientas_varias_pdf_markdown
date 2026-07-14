#!/usr/bin/env python3
"""astro_chart.py — Dibuja una **carta astral de signos enteros** (whole-sign, estilo
helenístico) como las de las ediciones LaTeX de Valens/Doroteo: rueda TikZ con la banda
zodiacal, los glifos de signo (fuente `starfont`), los números de casa 1–12, la flecha
del Ascendente y los planetas colocados por su longitud, con las Suertes opcionales.

Dos modos:
  • **Fase 1 — posiciones dadas** (por defecto): tú das el Ascendente y las longitudes.
  • **Fase 2 — cálculo** (`--birth`): calcula posiciones con la **Efeméride Suiza**
    (paquete `pyswisseph`; si falta:  pip install pyswisseph).

Las posiciones se dan como longitud absoluta 0–360 (0 = 0° Aries) **o** «Signo grado»,
p. ej. «Libra 18», «Piscis 6 50», «Piscis 6°50'», «♎ 18», «Vir 15.5». Nombres ES/EN.

Convención (marco único, no la de janegca): el signo del Ascendente ocupa el sector
izquierdo (casa I), las casas crecen en sentido antihorario y todo —cúspides, glifos,
planetas, Asc— se sitúa con  pantalla(λ) = 180 + (λ − medio_del_signo_Asc).

Uso (Fase 1):
    python3 astro_chart.py carta.pdf --spec carta.json [--png] [--scale 3.5]
    python3 astro_chart.py carta.pdf --asc "Libra 18" \\
        --planet Sol="Piscis 6 50" --planet Luna="Libra 18" --lot Fortuna="Escorpio 12" \\
        --title "Ejemplo" --png
    python3 astro_chart.py demo.pdf  --demo --png
Uso (Fase 2):
    python3 astro_chart.py carta.pdf --birth "1990-05-12 14:30" --lat 4.61 --lon -74.08 --tz -5

`--spec carta.json`:
    { "title": "...", "asc": "Libra 18", "mc": "Cancer 18",
      "planets": {"Sun":"Pisces 6 50", "Moon":"Libra 18", ...},
      "lots": {"Fortune":"Scorpio 12"} }

Requiere TeX Live con starfont, wasysym, tikz (motor lualatex). Ver README de La Forja.
"""
import argparse, json, pathlib, subprocess, sys, tempfile, shutil, re

# --- signos: índice 0..11 desde Aries (nombres ES/EN, abreviaturas y glifos) ---
SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
         "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
_SIGN_NAMES = {
    0:["aries","ari","ar","♈"], 1:["taurus","tauro","tau","ta","♉"],
    2:["gemini","géminis","geminis","gem","ge","♊"], 3:["cancer","cáncer","can","cnc","cn","♋"],
    4:["leo","le","♌"], 5:["virgo","vir","vg","vi","♍"],
    6:["libra","lib","li","♎"], 7:["scorpio","escorpio","escorpión","escorpion","sco","sc","♏"],
    8:["sagittarius","sagitario","sag","sa","♐"], 9:["capricorn","capricornio","cap","cp","♑"],
    10:["aquarius","acuario","aqu","aq","♒"], 11:["pisces","piscis","pis","pi","♓"],
}
SIGN_ALIASES = {a: i for i, al in _SIGN_NAMES.items() for a in al}
# --- planetas/puntos -> comando starfont ---
_PLANET_NAMES = {
    "Sun":["sun","sol","☉"], "Moon":["moon","luna","☽"],
    "Mercury":["mercury","mercurio","☿"], "Venus":["venus","♀"],
    "Mars":["mars","marte","♂"], "Jupiter":["jupiter","júpiter","♃"],
    "Saturn":["saturn","saturno","♄"], "Uranus":["uranus","urano","♅"],
    "Neptune":["neptune","neptuno","♆"], "Pluto":["pluto","plutón","pluton","♇"],
    "Ascnode":["node","nodo","northnode","nodonorte","☊"], "Descnode":["southnode","nodosur","☋"],
}
PLANET_CMD = {a: k for k, al in _PLANET_NAMES.items() for a in al}

def parse_lon(s):
    """'Libra 18' | 'Pisces 6 50' | 'Pisces 6°50'' | 198.3 -> longitud eclíptica 0..360."""
    if isinstance(s, (int, float)):
        return float(s) % 360.0
    s = str(s).strip()
    try:
        return float(s) % 360.0
    except ValueError:
        pass
    parts = s.replace("°", " ").replace("'", " ").replace("´", " ").split()
    key = parts[0].lower()
    if key not in SIGN_ALIASES:
        sys.exit(f"Signo no reconocido: {parts[0]!r}")
    base = SIGN_ALIASES[key] * 30.0
    deg = float(parts[1]) if len(parts) > 1 else 0.0
    minutes = float(parts[2]) if len(parts) > 2 else 0.0
    return (base + deg + minutes / 60.0) % 360.0

def deg_label(lon):
    """Grado dentro del signo -> '6°50' / '18°'."""
    within = lon % 30.0
    d = int(within); m = round((within - d) * 60)
    if m == 60: d += 1; m = 0
    return f"{d}°{m:02d}'" if m else f"{d}°"

PREAMBLE = r"""\documentclass[border=4pt]{standalone}
\usepackage{wasysym}
\usepackage{starfont}
\usepackage{tikz}
\usetikzlibrary{backgrounds, calc, quotes}
\starfontsans
\tikzset{
  pics/fortune/.style ={ code={
    \node (lot) [draw, circle, thick, scale=0.9] {};
    \draw [thick] (lot.north east) -- (lot.south west)
                  (lot.north west) -- (lot.south east);}},
  pics/spirit/.style ={ code={
    \node (lot) [draw, circle, thick, scale=0.9] {};
    \draw [very thick] ([yshift=0.04cm]lot.north) -- ([yshift=-0.04cm]lot.south);}},
  pics/lot/.style = { code={\node [draw, circle, thick, font=\bfseries, scale=0.5]
                            {\textbf{\textsl{#1}}};}},
}
\begin{document}
"""

def build_tex(spec, scale):
    asc = parse_lon(spec["asc"])
    asc_sign = int(asc // 30)
    asc_mid = asc_sign * 30 + 15                 # medio del signo del Asc
    screen = lambda lon: (180 + (lon - asc_mid)) % 360   # marco único

    L = [PREAMBLE, f"\\begin{{tikzpicture}}[scale={scale}]"]
    # anillo
    L.append(r"\draw (0,0) circle(1.05);")
    L.append(r"\draw (0,0) circle(0.85);")
    cusps = ",".join(str((15 + 30*j) % 360) for j in range(12))
    L.append(r"\foreach \x in {%s} { \draw[gray] (0,0) -- (\x:1.05); }" % cusps)
    L.append(r"\fill[white] (0,0) circle(0.15);")
    L.append(r"\draw (0,0) circle(0.15);")
    L.append(r"\draw (0,0) circle(0.25);")
    # glifos de signo (centro de cada sector) + números de casa (interior)
    for h in range(12):
        s = (asc_sign + h) % 12
        ang = screen(s*30 + 15)
        L.append(r"\node at (%.2f:0.95) {\%s};" % (ang, SIGNS[s]))
        L.append(r"\node at (%.2f:0.20) {\tiny %d};" % (ang, h + 1))
    # eje Asc-Desc (flecha roja) y MC opcional
    a = screen(asc)                               # flecha del IC->Asc, etiqueta SOBRE el Asc
    L.append(r"\draw[->, red] (%.2f:1.05) -- (%.2f:1.05) node[anchor=%s]{\tiny Asc\,%s};"
             % ((a + 180) % 360, a, "east" if 90 < a < 270 else "west", deg_label(asc)))
    if spec.get("mc"):
        mc = parse_lon(spec["mc"]); mca = screen(mc)
        L.append(r"\draw[->, blue] (%.2f:1.05) -- (%.2f:1.05) node[anchor=%s]{\tiny MC\,%s};"
                 % ((mca + 180) % 360, mca, "south" if mca < 180 else "north", deg_label(mc)))
    # planetas (con des-solapado radial simple)
    pl = []
    for name, pos in spec.get("planets", {}).items():
        cmd = PLANET_CMD.get(str(name).lower())
        if not cmd: sys.exit(f"Planeta no reconocido: {name!r}")
        lon = parse_lon(pos); pl.append((screen(lon), cmd, deg_label(lon)))
    pl.sort()
    LEVELS = [0.74, 0.62, 0.50]                   # radios para des-solapar cúmulos (stelliums)
    radii, last, lvl = [], None, 0
    for ang, _, _ in pl:
        lvl = (lvl + 1) % len(LEVELS) if (last is not None and (ang - last) < 13) else 0
        radii.append(LEVELS[lvl]); last = ang
    for (ang, cmd, lab), r in zip(pl, radii):
        L.append(r"\node at (%.2f:%.2f) {\%s\,\tiny{%s}};" % (ang, r, cmd, lab))
    # suertes
    for name, pos in spec.get("lots", {}).items():
        ang = screen(parse_lon(pos)); key = str(name).lower()
        pic = "fortune" if key in ("fortune","fortuna") else \
              "spirit" if key in ("spirit","daimon","daímon","espíritu") else None
        if pic:
            L.append(r"\pic at (%.2f:0.45) {%s};" % (ang, pic))
        else:
            L.append(r"\pic at (%.2f:0.45) {lot=%s};" % (ang, str(name)[:1].upper()))
    if spec.get("title"):
        L.append(r"\node[font=\scshape] at (0,-1.3) {%s};" % spec["title"])
    L.append(r"\end{tikzpicture}")
    L.append(r"\end{document}")
    return "\n".join(L)

def compute_birth(date, time, lat, lon, tz):
    """Fase 2: posiciones (planetas, Asc, MC, Suerte de Fortuna) desde datos de nacimiento."""
    if lat is None or lon is None:
        sys.exit("Con --birth hacen falta --lat y --lon.")
    try:
        import swisseph as swe
    except ImportError:
        sys.exit("Falta pyswisseph. Instala:  pip install pyswisseph")
    y, mo, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in time.split(":"))
    jd = swe.julday(y, mo, d, hh + mm/60.0 - tz)           # a Tiempo Universal
    spec = {"planets": {}}
    for name, pl in [("Sun",swe.SUN),("Moon",swe.MOON),("Mercury",swe.MERCURY),
                     ("Venus",swe.VENUS),("Mars",swe.MARS),("Jupiter",swe.JUPITER),
                     ("Saturn",swe.SATURN),("Uranus",swe.URANUS),("Neptune",swe.NEPTUNE),
                     ("Pluto",swe.PLUTO),("node",swe.TRUE_NODE)]:
        spec["planets"][name] = swe.calc_ut(jd, pl)[0][0]
    _, ascmc = swe.houses(jd, lat, lon, b"W")              # W = signos enteros
    spec["asc"] = ascmc[0]; spec["mc"] = ascmc[1]
    sun, moon = spec["planets"]["Sun"], spec["planets"]["Moon"]
    day = ((sun - ascmc[0]) % 360) >= 180                  # Sol sobre el horizonte
    spec["lots"] = {"Fortune": (ascmc[0] + (moon - sun if day else sun - moon)) % 360}
    return spec

DEMO = {   # Doroteo, Libro III.1, primera carta de ejemplo (valida contra charts/3_1_01)
    "title": "Doroteo III.1 (validación)",
    "asc": "Libra 18",
    "planets": {"Sun":"Pisces 6 50","Mercury":"Pisces 19 55","Moon":"Libra 18",
                "Venus":"Pisces 26 50","Saturn":"Aries 4 34","Jupiter":"Scorpio 20 10",
                "Mars":"Taurus 24 55"},
    "lots": {"Fortune":"Scorpio 12"},
}

def main():
    ap = argparse.ArgumentParser(description="Carta astral de signos enteros (TikZ -> PDF/PNG)")
    ap.add_argument("out", help="PDF de salida")
    ap.add_argument("--spec", help="JSON con asc/planets/lots (ver docstring)")
    ap.add_argument("--demo", action="store_true", help="carta de validación de Doroteo III.1")
    ap.add_argument("--asc", help="Ascendente, p.ej. \"Libra 18\" o 198")
    ap.add_argument("--planet", action="append", default=[], metavar="NOMBRE=POS",
                    help="planeta y posición (repetible), p.ej. --planet Sol=\"Piscis 6 50\"")
    ap.add_argument("--lot", action="append", default=[], metavar="NOMBRE=POS", help="Suerte (repetible)")
    ap.add_argument("--mc", help="Medio Cielo (opcional)")
    ap.add_argument("--title", default="", help="título bajo la carta")
    ap.add_argument("--birth", help="Fase 2: \"YYYY-MM-DD HH:MM\" (hora local)")
    ap.add_argument("--lat", type=float, help="latitud (grados, N+)")
    ap.add_argument("--lon", type=float, help="longitud (grados, E+)")
    ap.add_argument("--tz", type=float, default=0.0, help="huso horario respecto a UTC (h)")
    ap.add_argument("--scale", type=float, default=3.5, help="escala TikZ (def 3.5)")
    ap.add_argument("--png", action="store_true", help="además, exportar PNG (pdftoppm 200dpi)")
    ap.add_argument("--keep-tex", action="store_true", help="conservar el .tex junto al PDF")
    a = ap.parse_args()

    if a.birth:
        date, time = a.birth.split()
        spec = compute_birth(date, time, a.lat, a.lon, a.tz)
    elif a.demo:
        spec = dict(DEMO)
    elif a.spec:
        spec = json.loads(pathlib.Path(a.spec).read_text(encoding="utf-8"))
    else:
        spec = {"planets": {}, "lots": {}}
    if a.asc: spec["asc"] = a.asc
    if a.mc: spec["mc"] = a.mc
    if a.title: spec["title"] = a.title
    for kv in a.planet:
        k, v = kv.split("=", 1); spec.setdefault("planets", {})[k] = v
    for kv in a.lot:
        k, v = kv.split("=", 1); spec.setdefault("lots", {})[k] = v
    if "asc" not in spec:
        sys.exit("Falta el Ascendente (--asc, --spec, --demo o --birth).")

    tex = build_tex(spec, a.scale)
    out = pathlib.Path(a.out).resolve()
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        tf = td / (out.stem + ".tex"); tf.write_text(tex, encoding="utf-8")
        for _ in (1, 2):
            r = subprocess.run(["lualatex", "-interaction=nonstopmode", tf.name],
                               cwd=td, capture_output=True, text=True, timeout=120)
        pdf = td / (out.stem + ".pdf")
        if not pdf.exists():
            errs = "\n".join(l for l in r.stdout.splitlines() if l.startswith("!"))
            sys.stderr.write("lualatex no produjo PDF:\n" + (errs or r.stdout[-1500:]) + "\n")
            if a.keep_tex: shutil.copy(tf, out.with_suffix(".tex"))
            sys.exit(1)
        shutil.copy(pdf, out)
        if a.keep_tex: shutil.copy(tf, out.with_suffix(".tex"))
        if a.png:
            subprocess.run(["pdftoppm","-png","-r","200","-singlefile",str(out),
                            str(out.with_suffix(""))], check=True)
    print(f"  {out.name}" + ("  (+ PNG)" if a.png else ""))

if __name__ == "__main__":
    main()
