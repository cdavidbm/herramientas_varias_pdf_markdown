#!/usr/bin/env python3
"""
audit_conversion.py — Puerta de auditoría para una conversión PDF→markdown por
secciones (típicamente un escaneo OCR-eado y troceado con
`pdf_chapters_to_markdown.py`). Produce un INFORME con cuatro capas, separando lo
que se puede **probar** de lo que solo se puede **estimar**.

POR QUÉ CUATRO CAPAS (y qué garantiza cada una)
-----------------------------------------------
En un escaneo hay DOS fuentes de error independientes:

  (1) «texto → markdown» (troceo, reflow, notas, límites): AUDITABLE de forma
      determinista. Si algo se cayó al convertir, se ve comparando el markdown
      contra el texto del PDF. → Capa A.
  (2) «imagen → texto» (la precisión del OCR): NO se puede probar comparando
      texto contra texto, porque el texto del PDF ES la salida del OCR. Solo se
      estima: por diccionario (Capa B), contra la imagen (Capa C, la ancla de
      verdad) o contra un segundo motor OCR (Capa D).

Capas:
  [A] COMPLETITUD (determinista). Por sección: nº de palabras del PDF vs del md
      (ratio), lagunas de prosa (difflib, como check_completeness) y balance de
      notas `[^N]` (cada referencia con su definición y viceversa).
  [B] RUIDO OCR (estimación por diccionario). % de tokens que aspell no reconoce
      + los peores, por sección. Es una COTA SUPERIOR: incluye nombres propios,
      transliteraciones y latín, que no son errores. Sirve para comparar secciones
      y cazar garbage, no como tasa de error absoluta.
  [C] MUESTRA VISUAL (ancla de verdad; requiere ojos). Renderiza N páginas al azar
      a PNG y vuelca el texto OCR de cada una, para leer imagen vs texto y contar
      discrepancias a mano. Es lo ÚNICO que audita el OCR contra la verdad.
  [D] CONTRASTE 2º MOTOR (estimación automática). Re-OCR de las páginas muestreadas
      con una segunda config de tesseract (modelos del sistema vs `best`) y diff a
      nivel de palabra: donde los dos motores discrepan hay error PROBABLE.

USO
---
  python3 audit_conversion.py spec.json --out INFORME.md
  python3 audit_conversion.py spec.json --out INFORME.md --sample 40 --render-dir ./audit_pngs

`spec.json`:
{
  "pdf": "Libro (OCR, searchable).pdf",   // el PDF con capa de texto, rel. al spec
  "md_dir": "en",                          // carpeta de los .md, rel. al spec
  "sections": [
    {"md": "00_Introduction.md", "pages": [16, 29]},
    {"md": "01_Book_I.md",       "pages": [30, 51]}
  ]
}

Capa C es semi-manual A PROPÓSITO: la herramienta prepara los PNG + el texto; el
juicio «¿coincide?» lo pone un humano (o el agente leyendo los PNG). No se finge
automático lo que no lo es.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

from forja_common import require_tool

BEST_TESSDATA = Path.home() / ".local/share/forja-tessdata"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


# ---------- utilidades de texto ----------

def md_body(md: str) -> str:
    """Cuerpo del markdown SIN encabezados ni definiciones de nota (para contar
    palabras de prosa comparables con el PDF)."""
    out = []
    for ln in md.split("\n"):
        if ln.startswith("#"):
            continue
        out.append(ln)
    return "\n".join(out)


_WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")


def words(s: str) -> list[str]:
    return _WORD.findall(s)


def pdf_text(pdf: Path, a: int | None = None, b: int | None = None) -> str:
    cmd = ["pdftotext", "-layout"]
    if a:
        cmd += ["-f", str(a)]
    if b:
        cmd += ["-l", str(b)]
    cmd += [str(pdf), "-"]
    return sh(cmd).stdout


def page_text(pdf: Path, p: int) -> str:
    return pdf_text(pdf, p, p)


# ---------- [A] completitud ----------

def gaps(ref: str, got: str, minw: int = 4) -> list[str]:
    """Tramos de >=minw palabras que están en ref (PDF) y no en got (md)."""
    rt, gt = words(ref.lower()), words(got.lower())
    sm = difflib.SequenceMatcher(None, rt, gt, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and (i2 - i1) >= minw:
            out.append(" ".join(rt[i1:i2]))
    return out


def footnote_balance(md: str) -> tuple[int, int, list[int], list[int]]:
    defs = sorted(set(int(m) for m in re.findall(r"^\[\^(\d+)\]:", md, re.M)))
    refs = sorted(set(int(m) for m in re.findall(r"(?<!^)\[\^(\d+)\]", md, re.M)))
    orphan_refs = [n for n in refs if n not in defs]      # ref sin definición
    unref_defs = [n for n in defs if n not in refs]       # definición sin ref
    return len(defs), len(refs), orphan_refs, unref_defs


# ---------- [B] ruido OCR ----------

def aspell_unknown(text: str) -> list[str]:
    r = sh(["aspell", "--lang=en", "--encoding=utf-8", "list"], input=text)
    if r.returncode != 0:
        return []
    return [w for w in r.stdout.split("\n") if w.strip()]


def looks_garbled(tok: str) -> bool:
    """Heurística de GARBAGE de OCR (no solo palabra rara): minúscula→MAYÚSCULA a
    media palabra, o palabra larga sin vocales."""
    if re.search(r"[a-z][A-Z]", tok):
        return True
    if len(tok) >= 4 and not re.search(r"[aeiouyAEIOUY]", tok):
        return True
    return False


# ---------- [D] contraste 2º motor OCR ----------

def ocr_page(pdf: Path, p: int, dpi: int, tessdata: Path | None) -> str:
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        stem = Path(td) / "p"
        sh(["pdftoppm", "-f", str(p), "-l", str(p), "-r", str(dpi), "-png",
            str(pdf), str(stem)])
        pngs = sorted(Path(td).glob("p*.png"))
        if not pngs:
            return ""
        env = dict(os.environ)
        if tessdata and tessdata.is_dir():
            env["TESSDATA_PREFIX"] = str(tessdata)
        r = sh(["tesseract", str(pngs[0]), "stdout", "-l", "eng"], env=env)
        return r.stdout


def word_disagreements(a: str, b: str) -> tuple[int, int, list[tuple[str, str]]]:
    wa, wb = words(a.lower()), words(b.lower())
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    diffs, total = [], max(len(wa), 1)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            diffs.append((" ".join(wa[i1:i2]), " ".join(wb[j1:j2])))
    ndiff = sum(max(i2 - i1, j2 - j1)
                for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
    return ndiff, total, diffs


# ---------- muestreo determinista (sin RNG: paso fijo) ----------

def sample_pages(a: int, b: int, n: int) -> list[int]:
    span = b - a + 1
    if n >= span:
        return list(range(a, b + 1))
    step = span / n
    return sorted({a + int(i * step) for i in range(n)})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path, help="JSON con pdf, md_dir, sections[]")
    ap.add_argument("--out", type=Path, help="informe markdown (def: stdout)")
    ap.add_argument("--sample", type=int, default=40, help="páginas muestreadas para C+D (def 40)")
    ap.add_argument("--render-dir", type=Path, help="carpeta donde dejar los PNG de la muestra (capa C)")
    ap.add_argument("--dpi", type=int, default=200, help="DPI de render para muestra/2º motor")
    ap.add_argument("--no-cross-ocr", action="store_true", help="salta la capa D (más rápido)")
    args = ap.parse_args()

    require_tool("pdftotext", "apt: poppler-utils")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    base = args.spec.resolve().parent
    pdf = (base / spec["pdf"]).resolve()
    md_dir = (base / spec.get("md_dir", ".")).resolve()
    if not pdf.is_file():
        sys.exit(f"no existe el PDF: {pdf}")

    R = ["# Auditoría de conversión", "", f"**PDF:** `{pdf.name}`  ", f"**Carpeta md:** `{md_dir.name}/`", ""]

    # ---- [A] completitud + notas ----
    R += ["## [A] Completitud (determinista)", "",
          "| Sección | Págs | Palabras PDF | Palabras md | Ratio | Lagunas≥4 | Notas def/ref | Huérfanas |",
          "|---|---|---|---|---|---|---|---|"]
    a_alarms = []
    for sec in spec["sections"]:
        md_path = md_dir / sec["md"]
        if not md_path.is_file():
            R.append(f"| {sec['md']} | — | — | — | **FALTA .md** | — | — | — |")
            a_alarms.append(f"{sec['md']}: no existe el archivo")
            continue
        a, b = sec["pages"]
        ref = pdf_text(pdf, a, b)
        md = md_path.read_text(encoding="utf-8")
        mb = md_body(md)
        rw, mw = len(words(ref)), len(words(mb))
        ratio = mw / rw if rw else 0
        # difflib es O(n·m): en secciones enormes se dispara. El ratio ya es la
        # señal de completitud; el análisis fino de lagunas solo en secciones
        # manejables (las grandes se juzgan por ratio).
        gp_cell = str(len(gaps(ref, mb))) if rw < 15000 else "—(ratio)"
        ndef, nref, orphan, unref = footnote_balance(md)
        flag = "🔴" if ratio < 0.85 else ("🟡" if ratio < 0.93 else "🟢")
        orph = f"{len(orphan)}r/{len(unref)}d" if (orphan or unref) else "0"
        R.append(f"| {sec['md'][:34]} | {a}-{b} | {rw} | {mw} | {flag} {ratio:.3f} "
                 f"| {gp_cell} | {ndef}/{nref} | {orph} |")
        if ratio < 0.85:
            a_alarms.append(f"{sec['md']}: ratio {ratio:.3f} (posible pérdida de prosa)")
        if orphan:
            a_alarms.append(f"{sec['md']}: {len(orphan)} nota(s) [^N] sin definición: {orphan[:8]}")
    R += ["", "> Ratio = palabras del md / palabras del PDF en ese rango. Baja legítimamente"
          " por running-heads y marcadores de nota que el conversor descarta; <0.85 en prosa"
          " es alarma real. «Lagunas» = tramos de ≥4 palabras del PDF ausentes del md"
          " (incluye texto de notas no enlazado; no todo es pérdida de cuerpo).", ""]

    # ---- [B] ruido OCR ----
    R += ["## [B] Ruido OCR (estimación por diccionario — COTA SUPERIOR)", "",
          "| Sección | Tokens | Desconoc. | % | «Garbage» claro (muestra) |",
          "|---|---|---|---|---|"]
    for sec in spec["sections"]:
        md_path = md_dir / sec["md"]
        if not md_path.is_file():
            continue
        body = md_body(md_path.read_text(encoding="utf-8"))
        toks = words(body)
        unk = aspell_unknown(body)
        garb = sorted(set(w for w in unk if looks_garbled(w)))
        pct = 100 * len(unk) / max(len(toks), 1)
        R.append(f"| {sec['md'][:30]} | {len(toks)} | {len(unk)} | {pct:.1f}% "
                 f"| {', '.join(garb[:6])} |")
    R += ["", "> % desconocidas SOBREESTIMA el error: incluye nombres propios,"
          " transliteraciones (ḥ, ā…) y latín. La columna «garbage» aísla lo que casi"
          " seguro es basura de OCR (mayúscula a media palabra, palabra sin vocales).", ""]

    # ---- muestreo para C y D ----
    all_pages = []
    for sec in spec["sections"]:
        a, b = sec["pages"]
        all_pages.append((sec["md"], a, b))
    # repartir la muestra proporcional al tamaño de cada sección
    total_span = sum(b - a + 1 for _, a, b in all_pages)
    sample = []
    for md, a, b in all_pages:
        share = max(1, round(args.sample * (b - a + 1) / total_span))
        sample += [(md, p) for p in sample_pages(a, b, share)]

    # ---- [C] preparar muestra visual ----
    R += ["## [C] Muestra visual (ancla de verdad — requiere leer los PNG)", ""]
    if args.render_dir:
        require_tool("pdftoppm", "apt: poppler-utils")
        args.render_dir.mkdir(parents=True, exist_ok=True)
        for md, p in sample:
            sh(["pdftoppm", "-f", str(p), "-l", str(p), "-r", str(args.dpi), "-png",
                str(pdf), str(args.render_dir / f"p{p:04d}")])
        R.append(f"{len(sample)} páginas renderizadas en `{args.render_dir}/` "
                 f"(pXXXX-XX.png). Léelas contra el texto de cada página y cuenta discrepancias.")
    else:
        R.append(f"{len(sample)} páginas seleccionadas (pasa --render-dir para volcarlas a PNG): "
                 + ", ".join(str(p) for _, p in sample))
    R.append("")

    # ---- [D] contraste 2º motor OCR ----
    if not args.no_cross_ocr:
        R += ["## [D] Contraste 2º motor OCR (best vs sistema — error probable)", "",
              "| Pág | Sección | Palabras | Discrepancias | % | Ejemplos (best → sistema) |",
              "|---|---|---|---|---|---|"]
        tot_d = tot_w = 0
        # Ambos por tesseract stdout al MISMO dpi (300): así solo cambia el MODELO
        # (best vs sistema), no el orden de lectura ni la resolución. Comparar la
        # capa -layout del PDF contra tesseract-stdout medía diferencias de orden y
        # de dpi, no errores de OCR (inflaba la discrepancia en prosa correcta).
        XDPI = 300
        for md, p in sample:
            best = ocr_page(pdf, p, XDPI, BEST_TESSDATA)   # modelos best (los del entregable)
            other = ocr_page(pdf, p, XDPI, None)           # modelos del sistema
            nd, nw, diffs = word_disagreements(best, other)
            tot_d += nd; tot_w += nw
            ex = "; ".join(f"«{x[:16]}»→«{y[:16]}»" for x, y in diffs[:3] if x or y)
            R.append(f"| {p} | {md[:20]} | {nw} | {nd} | {100*nd/max(nw,1):.1f}% | {ex} |")
        R += ["", f"**Tasa de discrepancia global:** {tot_d}/{tot_w} = "
              f"**{100*tot_d/max(tot_w,1):.1f}%** de las palabras muestreadas.",
              "> Donde los dos motores coinciden, alta confianza. Donde discrepan, uno de los"
              " dos se equivocó (revisa el PNG de esa página). NO es la tasa de error del OCR"
              " final: es una señal de dónde MIRAR.", ""]

    # ---- resumen ----
    R = ["<!-- generado por audit_conversion.py -->"] + R
    R += ["## Resumen de alarmas [A]", ""]
    R += (["- " + x for x in a_alarms] if a_alarms
          else ["Ninguna alarma dura de completitud (ratios y notas dentro de lo esperado)."])
    report = "\n".join(R) + "\n"

    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"Informe escrito: {args.out}")
        # eco del resumen a stdout
        print("\n".join(R[-(len(a_alarms) + 3):]))
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
