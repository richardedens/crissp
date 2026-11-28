# testsuite: proof that the product works

What `crissp/check.sh`, `crissp/check-all.sh` and `crissp/test.sh` run and show. What differs per product is one
configuration, [suites.json](suites.json); everything else here is the framework's and the same in every product.
This repository is a product of its own: its parts are the framework's tests, the deploy template and the audit of the
pinned test tools.

## The product's parts: suites.json

`lib/project.py` reads and checks it; a mistake is a message that says where, never a confusing run.

| Field | What it says |
|---|---|
| `product`, `monogram` | the name in the top bar (default: the folder's name and its first letter) |
| `steps` | the suites of a run, in order: `key`, `label`, `dir` (where it runs), `run` (a bash command), `seconds`, `coverage`, `gate` (the coverage gate holds it), `sources` / `omit` / `fail_under` (what coverage measures, leaves out, the least it accepts), `tests` (where its test files are, for the dashboard), `full_only` (a build, a browser check), `when` (the step exists while this path does), `parallel` / `memory_mb` (its tests spread over the workers this machine has, and what one worker needs) |
| `paths` | what `crissp/check.sh` runs when a file changes: `{match, steps}`, first match wins; a match is a path, a folder `…/` or a name anywhere `*/name` |
| `shared` | the product's shared ground (`{match, why}`): a change there needs the full run |
| `notes` | what needs no test, besides Markdown, the backlog and `docs/` |
| `setup` | `venvs` (a part's `.venv` from its `requirements-dev.txt`), `npm` (a part's `node_modules`), `needs` (`{command, hint}`: never installed, the hint says how) |
| `audit` | what `lib/audit.py` scans: `pip`, `npm`, `fs`, `config`, `dockerfiles`, `images`, `own_images`, `python`; `sast` (the code Semgrep scans) and `sast_rules` (the project's own rules folders); `missing: "skip"` lists a place that is not there yet instead of failing on it (the template names the default places) |
| `texts` | the dashboard's texts for the product (`e2e`, `journeys`) |

A step's command gets `CRISSP_ROOT`, `RESULTS`, `STEP`, `JUNIT`, `COVERAGE_JSON`, `COVERAGE_FILE`, `TOOLS` and the
helper `covered <pytest arguments>` (`lib/steps.sh`): pytest under coverage, lines and branches, of the step's
`sources`, with the JUnit XML and the coverage JSON where the dashboard and the gate read them. `PY=.venv/bin/python
covered …` runs it in a part's own venv; without `PY` it runs with the pinned tools ([requirements.txt](requirements.txt))
through `uv`. The helper `frontend_lint` (`lib/frontend_lint.py`) lints the step's folder with crissp's own tools:
[frontend-lint/](frontend-lint/) pins ESLint 9 and stylelint with their plugins at exact versions, with the lockfile and
the configs. They are installed once per toolkit with `npm ci` into crissp's cache (`CRISSP_CACHE`, else
`$XDG_CACHE_HOME/crissp`, else `~/.cache/crissp`), never into the project, and both always run (no warning allowed).
A product's other frontend commands are its own (`npm test`, …).

**A parallel step** (`"parallel": true`) gets `WORKERS` and `WORKERS_WHY` from `lib/workers.py`: the tightest of the
CPUs less one, three quarters of the available memory per `memory_mb` (default 256), and the step's test files; at
least 1, `CRISSP_WORKERS=<n>` to set it. With more than one, `covered` runs pytest-xdist (`-n $WORKERS --dist loadfile`:
a test file stays on one worker) and coverage measures every worker (`results/coverage-<step>.rc`: `parallel`,
`patch = subprocess`) and combines them, so the gate sees the whole. A part's own venv (`PY=…`) then needs pytest-xdist
and coverage 7.10 or newer. The run prints the count (`passed (11s, 15 workers)`), `crissp check --plan` says it and why,
and `python3 crissp/testsuite/lib/workers.py` shows this machine. Tests in a parallel step must not share a fixed port
or file with each other.

**A database in a parallel step**: one PostgreSQL server for the whole run, never one per worker (a server per worker
costs its memory and start-up per CPU, and `memory_mb` would have to carry it). A session fixture gives each worker a
database per worker on that server, named after `PYTEST_XDIST_WORKER`:

```python
@pytest.fixture(scope="session")
def database_url():
    name = f"test_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"  # test_gw0, test_gw1, … or test_main
    with admin() as db:  # the one server, its maintenance database
        db.execute(f'DROP DATABASE IF EXISTS "{name}"')
        db.execute(f'CREATE DATABASE "{name}"')
    url = SERVER_URL.rsplit("/", 1)[0] + "/" + name
    migrate(url)
    yield url
    with admin() as db:
        db.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
```

The server is the Compose `postgres` service or one the step starts before pytest; the workers only make databases.

The coverage gate is a step of its own, `gate`, right after the last gated step. A step a change touches that is gated
brings the gate along.

## The commands

| Command | What it does |
|---|---|
| `crissp/check.sh --plan` | what changed since the last green commit, what it would run and how long |
| `crissp/check.sh` | runs only what the changes can affect (`lib/impact.py`), then moves the release certificate to this commit |
| `crissp/check-all.sh` | every step: the full run, the release certificate (`lib/release.py`) |
| `crissp/test.sh --dashboard` | the Tests dashboard and the UX suite on one local server, 127.0.0.1:8766 (`CRISSP_DASHBOARD_PORT`); `--ux` opens the UX suite |
| `crissp/testsuite/run.sh [--quick] [step…]` | the steps themselves (after `setup.sh`), without the certificate |

The scripts are doors: the logic is Python in `lib/` (`check.py`, `run.py`, `setup_plan.py`), tested at 100% lines and
branches. Commit first: the checks test what is committed. One run at a time: a lock in `results/.run.lock`.

Without git there is nothing to compare with: `check.sh` says so and stops (exit 2, "run git init and commit");
`check-all.sh` still runs every step for proof, but writes no certificate.

The project is `CRISSP_ROOT`, or the current directory: the scripts export it, so the libraries never find the project
from their own place. The engine's own files (the dashboard page, `crissp/look`, the UX page) are found next to the code.

## What a change runs (lib/impact.py)

In order, the first that matches decides: shared ground of every project (the check, run and setup scripts, the gate,
the certificate, this map, `suites.json`, the pinned tools, `.gitignore`) and the product's `shared` → the full run;
`CHANGELOG.md` and `VERSION` → a check of the release notes; Markdown, the backlog, `docs/`, the coverage baseline and
the product's `notes` → nothing; the product's `paths` → those steps; anything else → the full run, because a targeted
run cannot vouch for a file no rule names.

## The coverage gate (lib/gate.py)

Coverage may only go up, per gated step: its total lines and branches may not drop; a file may not drop; a file at 100%
stays there; a new file starts at 100%; every line added or changed since the baseline's commit is covered and every
branch on it taken both ways (file:line when not); `# pragma: no cover` only with a reason after a dash. Files are named
by their path in the project, however coverage named them. `coverage-baseline.json` starts absent: the first green
full run with a commit sets it. `python3 crissp/testsuite/lib/gate.py --accept "reason"` only for honest reasons.

## The release certificate (lib/release.py)

A full run writes `results/release.json`: the commit, whether tracked code had uncommitted changes or changed during
the run, every step's result. `crissp/deploy.sh` asks `release.py check`: green, at most 7 days old, about exactly the
code being deployed, every step of the product's full run among its results. `crissp/check.sh` moves it on for the
changes it tested.

## Setup (setup.sh, lib/setup_plan.py)

Installs only what is missing or out of date, quiet when everything is there: a part's venv (missing, broken, moved or
stale), a part's `node_modules`; it asks for `uv` and for what `setup.needs` names, never installs them.
`CRISSP_PYTHON` picks the python3 for the venvs.

