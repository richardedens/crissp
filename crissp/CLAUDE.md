# C.R.I.S.S.P. — how we work in this repository

Read this first in every session (the root CLAUDE.md loads it). It is the agreement between the product owner and
Claude on how C.R.I.S.S.P. itself is built, tested, released and run. Keep it current: when a way of working changes,
change it here (in the same commit). The backlog (`crissp/backlog/`) holds *what* to build; this file holds *how*. It is
the framework ([CRISSP.md](CRISSP.md): Consistent, Repeatable, Innovative, Secure, Scalable, Programming) applied to
itself. Where the work stands and the backlog: ask the crissp tools (`brief`, `backlog`; registered in `.mcp.json`)
instead of reading the backlog files; write findings, decisions, epics, features and PBIs with `finding`, `decision`,
`epic`, `feature` and `item` instead of editing them (never `done`). The backlog has three levels: epic (E2) → feature
(E2-F1) → PBI (E2-F1-01).

## The product

- **C.R.I.S.S.P.** is open source (Apache-2.0, see LICENSE and NOTICE) and ships as the Python package `crissp` on
  PyPI. People run `uvx crissp init` to bring a project in, then `crissp check`, `check-all`, `deploy`, `dashboard`,
  `ux` and `mcp`. Texts, code, commits, docs, backlog and release notes are English.
- This repository is both the source of the package and a C.R.I.S.S.P. project of its own:
  - `src/crissp/` — the `crissp` command (`cli.py`). Installed, the engine is package data under `crissp/engine/`.
  - `crissp/` — the engine, exactly as it ships: the guards (`check.sh`, `check-all.sh`, `deploy.sh`, `test.sh`,
    `ux.sh`), the crissp MCP tool (`tool/server.py`), the testsuite (`testsuite/lib`, `dashboard/`), the uxsuite,
    the shared look (`look/`, dark by default), the deploy template (`deploy/`: a Helm chart and Terraform) and the
    project template (`template/`).
  - This project's own data, never in the wheel: this agreement, `crissp/backlog/`, `crissp/testsuite/suites.json`
    (its parts), `changes.json`, `accepted-risks.json`, `coverage-baseline.json`, and the results (git-ignored).
- **The engine finds the project through `CRISSP_ROOT`** (the `crissp` command sets it), else the current directory;
  never from its own file location. Engine files (the look, the dashboard, the template) are found next to the code.
