# What every step's command can use (lib/run.py runs each command with bash and BASH_ENV pointing here).
#
#   covered <pytest arguments…>
#       pytest under coverage, lines and branches, of the step's sources (COVERAGE_SOURCES, COVERAGE_OMIT): the JUnit XML
#       to $JUNIT and the coverage JSON to $COVERAGE_JSON (the dashboard and the gate read them), the report in the log,
#       red below COVERAGE_FAIL_UNDER when the step names one. It runs with $PY when set (a part's own venv:
#       PY=.venv/bin/python covered …), else with the pinned test tools: uv run --with-requirements $TOOLS.
#       Coverage is measured one way, on one worker or many (results/coverage-<step>.rc: parallel, patch = subprocess,
#       then combine): the gate sees the same numbers on every machine. With WORKERS above 1 (a parallel step, lib/run.py:
#       what this machine gives it) the tests spread over that many pytest-xdist workers, a file on one (--dist loadfile).
#       With CRISSP_PLUGINS (lib/run.py) it loads crissp_timing: every test as it finishes, per worker, for /workers.
#   frontend_lint [<folder>]
#       the frontend linted with crissp's own pinned tools (lib/frontend_lint.py: ESLint and stylelint, installed once
#       into crissp's cache, never into the project), in the step's folder.
#
#   audit run | secrets | sast
#       crissp's security scans for the project (lib/audit.py, next to this file wherever crissp is installed): run is
#       the CVE and misconfiguration audit, secrets the git history, sast the code. Each writes results/<scan>.json
#       and is red on what blocks; suites.json `audit` says what each scans.
#
#   ruff_check <paths…>
#       ruff (the pinned one, through py) on top of the part's own ruff configuration, with ruff's Bandit rules (S)
#       added: a backend's lint is also a security lint. Tests may assert and use made-up secrets and random numbers;
#       nothing else is allowed there that is not allowed in the code.
CRISSP_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
audit() { python3 "$CRISSP_LIB/audit.py" "$@"; }
ruff_check() {
  local ignores=() pattern code
  for pattern in "**/tests/**" "**/test_*.py" "**/conftest.py"; do
    for code in S101 S105 S106 S107 S311; do ignores+=(--extend-per-file-ignores "$pattern:$code"); done
  done
  py -m ruff check --no-cache --extend-select S "${ignores[@]}" "$@"
}
py() {
  if [ -n "${PY:-}" ]; then "$PY" "$@"; else uv run --quiet --no-project --with-requirements "$TOOLS" python "$@"; fi
}
covered() {
  local status=0 rc="$RESULTS/coverage-${STEP:-step}.rc" spread=()
  { printf '[run]\nbranch = true\nparallel = true\npatch = subprocess\ndisable_warnings = no-data-collected\n'
    if [ -n "${COVERAGE_SOURCES:-}" ]; then printf 'source = %s\n' "$COVERAGE_SOURCES"; fi
    if [ -n "${COVERAGE_OMIT:-}" ]; then printf 'omit = %s\n' "$COVERAGE_OMIT"; fi; } > "$rc"
  if [ "${WORKERS:-1}" -gt 1 ] 2>/dev/null; then spread=(-n "$WORKERS" --dist loadfile); fi
  if [ -n "${CRISSP_PLUGINS:-}" ]; then  # every test as it finishes, per worker (lib/pytest_plugin/crissp_timing.py)
    local PYTHONPATH="$CRISSP_PLUGINS${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONPATH
    spread=(-p crissp_timing ${spread[@]+"${spread[@]}"})
  fi
  py -m coverage run --rcfile="$rc" -m pytest -q -p no:cacheprovider ${spread[@]+"${spread[@]}"} --junitxml="$JUNIT" "$@" \
    || status=$?
  py -m coverage combine --rcfile="$rc" -q || status=1
  py -m coverage json --rcfile="$rc" -q -o "$COVERAGE_JSON" || status=1  # also on red: the gate says what dropped
  py -m coverage report --rcfile="$rc" --show-missing ${COVERAGE_FAIL_UNDER:+--fail-under="$COVERAGE_FAIL_UNDER"} || status=1
  return $status
}
frontend_lint() {
  py "$(dirname "${BASH_SOURCE[0]}")/frontend_lint.py" "$@"
}
