#!/usr/bin/env python3
"""
agy_transcribe.py — Orquesta la TRANSCRIPCIÓN VISUAL de un rango de páginas de un
PDF a markdown de alto formato usando agy/Gemini (Antigravity CLI), de punta a punta:

  render → agy por lotes (con reintento) → centinela tesseract → consolidar → figuras

Pensado para libros escaneados nítidos donde importan cursivas, diacríticos, notas al
pie y tablas/figuras: agy/Gemini transcribe cada página conservando todo eso (muy por
encima de tesseract), sobre la cuota plana de Gemini (0 tokens de otro proveedor). Este
script hace el andamiaje reproducible y REANUDABLE (salta lotes ya hechos).

Flujo:
  1. Rasteriza pág A..B a `WORKDIR/pages/pdfNNN.png` (200 dpi por defecto).
  2. Agrupa en lotes de `--batch` páginas y lanza `agy -p PROMPT` por lote, con hasta
     `--parallel` procesos a la vez. Verifica que el lote devolvió todas sus páginas;
     si faltan, lo REINTENTA una vez. Salida cruda a `WORKDIR/agy/bNN.out`.
  3. (--sentinel) tesseract *best* por página como 2º motor: informa páginas donde agy
     trae << palabras que tesseract (posible salto de contenido) para revisión visual.
  4. Consolida con `agy_consolidate.py` → `--out` (une frases partidas, reúne notas,
     da balance refs↔defs).
  5. (--figures-dir) recorta cada `[[FIGURE:…|bbox=…]]` con `crop_figure.py` (la página
     se conoce por el bloque de agy) y sustituye la línea por `![cap](RELPATH/figNNN.png)`.

Uso:
  python3 agy_transcribe.py FUENTE.pdf --pages 37-96 --out en/01_Book_I.md \
      --title "Book I: Signs and Houses" --prompt _work/TRANSCRIPTION_PROMPT.txt \
      --workdir _work --figures-dir figuras --fig-relpath ../figuras --sentinel

Requisitos: `agy` en PATH (o --agy-bin), poppler (pdftoppm), tesseract (si --sentinel),
y en el mismo tools/: agy_consolidate.py y crop_figure.py.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PAGE_RE = re.compile(r"^===\s*pdf0*(\d+)", re.M)
FIG_RE = re.compile(r"\[\[FIGURE:\s*(.+?)\s*\|\s*bbox=([0-9.,]+)\]\]")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def render_pages(pdf: Path, a: int, b: int, dpi: int, pages_dir: Path) -> None:
    pages_dir.mkdir(parents=True, exist_ok=True)
    for p in range(a, b + 1):
        out = pages_dir / f"pdf{p:03d}.png"
        if out.exists() and out.stat().st_size > 0:
            continue
        # pdftoppm añade sufijo; render a prefijo temporal y renombra
        pref = str(pages_dir / f"_tmp{p:03d}")
        r = sh(["pdftoppm", "-r", str(dpi), "-png", "-f", str(p), "-l", str(p), str(pdf), pref])
        if r.returncode != 0:
            sys.exit(f"pdftoppm falló en pág {p}: {r.stderr.strip()}")
        cand = sorted(pages_dir.glob(f"_tmp{p:03d}*.png"))
        if not cand:
            sys.exit(f"pdftoppm no produjo PNG para pág {p}")
        cand[0].rename(out)


def batches(a: int, b: int, size: int) -> list[list[int]]:
    pages = list(range(a, b + 1))
    return [pages[i:i + size] for i in range(0, len(pages), size)]


def agy_call(pages: list[int], prompt: str, pages_dir: Path, model: str, agy_bin: str) -> str:
    files = ", ".join(f"pdf{p:03d}.png" for p in pages)
    full = f"{prompt}\nFiles (in ./pages/): {files}"
    r = sh([agy_bin, "-p", full, "--model", model,
            "--add-dir", str(pages_dir), "--dangerously-skip-permissions"])
    return r.stdout


def split_blocks(text: str) -> dict[int, str]:
    """Divide la salida de agy en {nº_página: bloque completo con su cabecera}."""
    blocks, cur, buf = {}, None, []
    for ln in text.split("\n"):
        m = re.match(r"^===\s*pdf0*(\d+)", ln)
        if m:
            if cur is not None:
                blocks[cur] = "\n".join(buf)
            cur = int(m.group(1)); buf = [ln]
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        blocks[cur] = "\n".join(buf)
    return blocks


def run_batch(idx: int, pages: list[int], prompt: str, pages_dir: Path,
              agy_dir: Path, model: str, agy_bin: str) -> tuple[int, int, int]:
    """Corre agy en un lote; si trunca, transcribe página-a-página las que falten.

    Devuelve (idx, esperadas, obtenidas). Reanudable: salta si el fichero ya está completo.
    """
    out = agy_dir / f"b{idx:02d}.out"
    expected = len(pages)
    if out.exists():
        got = len(PAGE_RE.findall(out.read_text(encoding="utf-8", errors="replace")))
        if got == expected:
            return idx, expected, got
    # 1) intento como lote completo (2 veces)
    blocks: dict[int, str] = {}
    for _ in range(2):
        blocks = split_blocks(agy_call(pages, prompt, pages_dir, model, agy_bin))
        if all(p in blocks for p in pages):
            break
    # 2) auto-reparación: página-a-página para las que falten (una página rara vez trunca)
    missing = [p for p in pages if p not in blocks]
    for p in missing:
        b = split_blocks(agy_call([p], prompt, pages_dir, model, agy_bin))
        if p in b:
            blocks[p] = b[p]
    # 3) reensambla en orden de página
    text = "\n".join(blocks[p] for p in pages if p in blocks)
    out.write_text(text + "\n", encoding="utf-8")
    return idx, expected, len([p for p in pages if p in blocks])


def sentinel(a: int, b: int, pages_dir: Path, agy_dir: Path, tess_dir: Path) -> list[int]:
    tess_dir.mkdir(parents=True, exist_ok=True)
    # texto agy por página
    raw = ""
    for f in sorted(agy_dir.glob("b*.out")):
        raw += f.read_text(encoding="utf-8", errors="replace") + "\n"
    per = {}
    cur = None
    for ln in raw.split("\n"):
        m = re.match(r"^===\s*pdf0*(\d+)", ln)
        if m:
            cur = int(m.group(1)); per[cur] = []
        elif cur is not None:
            per[cur].append(ln)
    wc = lambda t: len(re.findall(r"[A-Za-zÀ-ÿ]+", t))
    flags = []
    for p in range(a, b + 1):
        img = pages_dir / f"pdf{p:03d}.png"
        tf = tess_dir / f"pdf{p:03d}"
        if not (tf.with_suffix(".txt")).exists():
            sh(["tesseract", str(img), str(tf), "-l", "eng", "--psm", "6"],
               env={**os.environ, "TESSDATA_PREFIX": os.path.expanduser("~/.local/share/forja-tessdata")})
        tt = (tf.with_suffix(".txt")).read_text(encoding="utf-8", errors="replace") if tf.with_suffix(".txt").exists() else ""
        at = wc("\n".join(per.get(p, [])))
        tw = wc(tt)
        if tw > 30 and at / tw < 0.85:
            flags.append(p)
    return flags


def page_file_map(agy_dir: Path) -> dict[int, Path]:
    """{nº_página: fichero b*.out que la contiene}."""
    m = {}
    for f in sorted(agy_dir.glob("b*.out")):
        for p in PAGE_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
            m[int(p)] = f
    return m


def missing_ref_pages(out_md: Path, agy_dir: Path) -> list[int]:
    """Páginas cuyas notas se perdieron por truncación (refs en el cuerpo sin def)."""
    md = out_md.read_text(encoding="utf-8")
    refs = set(int(x) for x in re.findall(r"\[\^(\d+)\](?!:)", md))
    defs = set(int(x) for x in re.findall(r"^\[\^(\d+)\]:", md, re.M))
    missing = refs - defs
    if not missing:
        return []
    pages = set()
    for f in sorted(agy_dir.glob("b*.out")):
        for pnum, block in split_blocks(f.read_text(encoding="utf-8", errors="replace")).items():
            body_refs = set(int(x) for x in re.findall(r"\[\^(\d+)\](?!:)", block))
            if body_refs & missing:
                pages.add(pnum)
    return sorted(pages)


CLAUDE_FALLBACK = "Claude Opus 4.6 (Thinking)"


def _ndefs(block: str) -> int:
    return len(re.findall(r"^\[\^\d+\]:", block, re.M))


def heal_truncated(pdf, agy_dir, out_md, prompt, pages_dir, title, model, fallback, agy_bin) -> list[int]:
    """Re-transcribe páginas truncadas (notas huérfanas) escalando de modelo y re-consolida.

    Escalera: bloque ACTUAL (no regresar un arreglo ya bueno) → modelo principal →
    respaldo → Claude (arquitectura distinta, salva páginas donde Gemini trunca por una
    ilustración). Se queda con el candidato con MÁS definiciones de nota. Devuelve las
    páginas que SIGUEN sin resolverse (para intervención manual).
    """
    pmap = page_file_map(agy_dir)
    pending = missing_ref_pages(out_md, agy_dir)
    if not pending:
        return []
    for p in pending:
        if p not in pmap:
            continue
        f = pmap[p]
        blocks = split_blocks(f.read_text(encoding="utf-8", errors="replace"))
        best = blocks.get(p, "")                       # nunca regresar lo que ya hay
        for mdl in (model, fallback, CLAUDE_FALLBACK):
            cand = split_blocks(agy_call([p], prompt, pages_dir, mdl, agy_bin)).get(p, "")
            if _ndefs(cand) > _ndefs(best):
                best = cand
        blocks[p] = best
        order = [int(x) for x in PAGE_RE.findall(f.read_text(encoding="utf-8", errors="replace"))]
        f.write_text("\n".join(blocks[q] for q in order if q in blocks) + "\n", encoding="utf-8")
    # re-consolida
    outs = [str(x) for x in sorted(agy_dir.glob("b*.out"))]
    cmd = ["python3", str(TOOLS / "agy_consolidate.py"), str(out_md), *outs]
    if title:
        cmd += ["--title", title]
    sh(cmd)
    return missing_ref_pages(out_md, agy_dir)


def do_figures(pdf: Path, agy_dir: Path, out_md: Path, figures_dir: Path,
               relpath: str, dpi: int) -> int:
    figures_dir.mkdir(parents=True, exist_ok=True)
    # (página, caption, bbox) desde los bloques por página
    figs = []
    for f in sorted(agy_dir.glob("b*.out")):
        cur = None
        for ln in f.read_text(encoding="utf-8", errors="replace").split("\n"):
            m = re.match(r"^===\s*pdf0*(\d+)", ln)
            if m:
                cur = int(m.group(1)); continue
            fm = FIG_RE.search(ln)
            if fm and cur:
                figs.append((cur, fm.group(1).strip(), fm.group(2).strip()))
    md = out_md.read_text(encoding="utf-8")
    n = 0
    for page, cap, bbox in figs:
        num = re.search(r"Figure\s+(\d+)", cap)
        name = f"fig{int(num.group(1)):03d}.png" if num else f"figpg{page:03d}_{n}.png"
        r = sh(["python3", str(TOOLS / "crop_figure.py"), str(pdf), "--page", str(page),
                "--bbox", bbox, "--pad", "0.012", "--dpi", str(dpi),
                "--out", str(figures_dir / name)])
        if r.returncode != 0:
            print(f"    ⚠ figura pág {page} no recortada: {r.stderr.strip()}")
            continue
        # sustituye la línea [[FIGURE …]] por el embed
        pat = re.compile(r"\[\[FIGURE:\s*" + re.escape(cap) + r"\s*\|\s*bbox=[0-9.,]+\]\]")
        md, k = pat.subn(f"![{cap}]({relpath}/{name})", md)
        n += k
    out_md.write_text(md, encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe un rango de páginas de PDF con agy/Gemini a markdown.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", required=True, help="rango PDF 1-based, p.ej. 37-96")
    ap.add_argument("--out", type=Path, required=True, help="markdown de salida")
    ap.add_argument("--title", default=None, help="H1 del capítulo")
    ap.add_argument("--prompt", type=Path, required=True, help="fichero con el contrato de transcripción")
    ap.add_argument("--workdir", type=Path, default=Path("_work"))
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--model", default="Gemini 3.1 Pro (High)")
    ap.add_argument("--fallback-model", default="Gemini 3.5 Flash (High)",
                    help="modelo para re-transcribir páginas truncadas rebeldes")
    ap.add_argument("--agy-bin", default=os.path.expanduser("~/.local/bin/agy"))
    ap.add_argument("--sentinel", action="store_true", help="tesseract 2º motor + informe de páginas sospechosas")
    ap.add_argument("--no-heal", action="store_true", help="no re-transcribir páginas truncadas (si ya se arreglaron a mano)")
    ap.add_argument("--figures-dir", type=Path, default=None, help="recorta y embebe figuras aquí")
    ap.add_argument("--fig-relpath", default="../figuras", help="ruta relativa a las figuras desde el md")
    ap.add_argument("--fig-dpi", type=int, default=300)
    args = ap.parse_args()

    a, b = (int(x) for x in args.pages.split("-"))
    pages_dir = args.workdir / "pages"
    agy_dir = args.workdir / "agy" / (args.out.stem)
    agy_dir.mkdir(parents=True, exist_ok=True)
    prompt = args.prompt.read_text(encoding="utf-8")

    print(f"[1/5] Render pág {a}-{b} @ {args.dpi}dpi …")
    render_pages(args.pdf, a, b, args.dpi, pages_dir)

    grp = batches(a, b, args.batch)
    print(f"[2/5] agy: {len(grp)} lotes de ≤{args.batch} págs, {args.parallel} en paralelo …")
    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = [ex.submit(run_batch, i, pg, prompt, pages_dir, agy_dir, args.model, args.agy_bin)
                for i, pg in enumerate(grp)]
        for fu in futs:
            idx, exp, got = fu.result()
            tag = "ok" if got == exp else f"⚠ {got}/{exp}"
            results.append((idx, exp, got))
            print(f"    lote b{idx:02d}: {tag}")
    short = [f"b{i:02d}" for i, e, g in results if g != e]
    if short:
        print(f"    ⚠ lotes incompletos tras reintento: {short} (revisar antes de fiarse)")

    flags = []
    if args.sentinel:
        print("[3/5] centinela tesseract …")
        flags = sentinel(a, b, pages_dir, agy_dir, args.workdir / "tess")
        print(f"    páginas sospechosas (revisar contra imagen): {flags or 'NINGUNA'}")
    else:
        print("[3/5] centinela omitido")

    print("[4/5] consolidando …")
    outs = [str(p) for p in sorted(agy_dir.glob("b*.out"))]
    cmd = ["python3", str(TOOLS / "agy_consolidate.py"), str(args.out), *outs]
    if args.title:
        cmd += ["--title", args.title]
    r = sh(cmd)
    print(r.stdout.strip())
    if r.returncode != 0:
        sys.exit(f"consolidación falló: {r.stderr.strip()}")

    # auto-sanado de páginas truncadas (notas huérfanas)
    if args.no_heal:
        stubborn = missing_ref_pages(args.out, agy_dir)
        print(f"    auto-sanado OMITIDO (--no-heal); notas huérfanas actuales: {stubborn or 'ninguna'}")
    else:
        stubborn = heal_truncated(args.pdf, agy_dir, args.out, prompt, pages_dir,
                                  args.title, args.model, args.fallback_model, args.agy_bin)
        if stubborn:
            print(f"    ⚠ tras auto-sanado, notas aún huérfanas en págs {stubborn} → REVISAR/transcribir a mano")
        else:
            print("    ✓ auto-sanado: sin notas huérfanas")

    nfig = 0
    if args.figures_dir:
        print("[5/5] figuras …")
        nfig = do_figures(args.pdf, agy_dir, args.out, args.figures_dir, args.fig_relpath, args.fig_dpi)
        print(f"    figuras recortadas y embebidas: {nfig}")
    else:
        print("[5/5] figuras omitidas")

    print(f"\n== {args.out} listo ==  lotes={len(grp)} incompletos={len(short)} "
          f"sospechosas={len(flags)} figuras={nfig}")
    if short or flags:
        print("   → ACCIÓN: revisar lotes incompletos / páginas sospechosas contra la imagen.")


if __name__ == "__main__":
    main()
