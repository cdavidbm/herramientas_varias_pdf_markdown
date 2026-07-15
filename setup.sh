#!/usr/bin/env bash
# setup.sh — Prepara La Forja COMPLETA en una máquina nueva. Idempotente.
#
# Clona el repo en  ~/… o  C:\ideas\_La_Forja  (mismo path que la otra máquina,
# para que las skills encuentren tools/) y corre:  bash setup.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "== La Forja · setup en $REPO =="
echo

# --- 1) Dependencias base (requieren root; solo se reportan si faltan) ---------
echo "1) Dependencias base del sistema"
falta=()
for b in pandoc pdftotext pdfinfo mutool ocrmypdf tesseract qpdf ffmpeg; do
    if command -v "$b" >/dev/null; then echo "   ✓ $b"; else echo "   ✗ $b"; falta+=("$b"); fi
done
if ((${#falta[@]})); then
    echo "   → instala (con root):"
    echo "     sudo apt-get install -y poppler-utils mupdf-tools pandoc ocrmypdf tesseract-ocr qpdf ffmpeg"
fi
command -v uv   >/dev/null && echo "   ✓ uv"   || echo "   ✗ uv   → curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v node >/dev/null && echo "   ✓ node" || echo "   ✗ node (para el MCP de YouTube)"
echo

# --- 2) Conversores de alta fidelidad (sin root, vía uv) ----------------------
echo "2) Docling + markitdown + yt-dlp"
if command -v uv >/dev/null; then
    command -v docling    >/dev/null || uv tool install docling
    command -v markitdown >/dev/null || uv tool install 'markitdown[all]'
    command -v yt-dlp     >/dev/null || uv tool install yt-dlp
    echo "   ✓ docling / markitdown / yt-dlp"
else
    echo "   ⚠ sin uv: sáltate este paso hasta instalar uv"
fi
echo

# --- 2b) Librerías Python LIGERAS de los tools (requirements.txt, sin venv) ----
# EPUB (beautifulsoup4), RTF (striprtf) y estructura por fuente (pdfminer.six).
# Sin ellas, epub_to_markdown / rtf_to_markdown / pdf_headings crashean en una
# máquina limpia. Las pesadas (opencv, faster-whisper) van en venvs (pasos 4/4b).
echo "2b) Librerías Python ligeras (EPUB / RTF / estructura por fuente)"
# import-name  paquete-pip
pydeps=("bs4 beautifulsoup4" "striprtf striprtf" "pdfminer pdfminer.six")
for pair in "${pydeps[@]}"; do
    mod="${pair%% *}"; pkg="${pair##* }"
    if python3 -c "import $mod" 2>/dev/null; then
        echo "   ✓ $pkg"
    elif python3 -m pip install --user "$pkg" >/dev/null 2>&1; then
        echo "   ✓ $pkg instalado"
    else
        echo "   ✗ $pkg → python3 -m pip install --user $pkg"
    fi
done
echo

# --- 3) Skills → ~/.claude/skills --------------------------------------------
echo "3) Skills"
bash "$REPO/install-skills.sh" | sed 's/^/   /'
echo

# --- 4) OCR de alta calidad (modelos best + venv OpenCV/RapidOCR) -------------
echo "4) OCR (modelos multilingües + OpenCV/RapidOCR)"
bash "$REPO/tools/ocr_setup.sh" | sed 's/^/   /'
echo

# --- 4b) ASR (transcribir audio de videos SIN subtítulos) ---------------------
echo "4b) ASR de YouTube (faster-whisper, para videos sin subtítulos)"
bash "$REPO/tools/asr_setup.sh" | sed 's/^/   /'
echo

# --- 5) MCP (se cargan al REINICIAR Claude Code) ------------------------------
echo "5) MCP de Claude Code"
if command -v claude >/dev/null; then
    claude mcp add -s user markitdown -- uvx markitdown-mcp >/dev/null 2>&1 \
        && echo "   ✓ markitdown" || echo "   · markitdown (ya estaba o falló)"
    claude mcp add -s user youtube -- npx -y @anaisbetts/mcp-youtube >/dev/null 2>&1 \
        && echo "   ✓ youtube" || echo "   · youtube (ya estaba o falló)"
else
    echo "   ⚠ CLI 'claude' no encontrado; añade los MCP a mano luego"
fi
echo

# --- 6) Contexto de usuario global (verídico; no pisa uno existente) ----------
echo "6) Contexto de usuario (~/.claude/CLAUDE.md)"
if [ -f "$HOME/.claude/CLAUDE.md" ]; then
    echo "   · ya existe, no lo toco"
else
    mkdir -p "$HOME/.claude"
    cp "$REPO/docs/contexto-usuario.md" "$HOME/.claude/CLAUDE.md" \
        && echo "   ✓ copiado (revísalo/ajústalo a tu gusto)"
fi
echo

echo "== Pasos manuales que faltan =="
((${#falta[@]})) && echo "  • Instala las deps con root (línea sudo apt-get de arriba)."
echo "  • NotebookLM (opcional): uv tool install \"notebooklm-py[browser]\" &&"
echo "      ~/.local/share/uv/tools/notebooklm-py/bin/playwright install chromium &&"
echo "      notebooklm skill install && notebooklm login   (cuenta cdavidbm@gmail.com)"
echo "  • REINICIA Claude Code para cargar skills y MCP."
echo "  • Abre Claude dentro de esta carpeta: su CLAUDE.md se carga solo."
