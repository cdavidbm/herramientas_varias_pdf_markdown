#!/usr/bin/env bash
# asr_setup.sh — Prepara la transcripción de audio (ASR) de La Forja, sin root.
#
# Para videos SIN subtítulos (ni manuales ni auto-generados): el único camino al
# texto es transcribir el audio. Deja un venv aislado (NO en git) con
# faster-whisper (CTranslate2, CPU): rápido y de alta calidad.
#
# Idempotente: re-ejecutable, salta lo ya hecho. Uso: bash asr_setup.sh
set -uo pipefail

VENV="$HOME/.local/share/forja-asr-venv"

echo "== Venv de ASR (faster-whisper) en $VENV =="
if [ ! -x "$VENV/bin/python" ]; then
    uv venv "$VENV" || { echo "no pude crear el venv (¿está uv instalado?)"; exit 1; }
fi
uv pip install --python "$VENV/bin/python" -q faster-whisper \
    && echo "  ✓ faster-whisper" || { echo "  ✗ falló la instalación"; exit 1; }

if ! command -v ffmpeg >/dev/null; then
    echo "  ⚠ ffmpeg no está en el PATH: hace falta para decodificar el audio."
    echo "     sudo apt-get install -y ffmpeg"
fi

echo
echo "Listo. Transcribe con:"
echo "  $VENV/bin/python tools/yt_audio_transcribe.py \"URL\" --model large-v3"
echo
echo "Modelos (calidad ↑ / velocidad ↓): tiny · base · small · medium · large-v3."
echo "Se descargan solos la primera vez (caché en ~/.cache/huggingface)."
