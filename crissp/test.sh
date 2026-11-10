#!/usr/bin/env bash
# crissp/test.sh --dashboard   the Tests dashboard (what the last runs proved, the backlog board) and the UX suite, on one
#                              local server: builds the dashboard's data, serves it on 127.0.0.1 and opens it
#                              (CRISSP_DASHBOARD_PORT, default 8766); it stays current: a changed backlog, changes.json
#                              or run result rebuilds it and the page reloads
# crissp/test.sh --ux          the same server, opened on the UX suite (crissp/ux.sh does this)
# Running the tests is crissp/check.sh (what changed) or crissp/check-all.sh (everything): this script only shows what they proved.
set -euo pipefail
ENGINE="$(cd "$(dirname "$0")" && pwd)"  # the framework: this repository's crissp/, or an installed crissp's engine
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"  # the project: crissp sets it, else the folder above
SUITE="$ENGINE/testsuite"
ASKED=${CRISSP_DASHBOARD_PORT:-8766}
case "${1:-}" in
  --dashboard) PAGE=dashboard ;;
  --ux) PAGE=ux ;;
  *) sed -n '2,6p' "$0" | sed 's/^# //' >&2; exit 2 ;;
esac
python3 -I "$SUITE/lib/measure.py" >/dev/null
python3 -I "$SUITE/lib/collect.py"
# which port: this project's dashboard is reused, another project's is left alone (the next port), F-09 (lib/place.py)
read -r PORT STATE NOTE <<<"$(python3 -I "$SUITE/lib/place.py" "$ASKED")"
URL="http://127.0.0.1:$PORT/$PAGE/"
open_url() {
  [ "${CRISSP_NO_BROWSER:-}" = 1 ] && return 0  # the tests: never a real browser
  if command -v open >/dev/null; then open "$URL"; else xdg-open "$URL" >/dev/null 2>&1; fi
}
[ -n "$NOTE" ] && [ "$STATE" != taken ] && echo "$NOTE: this project gets port $PORT."
if [ "$STATE" = same ]; then  # this project's dashboard is served live already
  echo "Dashboard: $URL"
  open_url
  exit 0
fi
if [ "$STATE" = taken ]; then
  # a program that is no dashboard holds the port (an old server from a moved folder, another program), or no port is left
  holder=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)
  echo "Port $PORT is in use${holder:+ by pid $holder} but does not serve this dashboard${NOTE:+ ($NOTE, and no free port after it)}: stop that process, or set CRISSP_DASHBOARD_PORT." >&2
  exit 1
fi
echo "Dashboard: $URL   (Ctrl-C to stop)"
( sleep 1; open_url ) &
exec python3 -I "$SUITE/lib/serve.py" --port "$PORT"
