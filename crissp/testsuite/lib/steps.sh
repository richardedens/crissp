# What every step's command can use (lib/run.py runs each command with bash and BASH_ENV pointing here).
#
#   covered <pytest arguments…>
#       pytest under coverage, lines and branches, of the step's sources (COVERAGE_SOURCES, COVERAGE_OMIT): the JUnit XML
#       to $JUNIT and the coverage JSON to $COVERAGE_JSON (the dashboard and the gate read them), the report in the log,
#       red below COVERAGE_FAIL_UNDER when the step names one. It runs with $PY when set (a part's own venv:
#       PY=.venv/bin/python covered …), else with the pinned test tools: uv run --with-requirements $TOOLS.
#       With WORKERS above 1 (a parallel step, lib/run.py: what this machine gives it) the tests spread over that many
#       pytest-xdist workers, a test file on one worker (--dist loadfile), and coverage measures every worker
#       (results/coverage-<step>.rc: parallel, patch = subprocess), then combines them: the gate sees the whole.
py() {
  if [ -n "${PY:-}" ]; then "$PY" "$@"; else uv run --quiet --no-project --with-requirements "$TOOLS" python "$@"; fi
}
covered() {
  local status=0
  if [ "${WORKERS:-1}" -gt 1 ] 2>/dev/null; then
    local rc="$RESULTS/coverage-$STEP.rc"
    { printf '[run]\nbranch = true\nparallel = true\npatch = subprocess\ndisable_warnings = no-data-collected\n'
      if [ -n "${COVERAGE_SOURCES:-}" ]; then printf 'source = %s\n' "$COVERAGE_SOURCES"; fi
      if [ -n "${COVERAGE_OMIT:-}" ]; then printf 'omit = %s\n' "$COVERAGE_OMIT"; fi; } > "$rc"
    py -m coverage run --rcfile="$rc" -m pytest -q -p no:cacheprovider -n "$WORKERS" --dist loadfile \
      --junitxml="$JUNIT" "$@" || status=$?
    py -m coverage combine --rcfile="$rc" -q || status=1
    py -m coverage json --rcfile="$rc" -q -o "$COVERAGE_JSON" || status=1
    py -m coverage report --rcfile="$rc" --show-missing ${COVERAGE_FAIL_UNDER:+--fail-under="$COVERAGE_FAIL_UNDER"} || status=1
    return $status
  fi
  py -m coverage run --branch ${COVERAGE_SOURCES:+--source="$COVERAGE_SOURCES"} ${COVERAGE_OMIT:+--omit="$COVERAGE_OMIT"} \
    -m pytest -q -p no:cacheprovider --junitxml="$JUNIT" "$@" || status=$?
  py -m coverage json -q -o "$COVERAGE_JSON" || status=1  # also on red: the gate says what dropped
  py -m coverage report --show-missing ${COVERAGE_FAIL_UNDER:+--fail-under="$COVERAGE_FAIL_UNDER"} || status=1
  return $status
}
