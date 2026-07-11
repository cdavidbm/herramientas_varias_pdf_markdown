#!/usr/bin/env python3
"""
yt_audio_transcribe.py — Transcribe el AUDIO de un video (o un archivo local)
con ASR local (faster-whisper). Para videos SIN subtítulos de ningún tipo.

Cuando un video de YouTube no tiene subtítulos manuales NI auto-generados (lo
detecta yt_transcript.py), no hay texto que extraer: el único camino es
transcribir el audio. Esta herramienta baja el audio con yt-dlp y lo pasa por
faster-whisper (CTranslate2, CPU), produciendo la MISMA salida que
yt_transcript.py —`<slug>.txt` (texto sin timestamps) + `<slug>.meta.json`—
para que el paso de pulido de la skill /youtube funcione igual.

A diferencia de los auto-subtítulos de YouTube, Whisper YA entrega puntuación y
mayúsculas, así que el texto sale bastante limpio; el agente aún mejora párrafos,
tecnicismos/nombres propios y encabezados por capítulo. NUNCA resume: íntegro.

Requiere el venv de ASR:  bash tools/asr_setup.sh
  (crea ~/.local/share/forja-asr-venv con faster-whisper). Ejecuta este script
  con ESE python:
    ~/.local/share/forja-asr-venv/bin/python tools/yt_audio_transcribe.py ...

Usage:
  PY=~/.local/share/forja-asr-venv/bin/python
  $PY tools/yt_audio_transcribe.py "URL"                       # video entero
  $PY tools/yt_audio_transcribe.py "URL" --model large-v3      # máxima calidad
  $PY tools/yt_audio_transcribe.py "URL" --lang es             # fija el idioma
  $PY tools/yt_audio_transcribe.py "URL" --start 0:00 --end 3:00   # solo un tramo (prueba)
  $PY tools/yt_audio_transcribe.py audio.m4a --model medium    # archivo local
  $PY tools/yt_audio_transcribe.py "URL" --cookies-from-browser firefox  # video privado/oculto

Options:
  --model NAME     tiny|base|small|medium|large-v3 (def. large-v3; ↑calidad ↓velocidad).
  --lang CODE      idioma del audio (def. autodetección).
  --device DEV     cpu|cuda (def. cpu).  --compute-type int8|int8_float16|float16|float32.
  --start T --end T   transcribe solo ese tramo (mm:ss o segundos); usa
                      yt-dlp --download-sections. Ideal para probar en videos largos.
  --srt            además escribe un <slug>.srt con tiempos (por si lo necesitas).
  -o, --output-dir DIR    carpeta de salida (def. actual).
  --cookies FILE          cookies.txt (para videos privados/con login).
  --cookies-from-browser B   lee cookies del navegador (firefox, chrome, vivaldi…;
                             funciona con navegadores del MISMO sistema, no la
                             Vivaldi de Windows desde WSL — para eso exporta cookies.txt).
  --keep-audio     no borra el audio descargado.
  --wrap N         ancho de wrap del .txt (def. 100; 0 = sin wrap).

Requiere: faster-whisper (venv de ASR), yt-dlp (para URLs) y ffmpeg.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


def slugify(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:maxlen].strip("_") or "transcript"


def secs(t: str) -> str:
    """Normaliza 'mm:ss' / 'h:mm:ss' / '90' a segundos-string para yt-dlp."""
    t = t.strip()
    if ":" not in t:
        return t
    parts = [int(p) for p in t.split(":")]
    total = 0
    for p in parts:
        total = total * 60 + p
    return str(total)


def need(exe: str, hint: str) -> str:
    path = shutil.which(exe)
    if not path:
        sys.exit(f"ERROR: falta '{exe}'. {hint}")
    return path


def cookie_args(args) -> list[str]:
    out: list[str] = []
    if args.cookies:
        out += ["--cookies", args.cookies]
    if args.cookies_from_browser:
        out += ["--cookies-from-browser", args.cookies_from_browser]
    return out


def probe(url: str, args) -> dict:
    exe = need("yt-dlp", "Instálalo con `pip install --user yt-dlp`.")
    cmd = [exe, "--dump-single-json", "--no-playlist", "--no-warnings", *cookie_args(args), url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR: yt-dlp no pudo leer el video.\n{e.stderr.strip()}")
    return json.loads(out)


def download_audio(url: str, outdir: Path, args) -> Path:
    exe = need("yt-dlp", "Instálalo con `pip install --user yt-dlp`.")
    need("ffmpeg", "Instálalo con `sudo apt-get install ffmpeg`.")
    tmpl = str(outdir / "audio.%(ext)s")
    cmd = [exe, "-f", "bestaudio/best", "-o", tmpl, "--no-playlist",
           "--no-warnings", *cookie_args(args)]
    if args.start or args.end:
        start = secs(args.start) if args.start else "0"
        end = secs(args.end) if args.end else "inf"
        cmd += ["--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    files = sorted(outdir.glob("audio.*"))
    if not files:
        sys.exit(f"ERROR: yt-dlp no descargó audio.\n{r.stderr.strip()[-800:]}")
    return files[0]


def build_meta(info: dict, model: str, lang: str | None) -> dict:
    return {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "url": info.get("webpage_url"),
        "id": info.get("id"),
        "upload_date": info.get("upload_date"),
        "duration_string": info.get("duration_string"),
        "duration": info.get("duration"),
        "subtitle_kind": "asr",
        "asr_model": model,
        "asr_language": lang,
        "chapters": [
            {"title": c.get("title"), "start": c.get("start_time"), "end": c.get("end_time")}
            for c in (info.get("chapters") or [])
        ],
        "description": info.get("description"),
    }


def fmt_ts(t: float) -> str:
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _run(model, audio: Path, args, vad: bool):
    segments, info = model.transcribe(
        str(audio), language=args.lang, vad_filter=vad, beam_size=5,
    )
    total = info.duration or 0
    seg_list: list = []
    for seg in segments:
        seg_list.append(seg)
        pct = f" {seg.end/total*100:4.0f}%" if total else ""
        print(f"\r  [{fmt_ts(seg.end)}]{pct}", end="", file=sys.stderr, flush=True)
    print("", file=sys.stderr)
    return seg_list, info


def transcribe(audio: Path, args) -> tuple[str, list, str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("ERROR: falta faster-whisper. Corre `bash tools/asr_setup.sh` y "
                 "ejecuta este script con ~/.local/share/forja-asr-venv/bin/python.")
    print(f"Cargando modelo '{args.model}' ({args.device}/{args.compute_type})…",
          file=sys.stderr)
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    use_vad = not args.no_vad
    seg_list, info = _run(model, audio, args, vad=use_vad)
    # El VAD (Silero) a veces borra tramos válidos (audio tenue, música, voz lenta):
    # si activo dio 0 segmentos, reintento sin VAD para no perder el contenido.
    if use_vad and not seg_list:
        print("  ⚠ El VAD no dejó nada; reintento sin VAD…", file=sys.stderr)
        seg_list, info = _run(model, audio, args, vad=False)

    lang = info.language
    print(f"Idioma: {lang} (p={info.language_probability:.2f}) · "
          f"{len(seg_list)} segmentos.", file=sys.stderr)
    text = re.sub(r"\s+", " ", " ".join(s.text.strip() for s in seg_list)).strip()
    return text, seg_list, lang


def write_srt(seg_list: list, path: Path) -> None:
    lines = []
    for i, s in enumerate(seg_list, 1):
        lines.append(str(i))
        lines.append(f"{fmt_ts(s.start)} --> {fmt_ts(s.end)}")
        lines.append(s.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---- modo reanudable (auto-guardado + reanudación) ---------------------------
def _read_partial(path: Path) -> list:
    """Lee los segmentos ya guardados (uno por línea JSON)."""
    segs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                segs.append(json.loads(line))
            except Exception:
                pass
    return segs


def _slice_audio(audio: Path, offset: float, dest: Path) -> Path:
    """Extrae el audio desde `offset` s (re-codifica a wav 16k mono: corte limpio)."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{offset:.3f}", "-i", str(audio),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(dest)],
        capture_output=True,
    )
    return dest


