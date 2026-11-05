# What every step's command can use (lib/run.py runs each command with bash and BASH_ENV pointing here).
#
#   covered <pytest arguments…>
#       pytest under coverage, lines and branches, of the step's sources (COVERAGE_SOURCES, COVERAGE_OMIT): the JUnit XML
#       to $JUNIT and the coverage JSON to $COVERAGE_JSON (the dashboard and the gate read them), the report in the log,
#       red below COVERAGE_FAIL_UNDER when the step names one. It runs with $PY when set (a part's own venv:
#       PY=.venv/bin/python covered …), else with the pinned test tools: uv run --with-requirements $TOOLS.
py() {
  if [ -n "${PY:-}" ]; then "$PY" "$@"; else uv run --quiet --no-project --with-requirements "$TOOLS" python "$@"; fi
}
covered() {
  local status=0
  py -m coverage run --branch ${COVERAGE_SOURCES:+--source="$COVERAGE_SOURCES"} ${COVERAGE_OMIT:+--omit="$COVERAGE_OMIT"} \
    -m pytest -q -p no:cacheprovider --junitxml="$JUNIT" "$@" || status=$?
  py -m coverage json -q -o "$COVERAGE_JSON" || status=1  # also on red: the gate says what dropped
  py -m coverage report --show-missing ${COVERAGE_FAIL_UNDER:+--fail-under="$COVERAGE_FAIL_UNDER"} || status=1
  return $status
}
