---
name: ocr
description: OCR de máxima calidad para libros escaneados de mala calidad y para arreglar OCRs corruptos. Auto-diagnostica el escaneo, preprocesa la imagen (deskew, contraste, binarización), usa modelos tessdata_best multilingües (latín, griego, árabe, persa…) y, si hace falta, el motor RapidOCR; detecta texto corrupto para corregirlo con criterio. Activa con "/ocr" o intención como "haz OCR de este escaneo", "este PDF escaneado salió mal", "arregla este OCR corrupto", "el texto quedó ilegible".
---

# OCR de alta calidad (suite La Forja)

Para libros **escaneados de mala calidad** y **OCRs corruptos**. Va mucho más
allá del `ocrmypdf` básico: preprocesa la imagen, usa modelos **best**
multilingües y escala a un motor más fuerte cuando hace falta. El objetivo es
texto fiel — nunca inventar ni "corregir" a ciegas (dañaría términos válidos).

## Recursos (los deja `tools/ocr_setup.sh`; correr una vez por equipo)

- **Modelos best:** `TESSDATA_PREFIX=~/.local/share/forja-tessdata`
  (idiomas: eng spa lat grc ell ara fas deu fra ita osd — más precisos que los del sistema).
- **Python OCR** (OpenCV/RapidOCR): `~/.local/share/forja-ocr-venv/bin/python`.
- Herramientas en `tools/`: `ocr_preprocess.py`, `ocr_corruption.py`.

Define al empezar:
```bash
export TESSDATA_PREFIX=~/.local/share/forja-tessdata
T=/mnt/c/ideas/_La_Forja/tools ; PYV=~/.local/share/forja-ocr-venv/bin/python
```
Si falta algo: `bash $T/ocr_setup.sh`.

## Paso 0 · Diagnostica el caso

- **PDF/imagen escaneada sin texto** → pipeline de OCR (Paso 1).
- **Texto ya OCR-eado pero corrupto** → Paso 3 (detectar + corregir con criterio).
- **Idioma(s):** infiere del contenido y del usuario. Por defecto `spa+eng`;
  añade `lat`, `grc` (griego antiguo), `ell`, `ara`, `fas` según el material
  (alquimia→lat; astrología helenística/filosofía→grc; Rumi/medieval→fas+ara).
  Combina con `+`: `-l lat+grc+eng`.

## Paso 1 · OCR estándar afinado (primer intento)

```bash
ocrmypdf --deskew --clean --rotate-pages --optimize 1 \
    -l spa+eng+lat "entrada.pdf" "salida_ocr.pdf"      # ajusta -l a los idiomas
```
`ocrmypdf` usará automáticamente los modelos best por `TESSDATA_PREFIX`. Extrae
el texto (`pdftotext salida_ocr.pdf -`) y evalúa calidad con `$T/ocr_corruption.py`.

> **Escaneo largo o equipo que se puede apagar:** usa
> `python3 $T/ocr_incremental.py entrada.pdf --lang eng` en vez de `ocrmypdf`
> directo — corre por **lotes de páginas con checkpoint + resume** (ocrmypdf a
> secas no escribe nada hasta el final, así que una interrupción lo pierde todo).
> Reanuda solo con volver a ejecutarlo. Modo `--mode redo` (por defecto) re-OCR-ea
> para sustituir una capa de texto MALA (p. ej. Internet Archive) conservando la
> imagen; `--mode skip` solo añade capa a páginas sin texto. Usa los modelos best
> automáticamente. Ideal cuando hay que **pausar** a mitad.

## Paso 2 · Escalado para escaneos MUY malos

Si el Paso 1 deja mucho texto sospechoso, procesa página por página con
preprocesado OpenCV antes del OCR:

```bash
pdftoppm -r 300 -png "entrada.pdf" /tmp/pg              # rasteriza a imágenes
for f in /tmp/pg-*.png; do
    $PYV $T/ocr_preprocess.py "$f" "${f%.png}_clean.png"   # deskew+CLAHE+binariza
done
# luego OCR de las limpias (tesseract por página, o reensamblar a PDF):
for f in /tmp/pg-*_clean.png; do tesseract "$f" "${f%.png}" -l spa+eng+lat; done
cat /tmp/pg-*_clean.txt > "salida.txt"
```
Opciones de `ocr_preprocess.py`: `--min-dim` (reescala si DPI bajo), `--no-binarize`
(texto tenue/antiguo, deja gris), `--denoise N`, `--no-deskew`.

**Motor alternativo (RapidOCR)** cuando tesseract falla aun con buena imagen:
```bash
$PYV -c "from rapidocr_onnxruntime import RapidOCR; r=RapidOCR();
res,_=r('/tmp/pg-1_clean.png'); print('\n'.join(t[1] for t in res) if res else '')"
```
Compara su salida con la de tesseract y quédate con la mejor (criterio).

## Paso 3 · Arreglar un OCR ya corrupto

1. Si **conservas el escaneo original**, RE-OCR (Pasos 1–2) casi siempre supera
   cualquier arreglo del texto — prefiérelo.
2. Si **solo tienes el texto**, localiza lo dañado:
   ```bash
   python3 $T/ocr_corruption.py capitulo.md --umbral 0.35
   ```
   Marca líneas por densidad de símbolos, "palabras" sin vocales, texto espaciado,
   letra+dígito. **Corrige a mano SOLO esas, con criterio.**
3. **NUNCA autocorrección ciega** (spellcheck masivo): en textos académicos y
   multilingües "arreglaría" arcaísmos, latín, griego o transliteraciones válidas
   y **degradaría la calidad**. Corrige leyendo, conservando lo dudoso-pero-válido.

## Integración

Es el motor de OCR de [[forja]] (cuando un PDF no tiene capa de texto). Tras
obtener texto limpio, sigue el flujo normal: convertir a markdown por capítulo →
[[traducir-md]] / estudio. Ver [[forja-flujo]] para el encadenado automático.

## Límite honesto

El preprocesado y los modelos best suben mucho la precisión, pero un original
ilegible tiene un techo. Cuando el texto es dudoso, **márcalo como incierto** en
vez de adivinar; la fidelidad manda sobre la apariencia de completitud.