def _persist_download(url: str, dldir: Path, args) -> Path:
    """Descarga el audio a una carpeta estable (reutilizable al reanudar)."""
    existing = sorted(dldir.glob("audio.*")) if dldir.exists() else []
    if existing:
        return existing[0]
    dldir.mkdir(parents=True, exist_ok=True)
    return download_audio(url, dldir, args)


def run_resumable(args) -> None:
    """Transcribe con auto-guardado por segmento y reanudación tras un corte."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("ERROR: falta faster-whisper. Corre `bash tools/asr_setup.sh` y "
                 "ejecuta este script con ~/.local/share/forja-asr-venv/bin/python.")
    info = probe(args.source, args)
    title = info.get("title") or info.get("id") or "transcript"
    slug = slugify(title)
    outdir = Path(args.output_dir)
    total = info.get("duration") or 0
    partial = outdir / f".{slug}.partial.jsonl"
    dldir = outdir / f".{slug}.dl"
    slice_path = outdir / f".{slug}.slice.wav"

    print(f"Audio: {title}", file=sys.stderr)
    audio = _persist_download(args.source, dldir, args)

    prev = _read_partial(partial)
    offset = prev[-1]["e"] if prev else 0.0
    if offset > 0:
        print(f"↻ Reanudando desde {fmt_ts(offset)} "
              f"({len(prev)} segmentos ya guardados).", file=sys.stderr)
        trans_audio = _slice_audio(audio, offset, slice_path)
    else:
        trans_audio = audio

    print(f"Cargando modelo '{args.model}' ({args.device}/{args.compute_type})…",
          file=sys.stderr)
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    use_vad = not args.no_vad
    segments, sinfo = model.transcribe(
        str(trans_audio), language=args.lang, vad_filter=use_vad, beam_size=5,
    )
    lang = sinfo.language
    n_new = 0
    with partial.open("a", encoding="utf-8") as fh:   # append = no pisa lo guardado
        for seg in segments:
            obj = {"s": round(seg.start + offset, 3),
                   "e": round(seg.end + offset, 3),
                   "t": seg.text.strip()}
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            fh.flush()                                 # <- auto-guardado por segmento
            n_new += 1
            abs_end = seg.end + offset
            pct = f" {abs_end/total*100:4.0f}%" if total else ""
            print(f"\r  [{fmt_ts(abs_end)}]{pct}", end="", file=sys.stderr, flush=True)
    print("", file=sys.stderr)

    # Ensamblado final desde el .partial (todo lo guardado, resúmenes previos incluidos).
    allsegs = _read_partial(partial)
    text = re.sub(r"\s+", " ", " ".join(s["t"].strip() for s in allsegs)).strip()
    meta = build_meta(info, args.model, lang)
    out_text = textwrap.fill(text, width=args.wrap) if (args.wrap and args.wrap > 0) else text
    (outdir / f"{slug}.txt").write_text(out_text + "\n", encoding="utf-8")
    (outdir / f"{slug}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Limpieza (sólo tras terminar bien).
    partial.unlink(missing_ok=True)
    slice_path.unlink(missing_ok=True)
    if not args.keep_audio:
        shutil.rmtree(dldir, ignore_errors=True)

    wc = len(text.split())
    print(f"✅ {outdir / (slug + '.txt')}  ({wc} palabras · ASR {args.model} · {lang} · "
          f"{n_new} segmentos nuevos)")
    print(f"   {outdir / (slug + '.meta.json')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="URL de YouTube o archivo de audio/video local")
    ap.add_argument("--model", default="large-v3", help="tiny|base|small|medium|large-v3")
    ap.add_argument("--lang", help="idioma del audio (def. autodetección)")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument("--compute-type", default="int8", dest="compute_type",
                    help="int8|int8_float16|float16|float32")
    ap.add_argument("--start", help="inicio del tramo (mm:ss o segundos)")
    ap.add_argument("--end", help="fin del tramo (mm:ss o segundos)")
    ap.add_argument("--no-vad", action="store_true", dest="no_vad",
                    help="desactiva el filtro de voz (VAD); transcribe todo el audio")
    ap.add_argument("--srt", action="store_true", help="además escribe un .srt con tiempos")
    ap.add_argument("-o", "--output-dir", default=".", help="carpeta de salida")
    ap.add_argument("--cookies", help="archivo cookies.txt (videos privados/con login)")
    ap.add_argument("--cookies-from-browser", dest="cookies_from_browser",
                    help="lee cookies del navegador del mismo sistema")
    ap.add_argument("--keep-audio", action="store_true", help="no borra el audio descargado")
    ap.add_argument("--wrap", type=int, default=100, help="ancho de wrap (0 = sin wrap)")
    ap.add_argument("--resumable", action="store_true",
                    help="auto-guardado por segmento + reanudación: si el proceso se "
                         "corta (apagón, kill), al relanzar el MISMO comando continúa "
                         "desde el último segmento guardado. Recomendado para videos largos.")
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    p = Path(args.source)
    is_local = p.exists() and not re.match(r"https?://", args.source)

    if args.resumable and not is_local:
        run_resumable(args)
        return

    tmp: Path | None = None
    if is_local:
        audio = p
        info = {"title": p.stem}
    else:
        info = probe(args.source, args)
        tmp = Path(tempfile.mkdtemp(dir=outdir))
        print(f"Bajando audio de: {info.get('title')}", file=sys.stderr)
        audio = download_audio(args.source, tmp, args)

    text, seg_list, lang = transcribe(audio, args)
    meta = build_meta(info, args.model, lang)

    if args.wrap and args.wrap > 0:
        out_text = textwrap.fill(text, width=args.wrap)
    else:
        out_text = text
    slug = slugify(info.get("title") or "transcript")
    (outdir / f"{slug}.txt").write_text(out_text + "\n", encoding="utf-8")
    (outdir / f"{slug}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.srt:
        write_srt(seg_list, outdir / f"{slug}.srt")

    if tmp and not args.keep_audio:
        shutil.rmtree(tmp, ignore_errors=True)

    wc = len(text.split())
    print(f"✅ {outdir / (slug + '.txt')}  ({wc} palabras · ASR {args.model} · {lang})")
    print(f"   {outdir / (slug + '.meta.json')}")
    if args.srt:
        print(f"   {outdir / (slug + '.srt')}")


if __name__ == "__main__":
    main()
