#!/usr/bin/env bash
# crissp/testsuite/lint/lint.sh: this repository's lint step (F-38). Dev-only: these tools never reach the package.
#   1. shellcheck on every tracked bash script (a bash/sh shebang, or a .sh file), pinned in requirements.txt here
#      (shellcheck-py), run with uv
#   2. ESLint on every tracked JavaScript file (the shared look, the Tests dashboard, the UX suite's page), pinned in
#      package.json and package-lock.json here; npm ci when node_modules is missing or older than the lock
# Without uv or Node.js a step is FAILED with how to get it, never a silent pass.
#
#   lint.sh                     lint everything; exit 0 only when both are clean
#   lint.sh --list shell|js     the files it lints, one per line
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${CRISSP_ROOT:-$(cd "$HERE/../../.." && pwd)}"
cd "$ROOT" || exit 1

shell_files() {
  local f first
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    if [[ "$f" == *.sh ]]; then echo "$f"; continue; fi
    IFS= read -r first < "$f" || true
    if [[ "$first" == '#!'*bash* || "$first" =~ ^#!.*/sh[[:space:]]*$ ]]; then echo "$f"; fi
  done < <(git ls-files)
}
js_files() { git ls-files '*.js' '*.mjs' | grep -v '^crissp/testsuite/lint/'; }

if [ "${1:-}" = "--list" ]; then
  case "${2:-}" in
    shell) shell_files ;;
    js) js_files ;;
    *) echo "usage: lint.sh [--list shell|js]" >&2; exit 2 ;;
  esac
  exit 0
fi

failed=0
bad() { echo "FAILED: $*"; failed=1; }

echo "== shellcheck (every bash script)"
mapfile -t scripts < <(shell_files)
if command -v uv >/dev/null 2>&1; then
  # -s bash: a sourced file without a shebang (lib/steps.sh) is bash too; -x follows what a script sources
  if uv run --quiet --no-project --with-requirements "$HERE/requirements.txt" shellcheck -s bash -x "${scripts[@]}"; then
    echo "ok: shellcheck, ${#scripts[@]} scripts"
  else
    bad "shellcheck"
  fi
else
  bad "uv is not installed: shellcheck cannot run (https://docs.astral.sh/uv/)"
fi

echo "== ESLint (every JavaScript file)"
mapfile -t sources < <(js_files)
if command -v npm >/dev/null 2>&1; then
  record="$HERE/node_modules/.package-lock.json"
  if [ ! -f "$record" ] || [ "$HERE/package-lock.json" -nt "$record" ]; then
    (cd "$HERE" && npm ci --silent --no-audit --no-fund) || bad "npm ci in crissp/testsuite/lint"
  fi
  if [ -x "$HERE/node_modules/.bin/eslint" ]; then
    if "$HERE/node_modules/.bin/eslint" --no-warn-ignored -c "$HERE/eslint.config.js" "${sources[@]}"; then
      echo "ok: ESLint, ${#sources[@]} files"
    else
      bad "ESLint"
    fi
  fi
else
  bad "Node.js (npm) is not installed: ESLint cannot run (https://nodejs.org, 20 or newer)"
fi

exit "$failed"