## The CVE audit (lib/audit.py)

The scanners the product names, decided from their JSON, never their exit codes: pip-audit on resolved requirements
(every finding blocks: PyPI gives no severity), npm audit (high and critical block), trivy fs, config and image (high
and critical block when a fix exists). A scanner that cannot run is a problem, never a pass. `accepted-risks.json`
accepts a finding for at most 90 days, with why and by whom. A project's own `.trivyignore` is read by trivy as usual.
A project's step runs it as `audit run` (a helper of `lib/steps.sh`); the template has it as a full-run step.

trivy (and gitleaks, below) are pinned in `lib/tools.py`: one version, fetched once from its release for this system
(Linux or macOS, x86_64 or arm64), checked against the SHA-256 written there and kept in the crissp cache
(`CRISSP_CACHE`, else `XDG_CACHE_HOME/crissp`, else `~/.cache/crissp`). A download that differs is refused. The version
on a machine's `PATH` is never used. `python3 crissp/testsuite/lib/tools.py path trivy` says where it is.

## Secrets (lib/audit.py secrets)

`audit secrets` runs the pinned gitleaks over the whole git history (over the files when there is no git) and writes
`results/secrets.json`. A finding says where (file, line, commit) and which rule, never the value: gitleaks redacts it
and crissp never reads it. Every finding blocks. The project's own gitleaks configuration counts, as gitleaks reads
it: `.gitleaks.toml` (rules and allowlists), `.gitleaksignore` (fingerprints) and `gitleaks:allow` on a line. A finding
that is no secret is best allowed in `.gitleaks.toml` by its file and value (`[[allowlists]]` with `condition = "AND"`,
`paths` and `regexes`, and a description saying why). A fingerprint names a commit, and a shallow clone (CI, a cloud
container) sees the line in its top commit instead, so there it no longer matches. A real leak is rotated first,
then removed from the history.

