#!/usr/bin/env bash
# Install what the project's suites need, and only what is missing or out of date: quiet when everything is in place,
# it says what it changed, and when something cannot be installed it says how to fix it and exits non-zero.
#
#   crissp/testsuite/setup.sh
#
# check.sh, check-all.sh and run.sh run it first. lib/setup_plan.py decides and does it (uv, the parts' venvs and
# node_modules, the commands the steps need: crissp/testsuite/suites.json, setup).
set -uo pipefail
SUITE="$(cd "$(dirname "$0")" && pwd)"
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$(dirname "$SUITE")")}"
exec python3 "$SUITE/lib/setup_plan.py" apply
