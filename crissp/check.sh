#!/usr/bin/env bash
# Test only what changed since the last green state, then mark this commit as tested (deploy.sh asks for that).
#
#   crissp/check.sh          show the plan, run it, and on green advance the release certificate to this commit
#   crissp/check.sh --plan   only show what it would run and roughly how long it takes
#
# What runs depends on what changed (crissp/testsuite/lib/impact.py, from the product's parts in
# crissp/testsuite/suites.json): notes (the backlog, docs/, Markdown) nothing; the release notes (CHANGELOG.md, VERSION)
# a check of the two files; a part of the product the steps its `paths` rule names (a gated step brings the coverage
# gate); shared ground (these scripts, the gate, the certificate, the configuration, what the product calls shared,
# anything unmapped) → it says so and stops with exit 3: run crissp/check-all.sh.
# Commit first: it tests what is committed (that is what gets deployed). Without git it says so and stops.
# The logic is crissp/testsuite/lib/check.py; this is its door.
set -uo pipefail
ENGINE="$(cd "$(dirname "$0")" && pwd)"  # the framework: this repository's crissp/, or an installed crissp's engine
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"  # the project: crissp sets it, else the folder above
exec python3 "$ENGINE/testsuite/lib/check.py" changed "$@"
