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
| `steps` | the suites of a run, in order: `key`, `label`, `dir` (where it runs), `run` (a bash command), `seconds`, `coverage`, `gate` (the coverage gate holds it), `sources` / `omit` / `fail_under` (what coverage measures, leaves out, the least it accepts), `tests` (where its test files are, for the dashboard), `full_only` (a build, a browser check), `when` (the step exists while this path does) |
| `paths` | what `crissp/check.sh` runs when a file changes: `{match, steps}`, first match wins; a match is a path, a folder `…/` or a name anywhere `*/name` |
| `shared` | the product's shared ground (`{match, why}`): a change there needs the full run |
| `notes` | what needs no test, besides Markdown, the backlog and `docs/` |
| `setup` | `venvs` (a part's `.venv` from its `requirements-dev.txt`), `npm` (a part's `node_modules`), `needs` (`{command, hint}`: never installed, the hint says how) |
| `audit` | what `lib/audit.py` scans: `pip`, `npm`, `fs`, `config`, `dockerfiles`, `images`, `own_images`, `python` |
| `texts` | the dashboard's texts for the product (`e2e`, `journeys`) |

A step's command gets `CRISSP_ROOT`, `RESULTS`, `STEP`, `JUNIT`, `COVERAGE_JSON`, `COVERAGE_FILE`, `TOOLS` and the
helper `covered <pytest arguments>` (`lib/steps.sh`): pytest under coverage, lines and branches, of the step's
`sources`, with the JUnit XML and the coverage JSON where the dashboard and the gate read them. `PY=.venv/bin/python
covered …` runs it in a part's own venv; without `PY` it runs with the pinned tools ([requirements.txt](requirements.txt))
through `uv`. A product with a frontend writes its own commands (`npm run --silent lint`, …).

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
accepts a finding for at most 90 days, with why and by whom.

## The dashboard (dashboard/, lib/collect.py, lib/serve.py)

`crissp/test.sh --dashboard` builds the data (`results/data.js`, generated, not in git) and serves the page with the UX
suite on 127.0.0.1 only: `/dashboard/` the Tests, `/ux/` the UX suite, `/look/` the shared look (crissp/look: the
tokens, the Figtree font, the theme, the water), `/results/` the run output. Nothing else of the repository. The page
asks for a stamp every few seconds and reloads when the backlog, `changes.json` or a run's results changed. It never
runs a test. Dark by default, light when chosen (remembered per viewer).

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