## SAST (lib/audit.py sast, sast/)

`audit sast` runs Semgrep (pinned in `lib/audit.py`, through uv) offline: metrics off, no registry, only crissp's own
rules (`sast/python.yaml`, `sast/javascript.yaml`: Python, JavaScript, TypeScript and JSX) plus the rules folders the
project names in `audit.sast_rules`, on the code it names in `audit.sast` (the template: `app`). An ERROR blocks
(eval or exec of a value, a shell built from a value, `yaml.load`, TLS checks off, a debug server); a WARNING is
listed for review (pickle, SQL built from strings, HTML put into the page from a value, `dangerouslySetInnerHTML`,
`mktemp`). A finding names the file, the line, the rule and why, never the code. The project's `.semgrepignore`
counts; without one, Semgrep's defaults apply (they skip tests). Every rule has tests in `sast/tests/` (a line under
`ruleid:` must match, one under `ok:` must not): `audit rules` runs them, and this repository's `sast` step does so
before it scans `src`, `crissp` and `site`.

The backend's lint (`ruff_check`, a helper of `lib/steps.sh`) adds ruff's Bandit rules (`S`) on top of the part's own
ruff configuration; in tests an `assert`, a made-up password and `random` are allowed.

## The dashboard (dashboard/, lib/collect.py, lib/serve.py)

`crissp/test.sh --dashboard` builds the data (`results/data.js`, generated, not in git) and serves the page with the UX
suite on 127.0.0.1 only: `/dashboard/` the Tests, `/ux/` the UX suite, `/look/` the shared look (crissp/look: the
tokens, the Figtree font, the theme, the water), `/results/` the run output. Nothing else of the repository. The page
asks for a stamp every few seconds and reloads when the backlog, `changes.json` or a run's results changed; a change
made while the data was being rebuilt is picked up by the next ask, and a rebuild that failed is said next to the stamp
("not current", with the reason) instead of "live". It never runs a test. Dark by default, light when chosen
(remembered per viewer).

**The board's decisions and findings**: above the lanes, the open decisions (`DECISIONS.md`, not yet taken) and the
findings (`FINDINGS.md`, newest first, with how many are not fixed yet), read with the crissp tool's own parser.

**/activity** (`dashboard/activity.html`, its data `/dashboard/activity.json` from `lib/activity.py`): what this
repository's Claude Code sessions do now, read from their transcripts (the ones written in the last half hour): per
session its title, the last prompt, the orchestrator's latest step and since when (busy while it wrote in the last two
minutes), and every agent it started, running first, each with its own latest step. Only what Claude sent to its tools,
masked like the session pages. The page asks every two seconds while it is open.

**The board's movement** (`lib/movement.py`): every PBI's moves, replayed from the commits that changed the epic files
(with the crissp tool's own parser) plus what the working tree holds beyond the last commit. The board shows "Moved
recently" and, per card, how long it has stood in its column.

**One top bar**: the sections (Tests · Backlog · UX · Workers · Activity · Sessions) are one list in `crissp/look/look.js`;
every page has an empty `<nav class="sections" data-current="…">` that it fills.

**/workers** (`dashboard/workers.html`, its data `/dashboard/workers.json` from `lib/workers.py`): this machine's CPUs,
memory and what is available, how many workers a parallel step gets here and why, and per step that runs or ran (from
`results/timing/`, written by `lib/pytest_plugin/crissp_timing.py`) its workers, how far it is and about how long is
left, its outcomes, and one lane per worker: what it runs now and since when (quiet after a minute), what it finished,
how much of the step it was busy, what failed. It asks every two seconds while it is open.

Tabs: Overview, Backlog (epic → feature → PBI, read by the crissp tool; a PBI an approved UX design became links back
to it), Changes (`changes.json`: what was wrong, the fix, the code, the proof), Tests, Coverage (with the gate), Runs &
logs, Known gaps; and Capabilities, Journeys, Threat model and E2E once the product has them (`results/capabilities.json`,
`results/journeys/`, `threats.json`, an `e2e` step).

`lib/measure.py` and `lib/sessionview.py` turn Claude Code's transcripts into the Sessions pages (`results/sessions/`,
not in git: they hold the prompts).

## Files

| Path | What | Whose |
|---|---|---|
| `suites.json` | the product's parts | the product |
| `changes.json` | every fix with its proof; the known gaps | the product |
| `accepted-risks.json`, `threats.json` | accepted CVEs; the threat model (optional) | the product |
| `coverage-baseline.json` | the gate's baseline (written by the gate) | the product |
| `results/` | everything a run writes | local, not in git |
| `lib/`, `dashboard/`, `run.sh`, `setup.sh`, `requirements.txt`, `tests/` | the engine and its tests | the framework |
