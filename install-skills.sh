#!/usr/bin/env bash
# install-skills.sh — Instala las skills de La Forja en este equipo.
# Copia skills/<nombre> -> ~/.claude/skills/<nombre> (scope user = global).
#
# Uso:  bash install-skills.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/skills"
DST="$HOME/.claude/skills"

mkdir -p "$DST"
echo "Instalando skills de La Forja en: $DST"

count=0
for dir in "$SRC"/*/; do
    name="$(basename "$dir")"
    rm -rf "$DST/$name"
    cp -r "$dir" "$DST/$name"
    rm -rf "$DST/$name/__pycache__"
    echo "  ✅ $name"
    count=$((count + 1))
done

echo "Listo: $count skill(s) instaladas. Reabre Claude Code si estaba abierto."
echo
echo "NOTA: las skills usan herramientas externas que NO vienen en este repo."
echo "Revisa skills/README.md para instalarlas (pandoc, poppler, docling, etc.)."