- The engine uses the **Python standard library only** at runtime (Python 3.12 or newer). Test tools are pinned in
  `crissp/testsuite/requirements.txt` (and `crissp/deploy/requirements.txt` for the chart's tests).
- Runtime dependencies are local: the dashboard and the uxsuite load nothing from a CDN; the font is bundled (OFL-1.1).

## Testing — the product owner drives, never on a schedule

| Command | What it does |
|---|---|
| `crissp/check.sh --plan` | Shows what changed since the last green state, what it would run and how long |
| `crissp/check.sh` | Runs only what the changes can affect (`crissp/testsuite/lib/impact.py`, from `suites.json`), then moves the release certificate to this commit |
| `crissp/check-all.sh` | The full run: every step below, plus the CVE audit of the pinned tools |
| `crissp/test.sh --dashboard` | One local server (127.0.0.1:8766, `CRISSP_DASHBOARD_PORT`): the Tests dashboard, the backlog board and the UX suite (never runs a test) |

This project's steps (`crissp/testsuite/suites.json`):

- `tools`: the testsuite's, uxsuite's and crissp tool's own tests, held at **100% lines and branches**.
- `gate`: the coverage gate (coverage only goes up).
- `deploy`: `crissp/deploy/check.sh`, with helm lint and template, `terraform fmt` and `validate` when Terraform is
  installed (otherwise a visible "skipped"), and the chart's structure tests.
- `package`: builds the wheel, installs it into a throwaway venv, runs `crissp init` in an empty git repository, and
  then that project's full run.
- `audit`: pip-audit of the pinned tools (full run only).

What `crissp/check.sh` runs per change:

- notes and backlog → nothing;
- `CHANGELOG.md`/`VERSION` → a file check;
- `crissp/testsuite/`, `uxsuite/`, `tool/`, `look/`, `template/` → tools;
- `crissp/deploy*` → deploy;
- `src/`, `pyproject.toml` → package;
- shared ground (the check scripts, the gate, the certificate, `.mcp.json`, anything unmapped) → it stops and asks
  for `crissp/check-all.sh`.

- Directly: `crissp/testsuite/run.sh --quick tools gate deploy package`. CI (`.github/workflows/ci.yml`) runs the same.
- **Commit first**: the scripts test what is committed. **One run at a time** (a lock in `crissp/testsuite/results/`).
  Claude may run `crissp/check.sh` for its own work; the full run is the product owner's to start unless they ask.
- Tests never read a developer's `.env`, never touch a real cluster, registry or PyPI, and never start a real Claude
  round (they use stand-ins). They never start the real dashboard either: a test that needs the engine's scripts gives
  the tool an empty engine.

## Releasing — nothing goes live untested

- The version is in `VERSION` (semver); the package's version is read from it.
- **Release notes are Claude's job, always, without asking**: every change a user of crissp would notice goes into
  the top entry of `CHANGELOG.md` (newest first), for the version in `VERSION`.
- A release is a tag the product owner pushes, `v<VERSION>`. Then `.github/workflows/publish.yml`:
  1. builds the package and checks the tag against `VERSION`;
  2. installs the wheel and runs `crissp init`;
  3. waits for approval in the `pypi` environment;
  4. publishes to PyPI by trusted publishing (no token anywhere).

  "Run workflow" publishes `<VERSION>.dev<n>` to TestPyPI instead.
- PyPI never accepts the same version twice: try on TestPyPI first. Claude never tags, pushes or publishes.
- Git: the product owner pushes. Never commit generated or large files (builds, `dist/`, results, caches).

## Security

- **Never in git, never in the package**: `.env*` (except the examples), keys, kubeconfigs, Terraform state and real
  `*.tfvars`, dumps and backups, results. `.gitignore` says so. The wheel is built from an explicit list
  (`pyproject.toml`), and the package test proves what is and is not in it.
- No private names: `crissp/testsuite/tests/test_private_names.py` and `test_generic_names.py` keep the names of
  private projects, people and clusters out of every file. The names are held as hashes, so the guards don't name them.
- The deploy template:
  - every container runs non-root, with a read-only root file system and NetworkPolicies;
  - secrets come only from untracked files, are written into private mode-600 files, and those are removed afterwards;
  - `--cluster-plan` changes nothing.
- The release gate has no bypass, and Claude never builds one.
- Secrets never go through chat, logs or the Claude panel: print that a secret is present, never its value.

## Fixing — every fix proves itself

- **Test first, always**: every PBI and every fix starts with a test that **fails without the change** (write it, see
  it red, then build until green). New and changed Python code is fully covered; the gate only goes up
  (`crissp/testsuite/lib/gate.py --accept "reason"` only for honest reasons, stated in the commit).
- One commit per finding or PBI: `F-xx: <what>` or `E2-F1-01: <what>`, with what was wrong or missing, how it was
  done, the proof. Fixes are recorded in `crissp/testsuite/changes.json` (problem, fix, sources, tests).
- Parallel work: agents in their own git worktrees, grouped by part (testsuite, uxsuite, deploy, package), each running
  its part's tests before reporting. Claude reviews, merges, runs the checks, updates the backlog and release notes.
  Agents never edit `crissp/backlog/`.

## Documentation

- `README.md` (also the PyPI page) says how to install and use crissp.
- `crissp/CRISSP.md` is the framework, and this file says how we work.
- `crissp/testsuite/README.md`, `crissp/uxsuite/README.md` and `crissp/deploy/README.md` describe their parts.
- The template follows the framework: a change to the framework changes CRISSP.md and the template in one commit.
- Docs never contain real customer data, real names of private projects or real infrastructure.

## The backlog

- `crissp/backlog/`: README (item format, definition of done), PLAN, DECISIONS (D-xx), one file per epic
  (`E<n>-<slug>.md`), and FINDINGS (observations F-xx, collected while working).
- Status: `todo` · `doing` · `review` (built, waiting for the product owner) · `done`. Only the product owner accepts;
  accepted work moves to `crissp/backlog/done/`.
- New observations go to FINDINGS.md right away (`F-next | where seen | what | goes to`).

## Working with the product owner

- Act when the intent is clear; ask only for real choices that are expensive to undo, with a recommendation.
- Be honest about what is and is not done; never report something as green that was not run.
- Anything that leaves the machine or cannot be undone (push, tag, publish, deploy, delete) waits for an explicit yes
  for that action.
