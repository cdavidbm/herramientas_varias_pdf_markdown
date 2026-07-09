#!/usr/bin/env bash
# ocr_setup.sh — Prepara el OCR de alta calidad de La Forja (sin root).
#
# Deja, en carpetas de usuario (NO en git):
#   1) Modelos tessdata_best (LSTM, más precisos) para los idiomas del usuario.
#   2) Un venv aislado con OpenCV (preprocesado) y, si se puede, RapidOCR (motor fuerte).
#
# Idempotente: re-ejecutable, salta lo ya hecho. Uso: bash ocr_setup.sh
set -uo pipefail

TESSDIR="$HOME/.local/share/forja-tessdata"
VENV="$HOME/.local/share/forja-ocr-venv"
BEST_URL="https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main"

# Idiomas para astrología/alquimia/filosofía/Rumi (+ europeos frecuentes).
LANGS=(eng spa osd lat grc ell ara fas deu fra ita)

echo "== 1) Modelos tessdata_best en $TESSDIR =="
mkdir -p "$TESSDIR"
for L in "${LANGS[@]}"; do
    dest="$TESSDIR/$L.traineddata"
    if [ -s "$dest" ]; then
        echo "  ✓ $L (ya está)"
    else
        echo -n "  ↓ $L … "
        if curl -fsSL --retry 3 -o "$dest" "$BEST_URL/$L.traineddata"; then
            echo "ok ($(du -h "$dest" | cut -f1))"
        else
            echo "FALLÓ (sigo con los demás)"; rm -f "$dest"
        fi
    fi
done

echo "== 2) Venv de OCR (OpenCV + RapidOCR) en $VENV =="
if [ ! -x "$VENV/bin/python" ]; then
    uv venv "$VENV" || { echo "no pude crear el venv"; exit 1; }
fi
# OpenCV headless: preprocesado sin dependencias gráficas (ideal en WSL/headless).
uv pip install --python "$VENV/bin/python" -q opencv-python-headless numpy pillow \
    && echo "  ✓ OpenCV + numpy + pillow"
# RapidOCR (ONNX, CPU): motor fuerte de respaldo. Best-effort — no aborta si falla.
if uv pip install --python "$VENV/bin/python" -q rapidocr-onnxruntime 2>/dev/null; then
    echo "  ✓ RapidOCR (motor alternativo disponible)"
else
    echo "  ⚠ RapidOCR no se instaló (opcional); el resto funciona igual"
fi

echo
echo "Listo. Los scripts de OCR usan:"
echo "  TESSDATA_PREFIX=$TESSDIR   (idiomas best)"
echo "  Python OCR: $VENV/bin/python   (OpenCV/RapidOCR)"
echo "Idiomas disponibles: $(ls "$TESSDIR"/*.traineddata 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/.traineddata//' | tr '\n' ' ')"
