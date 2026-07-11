#!/usr/bin/env python3
"""
yt_transcript.py — YouTube subtitles → clean, de-duplicated, timestamp-free text.

The crown jewel of La Forja's YouTube toolbox. Turns a video's captions —
especially YouTube's **auto-generated** ones — into a clean plain-text
transcript with NO timestamps, NO markup, and NO rolling-window duplication,
ready for the agent to polish into high-quality markdown (punctuation,
paragraphs, spelling) with the /youtube skill.

Why a script: YouTube auto-caption VTT is hostile to read. Each spoken phrase
appears TWICE (once being "typed out" with per-word `<00:00:04.400><c> word</c>`
timing tags, once as a settled plain line) and consecutive cues overlap in a
rolling window ("hello" → "hello everyone" → "hello everyone and welcome").
Naive timestamp-stripping yields a stutter ("hello hello everyone hello
everyone and welcome"). This script rebuilds the real word stream with a
word-level suffix/prefix overlap merge, which handles both manual and
auto-generated subtitles.

What it does NOT do: it does not add punctuation, capitalization or paragraphs —
auto-captions have none, and restoring them is editorial judgment the AGENT
does (that is the /youtube skill's job). This tool only recovers the faithful,
de-duplicated word stream. It never summarizes or drops content.

Inputs:
  - A YouTube URL (video or a single video of a playlist) → fetches subs via
    yt-dlp (prefers human/manual subs in the requested language, falls back to
    auto-generated), then cleans them.
  - A local .vtt or .srt file → just cleans it (no network, no yt-dlp needed).

Usage:
  python3 yt_transcript.py "https://youtu.be/VIDEO"                 # -> <slug>.txt + <slug>.meta.json
  python3 yt_transcript.py "https://youtu.be/VIDEO" --lang es       # prefer Spanish track
  python3 yt_transcript.py "https://youtu.be/VIDEO" --auto          # force auto-generated
  python3 yt_transcript.py "https://youtu.be/VIDEO" --list          # just list available tracks
  python3 yt_transcript.py captions.vtt --stdout                    # clean a local file to stdout
  python3 yt_transcript.py "URL" -o ./transcripts --stdout

Options:
  --lang CODE     Preferred language (default: original / first available).
  --auto          Prefer auto-generated captions over manual ones.
  --manual-only   Fail if no human/manual subtitles exist (no auto fallback).
  --list          Print available subtitle tracks and exit.
  -o, --output-dir DIR   Where to write outputs (default: current dir).
  --stdout        Print the clean transcript to stdout (still writes files
                  unless --no-files).
  --no-files      Don't write .txt / .meta.json (use with --stdout).
  --wrap N        Wrap output at N columns for readability (default 100; 0 = off).
  --keep-overlap  Disable the overlap merge (debug: raw de-timestamped lines).

Requires: yt-dlp on PATH (only for URL inputs). Local file inputs use stdlib.
"""
from __future__ import annotations
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

# ---- regexes -----------------------------------------------------------------
TS_LINE = re.compile(r"-->")                       # cue timing line
INLINE_TS = re.compile(r"<\d{2}:\d{2}:\d{2}[.,]\d{3}>")   # <00:00:04.400>
TAG = re.compile(r"</?[cibuv](?:\.[\w\-]+)?[^>]*>|</?[^>]+>")  # <c>, </c>, <v ...>, any tag
SRT_INDEX = re.compile(r"^\d+$")
SRT_TS = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
VTT_NOTE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\b|STYLE\b|REGION\b)")


def slugify(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:maxlen].strip("_") or "transcript"


# ---- VTT / SRT parsing -------------------------------------------------------
def _clean_text_line(line: str) -> str:
    """Strip inline timing tags, markup and entities from one caption text line."""
    line = INLINE_TS.sub("", line)
    line = TAG.sub("", line)
    line = html.unescape(line)
    return re.sub(r"\s+", " ", line).strip()


def parse_cues(raw: str) -> list[str]:
    """Return an ordered list of cue texts (one string per cue), markup removed.

    Works for both WebVTT and SRT. Cue text lines within a cue are joined with a
    single space. Empty cues are dropped.
    """
    # Normalise newlines; split into blocks on blank lines.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n", raw)
    cues: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        text_lines: list[str] = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if VTT_NOTE.match(s):
                continue
            if TS_LINE.search(s):        # cue timing line (VTT or SRT)
                continue
            if SRT_INDEX.match(s):       # SRT numeric index line
                continue
            text_lines.append(ln)
        cleaned = _clean_text_line(" ".join(text_lines))
        if cleaned:
            cues.append(cleaned)
    return cues


