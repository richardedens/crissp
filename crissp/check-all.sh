#!/usr/bin/env bash
# The full run: every step of the product's suites (crissp/testsuite/suites.json), the coverage gate among them.
# It is the foundation crissp/check.sh builds on: a deploy needs one that is at most 7 days old.
#
#   crissp/check-all.sh
#
# Commit first: it tests what is committed (that is what gets deployed). The result is the release certificate,
# crissp/testsuite/results/release.json (crissp/testsuite/lib/release.py). Without git it still runs every step, for
# proof, but writes no certificate. The logic is crissp/testsuite/lib/check.py; this is its door.
set -uo pipefail
ENGINE="$(cd "$(dirname "$0")" && pwd)"  # the framework: this repository's crissp/, or an installed crissp's engine
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"  # the project: crissp sets it, else the folder above
exec python3 "$ENGINE/testsuite/lib/check.py" all "$@"
