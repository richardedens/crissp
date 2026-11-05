#!/usr/bin/env bash
# Build the website into site/_site: the pages plus the framework's own look (crissp/look), so the site and the
# dashboard are one look and nothing is copied by hand. Used by .github/workflows/pages.yml; locally:
#   site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOOK="$HERE/../crissp/look"
OUT="$HERE/_site"
rm -rf "$OUT" && mkdir -p "$OUT/look"
cp "$HERE/index.html" "$HERE/site.css" "$OUT/"
cp "$LOOK/look.css" "$LOOK/look.js" "$LOOK/water.js" "$LOOK/figtree-latin-variable.woff2" "$LOOK/LICENSE-figtree.txt" "$OUT/look/"
mkdir -p "$OUT/images" && cp "$HERE/../docs/images/"* "$OUT/images/"
touch "$OUT/.nojekyll"
echo "site: $OUT"
