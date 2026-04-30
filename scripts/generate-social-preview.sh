#!/usr/bin/env bash
# Regenerate media/social/data-architecture-landscape.png from data-landscape.pdf.
#
# Run after refreshing data-landscape.pdf so the og:image stays in sync:
#
#     ./scripts/generate-social-preview.sh
#
# Requires: pdftoppm (poppler) and magick (ImageMagick).
#   brew install poppler imagemagick
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PDF="$ROOT/data-landscape.pdf"
OUT="$ROOT/media/social/data-architecture-landscape.png"

[ -f "$PDF" ] || { echo "Missing $PDF — run scripts/generate-pdf.py first." >&2; exit 1; }
command -v pdftoppm >/dev/null || { echo "Need pdftoppm: brew install poppler" >&2; exit 1; }
command -v magick   >/dev/null || { echo "Need magick: brew install imagemagick" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Rasterise page 1 at 200 DPI, then letterbox into 1200x630 (standard og:image).
pdftoppm -png -r 200 -f 1 -l 1 "$PDF" "$TMP/page"
magick "$TMP/page-1.png" \
  -resize 1200x630 \
  -background white -gravity center -extent 1200x630 \
  -strip \
  "$OUT"

bytes=$(wc -c < "$OUT" | tr -d ' ')
echo "Wrote ${OUT#$ROOT/} (${bytes} bytes, 1200x630)."
