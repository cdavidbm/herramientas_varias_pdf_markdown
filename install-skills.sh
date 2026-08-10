#!/usr/bin/env bash
# install-skills.sh — Instala las skills de La Forja en este equipo.
# Copia skills/<nombre> -> ~/.claude/skills/<nombre> (scope user = global).
#
# PODA lo que ya no exista en el repo, y por eso lleva MANIFIESTO. Antes solo
# copiaba: una skill retirada o renombrada se quedaba instalada para siempre,
# desfasada y compitiendo con la nueva por la misma intención. Ese es el mismo
# fallo de obsolescencia silenciosa que hemos ido corrigiendo por todo el repo.
#
# El manifiesto (`.forja-skills` en el destino) registra qué instaló ESTE script.
# Así la poda solo puede tocar lo que vino de aquí: las skills ajenas al repo
# —instaladas a mano o por otra vía— no se rozan, aunque estén en la misma
# carpeta. Sin esa lista, «borrar lo que no está en el repo» se llevaría por
# delante skills que nada tienen que ver con La Forja.
#
# Uso:  bash install-skills.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/skills"
DST="$HOME/.claude/skills"
MANIFIESTO="$DST/.forja-skills"

mkdir -p "$DST"
echo "Instalando skills de La Forja en: $DST"

nuevas=""
count=0
for dir in "$SRC"/*/; do
    name="$(basename "$dir")"
    rm -rf "$DST/$name"
    cp -r "$dir" "$DST/$name"
    rm -rf "$DST/$name/__pycache__"
    echo "  ✅ $name"
    nuevas="$nuevas$name"$'\n'
    count=$((count + 1))
done

# Poda: lo que este script instaló alguna vez y ya no está en el repo.
podadas=0
if [ -f "$MANIFIESTO" ]; then
    while IFS= read -r vieja; do
        [ -z "$vieja" ] && continue
        if ! printf '%s' "$nuevas" | grep -qx "$vieja"; then
            if [ -d "$DST/$vieja" ]; then
                rm -rf "$DST/$vieja"
                echo "  🗑  $vieja (retirada del repo)"
                podadas=$((podadas + 1))
            fi
        fi
    done < "$MANIFIESTO"
fi

printf '%s' "$nuevas" > "$MANIFIESTO"

echo "Listo: $count skill(s) instaladas${podadas:+, $podadas podada(s)}. Reabre Claude Code si estaba abierto."
echo
echo "NOTA: las skills usan herramientas externas que NO vienen en este repo."
echo "Revisa skills/README.md para instalarlas (pandoc, poppler, docling, etc.)."
