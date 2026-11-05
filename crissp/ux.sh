#!/usr/bin/env bash
# The UX suite: virtual people walk the running product, debate it, advise per walk and design on request.
#
#   crissp/ux.sh                          open the UX suite (the same local server as the Tests dashboard, on /ux/)
#   crissp/ux.sh --list                   the product, the team and the walks (crissp/uxsuite/team.json, walks/)
#   crissp/ux.sh --status                 what the team does now, what waits, how many rounds, designs and verdicts
#   crissp/ux.sh --shoot <walk>           take the walk's screenshots on a laptop and a phone (the product must run)
#   crissp/ux.sh --round <walk>           a round on a walk: review, debate, advice (now, or queued)
#   crissp/ux.sh --propose <walk> [focus] a design for a walk, with an optional focus
# Rounds and designs are headless Claude Code runs that cost tokens: the product owner asks for them, never a schedule.
# What the suite makes goes to crissp/uxsuite/results/ (not in git).
set -euo pipefail
ENGINE="$(cd "$(dirname "$0")" && pwd)"  # the framework: this repository's crissp/, or an installed crissp's engine
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"  # the project: crissp sets it, else the folder above
case "${1:-}" in
  "") exec "$ENGINE/test.sh" --ux ;;
  --list|--status|--shoot|--round|--propose)
    cmd=${1#--}; shift
    exec python3 -I "$ENGINE/uxsuite/cli.py" "$cmd" "$@" ;;
  *) sed -n '4,9p' "$0" | sed 's/^# //' >&2; exit 2 ;;
esac