def merge_overlap(cues: list[str], enable: bool = True) -> str:
    """Rebuild the real word stream from rolling/duplicated caption cues.

    For each cue, find the longest suffix of the words emitted so far that
    equals the prefix of this cue, and append only the non-overlapping tail.
    This collapses YouTube's rolling window ("a", "a b", "a b c" -> "a b c")
    and drops exact settled duplicates, while a brand-new cue (no overlap)
    is appended whole.
    """
    if not enable:
        # Debug path: just drop lines identical to the previous one.
        out: list[str] = []
        for c in cues:
            if not out or out[-1] != c:
                out.append(c)
        return "\n".join(out)

    emitted: list[str] = []
    for cue in cues:
        words = cue.split()
        if not words:
            continue
        max_k = min(len(emitted), len(words))
        k = 0
        # Prefer the LONGEST overlap so partial rolling windows merge fully.
        for kk in range(max_k, 0, -1):
            if emitted[-kk:] == words[:kk]:
                k = kk
                break
        emitted.extend(words[k:])
    return " ".join(emitted)


def clean_subtitle_file(path: Path, enable_merge: bool = True) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    cues = parse_cues(raw)
    return merge_overlap(cues, enable_merge)


# ---- yt-dlp helpers ----------------------------------------------------------
def _need_ytdlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        sys.exit("ERROR: yt-dlp no está en el PATH. Instálalo (p. ej. "
                 "`pip install --user yt-dlp`) o pásale un .vtt/.srt local.")
    return exe


def cookie_args(args) -> list[str]:
    out: list[str] = []
    if getattr(args, "cookies", None):
        out += ["--cookies", args.cookies]
    if getattr(args, "cookies_from_browser", None):
        out += ["--cookies-from-browser", args.cookies_from_browser]
    return out


