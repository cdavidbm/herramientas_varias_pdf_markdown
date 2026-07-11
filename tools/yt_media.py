#!/usr/bin/env python3
"""
yt_media.py — Front door to yt-dlp for La Forja: probe a video and download its
audio, video, subtitle files, thumbnail or description.

Companion to yt_transcript.py. Use THIS for grabbing media/files (audio for a
podcast source, the video itself, raw subtitle files, the description with its
links); use yt_transcript.py when what you want is a clean text transcript for a
markdown document.

Works on single videos and playlists (yt-dlp expands playlist URLs itself).

Usage:
  python3 yt_media.py "URL" --info                 # summary (title, canal, subs, capítulos)
  python3 yt_media.py "URL" --info --json          # full metadata JSON to stdout
  python3 yt_media.py "URL" --audio                # bestaudio -> mp3 (needs ffmpeg)
  python3 yt_media.py "URL" --audio --format m4a   # keep m4a container
  python3 yt_media.py "URL" --video                # best <=1080p mp4
  python3 yt_media.py "URL" --video --quality 720
  python3 yt_media.py "URL" --subs --lang es       # write subtitle FILES (manual+auto)
  python3 yt_media.py "URL" --thumbnail
  python3 yt_media.py "URL" --description           # dump description to <id>.description.txt

Options:
  -o, --output-dir DIR   Destination (default: current dir).
  --lang CODE            Subtitle language for --subs (default: all).
  --format EXT           Audio container/codec (mp3 default, or m4a/opus/wav/flac).
  --quality N            Max video height for --video (default 1080).
  --no-playlist          Treat a playlist URL as the single linked video.
  --dry-run              Print the yt-dlp command(s) without running them.

Requires: yt-dlp on PATH; ffmpeg for --audio re-encoding and merged --video.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def need_ytdlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        sys.exit("ERROR: yt-dlp no está en el PATH. Instálalo con "
                 "`pip install --user yt-dlp` (o vía uv).")
    return exe


def cookie_args(args) -> list[str]:
    out: list[str] = []
    if getattr(args, "cookies", None):
        out += ["--cookies", args.cookies]
    if getattr(args, "cookies_from_browser", None):
        out += ["--cookies-from-browser", args.cookies_from_browser]
    return out


def run(cmd: list[str], dry: bool) -> None:
    if dry:
        print("· " + " ".join(cmd))
        return
    subprocess.run(cmd, check=False)


def probe(url: str, no_playlist: bool, cookies: list[str] | None = None) -> dict:
    exe = need_ytdlp()
    cmd = [exe, "--dump-single-json", "--no-warnings", *(cookies or []), url]
    if no_playlist:
        cmd.insert(1, "--no-playlist")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR: yt-dlp no pudo leer el video.\n{e.stderr.strip()}")
    return json.loads(out)


def cmd_info(url: str, args) -> None:
    info = probe(url, args.no_playlist, cookie_args(args))
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    manual = sorted((info.get("subtitles") or {}).keys())
    auto = sorted((info.get("automatic_captions") or {}).keys())
    print(f"Título   : {info.get('title')}")
    print(f"Canal    : {info.get('channel') or info.get('uploader')}")
    print(f"Subido   : {info.get('upload_date')}")
    print(f"Duración : {info.get('duration_string')}")
    print(f"Vistas   : {info.get('view_count')}")
    print(f"URL      : {info.get('webpage_url')}")
    print(f"\nSubtítulos manuales ({len(manual)}): " + (", ".join(manual) or "—"))
    # auto captions list every translation target; show a compact hint.
    base_auto = sorted({l.split("-")[0] for l in auto})
    print(f"Auto-generados: {len(auto)} pistas "
          f"(idiomas base: {', '.join(base_auto[:20]) or '—'}"
          f"{' …' if len(base_auto) > 20 else ''})")
    ch = info.get("chapters") or []
    if ch:
        print(f"\nCapítulos ({len(ch)}):")
        for c in ch:
            print(f"  · {c.get('title')}")


def cmd_audio(url: str, args) -> None:
    exe = need_ytdlp()
    if not shutil.which("ffmpeg"):
        print("⚠ ffmpeg no está en el PATH: la conversión de audio puede fallar.",
              file=sys.stderr)
    out = str(Path(args.output_dir) / "%(title)s.%(ext)s")
    cmd = [exe, "-x", "--audio-format", args.format, "--audio-quality", "0",
           "--no-warnings", *cookie_args(args), "-o", out, url]
    if args.no_playlist:
        cmd.insert(1, "--no-playlist")
    run(cmd, args.dry_run)


def cmd_video(url: str, args) -> None:
    exe = need_ytdlp()
    q = args.quality
    fmt = f"bv*[height<={q}]+ba/b[height<={q}]/bv*+ba/b"
    out = str(Path(args.output_dir) / "%(title)s.%(ext)s")
    cmd = [exe, "-f", fmt, "--merge-output-format", "mp4",
           "--no-warnings", *cookie_args(args), "-o", out, url]
    if args.no_playlist:
        cmd.insert(1, "--no-playlist")
    run(cmd, args.dry_run)


def cmd_subs(url: str, args) -> None:
    exe = need_ytdlp()
    langs = args.lang or "all"
    out = str(Path(args.output_dir) / "%(title)s.%(ext)s")
    cmd = [exe, "--skip-download", "--write-subs", "--write-auto-subs",
           "--sub-langs", langs, "--sub-format", "vtt/srt/best",
           "--no-warnings", *cookie_args(args), "-o", out, url]
    if args.no_playlist:
        cmd.insert(1, "--no-playlist")
    run(cmd, args.dry_run)


def cmd_thumbnail(url: str, args) -> None:
    exe = need_ytdlp()
    out = str(Path(args.output_dir) / "%(title)s.%(ext)s")
    cmd = [exe, "--skip-download", "--write-thumbnail",
           "--no-warnings", *cookie_args(args), "-o", out, url]
    if args.no_playlist:
        cmd.insert(1, "--no-playlist")
    run(cmd, args.dry_run)


def cmd_description(url: str, args) -> None:
    exe = need_ytdlp()
    out = str(Path(args.output_dir) / "%(title)s.%(ext)s")
    cmd = [exe, "--skip-download", "--write-description",
           "--no-warnings", *cookie_args(args), "-o", out, url]
    if args.no_playlist:
        cmd.insert(1, "--no-playlist")
    run(cmd, args.dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="URL de YouTube (video o playlist)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--info", action="store_true", help="muestra metadatos")
    g.add_argument("--audio", action="store_true", help="baja el audio")
    g.add_argument("--video", action="store_true", help="baja el video")
    g.add_argument("--subs", action="store_true", help="baja los archivos de subtítulos")
    g.add_argument("--thumbnail", action="store_true", help="baja la miniatura")
    g.add_argument("--description", action="store_true", help="baja la descripción")
    ap.add_argument("--json", action="store_true", help="con --info: JSON completo")
    ap.add_argument("-o", "--output-dir", default=".", help="carpeta de salida")
    ap.add_argument("--lang", help="idioma de subtítulos para --subs (def: all)")
    ap.add_argument("--format", default="mp3", help="formato de audio (mp3/m4a/opus/wav/flac)")
    ap.add_argument("--quality", type=int, default=1080, help="altura máx. de video")
    ap.add_argument("--no-playlist", action="store_true", help="ignora la playlist")
    ap.add_argument("--cookies", help="archivo cookies.txt (videos privados/con login)")
    ap.add_argument("--cookies-from-browser", dest="cookies_from_browser",
                    help="lee cookies del navegador del mismo sistema (firefox, chrome…)")
    ap.add_argument("--dry-run", action="store_true", help="imprime el comando sin ejecutar")
    args = ap.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if args.info:
        cmd_info(args.url, args)
    elif args.audio:
        cmd_audio(args.url, args)
    elif args.video:
        cmd_video(args.url, args)
    elif args.subs:
        cmd_subs(args.url, args)
    elif args.thumbnail:
        cmd_thumbnail(args.url, args)
    elif args.description:
        cmd_description(args.url, args)


if __name__ == "__main__":
    main()
