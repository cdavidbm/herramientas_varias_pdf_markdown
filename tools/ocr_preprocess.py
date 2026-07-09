#!/usr/bin/env python3
"""
ocr_preprocess.py — Limpia una imagen de página ANTES del OCR (escaneos malos).

Sube mucho la precisión de tesseract en originales de baja calidad: convierte a
gris, mejora contraste (CLAHE), quita ruido, endereza (deskew), reescala si el
DPI es bajo y binariza de forma adaptativa. Fiel al texto — no inventa píxeles.

Requiere OpenCV (venv de La Forja: ~/.local/share/forja-ocr-venv/bin/python).

Uso:
    python ocr_preprocess.py entrada.png salida.png [opciones]
Opciones:
    --min-dim N      reescala si el lado menor < N px (def. 1800; 0 = nunca)
    --no-deskew      no enderezar
    --no-binarize    deja en gris (útil si el texto es tenue/antiguo)
    --denoise N      fuerza de denoise 0-15 (def. 7)
"""
from __future__ import annotations
import argparse
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("error: falta OpenCV. Corre tools/ocr_setup.sh (crea el venv de OCR).")


def deskew(gray: "np.ndarray") -> "np.ndarray":
    """Endereza usando el ángulo del texto (minAreaRect de los píxeles oscuros)."""
    inv = cv2.bitwise_not(gray)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if len(coords) < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.2 or abs(angle) > 15:   # nada que hacer, o ángulo absurdo
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("salida")
    ap.add_argument("--min-dim", type=int, default=1800)
    ap.add_argument("--no-deskew", action="store_true")
    ap.add_argument("--no-binarize", action="store_true")
    ap.add_argument("--denoise", type=int, default=7)
    args = ap.parse_args()

    img = cv2.imread(args.entrada, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"error: no pude leer {args.entrada}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Reescala si la resolución es baja (tesseract rinde ~300 dpi).
    if args.min_dim > 0:
        h, w = gray.shape
        if min(h, w) < args.min_dim:
            s = args.min_dim / min(h, w)
            gray = cv2.resize(gray, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)

    # Contraste local (CLAHE): rescata texto tenue y desiguala iluminación.
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    # Denoise preservando bordes de letra.
    if args.denoise > 0:
        gray = cv2.fastNlMeansDenoising(gray, None, h=args.denoise,
                                        templateWindowSize=7, searchWindowSize=21)

    if not args.no_deskew:
        gray = deskew(gray)

    if args.no_binarize:
        out = gray
    else:
        # Binarización adaptativa (gaussiana): buena con sombras/manchas/transparencia.
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, blockSize=31, C=15)

    if not cv2.imwrite(args.salida, out):
        sys.exit(f"error: no pude escribir {args.salida}")
    print(f"preprocesado → {args.salida}  ({out.shape[1]}x{out.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