def probe(url: str, cookies: list[str] | None = None) -> dict:
    """Fetch the video's metadata JSON (single video, no playlist)."""
    exe = _need_ytdlp()
    try:
        out = subprocess.run(
            [exe, "--dump-single-json", "--no-playlist", "--no-warnings",
             *(cookies or []), url],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR: yt-dlp no pudo leer el video.\n{e.stderr.strip()}")
    return json.loads(out)


def available_tracks(info: dict) -> tuple[dict, dict]:
    """Return (manual_subs, auto_captions) dicts: {lang: [formats]}."""
    manual = {k: [f.get("ext") for f in v] for k, v in (info.get("subtitles") or {}).items()}
    auto = {k: [f.get("ext") for f in v] for k, v in (info.get("automatic_captions") or {}).items()}
    return manual, auto


def _pick_lang(langs: list[str], want: str | None) -> str | None:
    """Choose the best matching language code from what's available."""
    if not langs:
        return None
    if not want:
        # Prefer an "-orig" (original) auto track, else the first.
        for l in langs:
            if l.endswith("-orig"):
                return l
        return langs[0]
    want = want.lower()
    # exact, then prefix (es matches es-ES / es-orig), then any startswith.
    for l in langs:
        if l.lower() == want:
            return l
    for l in langs:
        base = l.lower().split("-")[0]
        if base == want:
            return l
    return None


def download_subs(url: str, lang: str, auto: bool, outdir: Path,
                  cookies: list[str] | None = None) -> Path | None:
    """Download one subtitle track (vtt) to a temp dir, return the .vtt path."""
    exe = _need_ytdlp()
    tmp = Path(tempfile.mkdtemp(dir=outdir))
    flag = "--write-auto-subs" if auto else "--write-subs"
    cmd = [exe, "--skip-download", flag, "--no-playlist", "--no-warnings",
           "--sub-langs", lang, "--sub-format", "vtt/srt/best",
           *(cookies or []), "-o", str(tmp / "%(id)s.%(ext)s"), url]
    subprocess.run(cmd, capture_output=True, text=True)
    files = sorted(list(tmp.glob("*.vtt")) + list(tmp.glob("*.srt")))
    return files[0] if files else None


def build_meta(info: dict, sub_kind: str | None, sub_lang: str | None) -> dict:
    return {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "url": info.get("webpage_url"),
        "id": info.get("id"),
        "upload_date": info.get("upload_date"),
        "duration_string": info.get("duration_string"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "subtitle_kind": sub_kind,       # "manual" | "auto"
        "subtitle_lang": sub_lang,
        "chapters": [
            {"title": c.get("title"), "start": c.get("start_time"), "end": c.get("end_time")}
            for c in (info.get("chapters") or [])
        ],
        "description": info.get("description"),
    }


# ---- main --------------------------------------------------------------------
def run_url(url: str, args) -> None:
    ck = cookie_args(args)
    info = probe(url, ck)
    manual, auto = available_tracks(info)

    if args.list:
        print(f"Título : {info.get('title')}")
        print(f"Canal  : {info.get('channel') or info.get('uploader')}")
        print(f"Duración: {info.get('duration_string')}")
        print(f"\nSubtítulos MANUALES ({len(manual)}): "
              + (", ".join(sorted(manual)) or "—"))
        print(f"Auto-generados ({len(auto)}): "
              + (", ".join(sorted(auto)) or "—"))
        if info.get("chapters"):
            print(f"\nCapítulos ({len(info['chapters'])}):")
            for c in info["chapters"]:
                print(f"  · {c.get('title')}")
        return

    # Decide which track to pull.
    sub_kind = sub_lang = None
    vtt = None
    if not args.auto:
        picked = _pick_lang(sorted(manual), args.lang)
        if picked:
            vtt = download_subs(url, picked, auto=False, outdir=args._outdir, cookies=ck)
            if vtt:
                sub_kind, sub_lang = "manual", picked
    if vtt is None and not args.manual_only:
        picked = _pick_lang(sorted(auto), args.lang)
        if picked:
            vtt = download_subs(url, picked, auto=True, outdir=args._outdir, cookies=ck)
            if vtt:
                sub_kind, sub_lang = "auto", picked

    if vtt is None:
        if args.manual_only:
            sys.exit("ERROR: no hay subtítulos MANUALES en el idioma pedido "
                     f"(manuales: {', '.join(sorted(manual)) or '—'}).")
        sys.exit("ERROR: este video no tiene subtítulos utilizables "
                 f"(manuales: {', '.join(sorted(manual)) or '—'} · "
                 f"auto: {', '.join(sorted(auto)) or '—'}).\n"
                 "Sin subtítulos, baja el audio con yt_media.py --audio y "
                 "transcríbelo aparte.")

    text = clean_subtitle_file(vtt, enable_merge=not args.keep_overlap)
    meta = build_meta(info, sub_kind, sub_lang)
    emit(text, meta, info.get("title") or info.get("id") or "transcript", args)
    print(f"[{sub_kind}:{sub_lang}] {meta['title']}", file=sys.stderr)


def run_local(path: Path, args) -> None:
    text = clean_subtitle_file(path, enable_merge=not args.keep_overlap)
    meta = {"source_file": str(path), "subtitle_kind": "local"}
    emit(text, meta, path.stem, args)


def emit(text: str, meta: dict, title: str, args) -> None:
    if args.wrap and args.wrap > 0:
        text = textwrap.fill(text, width=args.wrap)
    if args.stdout:
        print(text)
    if args.no_files:
        return
    slug = slugify(title)
    txt_path = args._outdir / f"{slug}.txt"
    txt_path.write_text(text + "\n", encoding="utf-8")
    meta_path = args._outdir / f"{slug}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.stdout:
        wc = len(text.split())
        print(f"✅ {txt_path}  ({wc} palabras)")
        print(f"   {meta_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="URL de YouTube o archivo .vtt/.srt local")
    ap.add_argument("--lang", help="idioma preferido (es, en, es-ES, ...)")
    ap.add_argument("--auto", action="store_true", help="prefiere auto-generados")
    ap.add_argument("--manual-only", action="store_true", help="falla si no hay subs manuales")
    ap.add_argument("--list", action="store_true", help="lista pistas disponibles y sale")
    ap.add_argument("-o", "--output-dir", default=".", help="carpeta de salida")
    ap.add_argument("--stdout", action="store_true", help="imprime el transcript limpio")
    ap.add_argument("--no-files", action="store_true", help="no escribe .txt/.meta.json")
    ap.add_argument("--wrap", type=int, default=100, help="ancho de wrap (0 = sin wrap)")
    ap.add_argument("--keep-overlap", action="store_true",
                    help="desactiva la fusión de solapes (debug)")
    ap.add_argument("--cookies", help="archivo cookies.txt (videos privados/con login)")
    ap.add_argument("--cookies-from-browser", dest="cookies_from_browser",
                    help="lee cookies del navegador del mismo sistema (firefox, chrome…)")
    args = ap.parse_args()

    args._outdir = Path(args.output_dir)
    args._outdir.mkdir(parents=True, exist_ok=True)

    src = args.source
    p = Path(src)
    if p.exists() and p.suffix.lower() in (".vtt", ".srt"):
        run_local(p, args)
    elif re.match(r"https?://", src) or re.match(r"^[\w-]{11}$", src):
        run_url(src, args)
    else:
        sys.exit(f"ERROR: no reconozco '{src}' como URL ni como .vtt/.srt.")


if __name__ == "__main__":
    main()
