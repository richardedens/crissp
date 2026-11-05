#!/usr/bin/env bash
# Run the project's suites and write what the gate, the certificate and the dashboard read (crissp/testsuite/results).
#   crissp/testsuite/run.sh                 everything: the full run of crissp/check-all.sh
#   crissp/testsuite/run.sh --quick         the steps that are not full-run only
#   crissp/testsuite/run.sh --quick <step…> only these steps (crissp/check.sh passes the ones a change touches)
# The steps are the project's (crissp/testsuite/suites.json); lib/run.py runs them, after setup.sh installed what they need.
set -uo pipefail
SUITE="$(cd "$(dirname "$0")" && pwd)"
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$(dirname "$SUITE")")}"
"$SUITE/setup.sh" || exit 1
exec python3 "$SUITE/lib/run.py" "$@"
