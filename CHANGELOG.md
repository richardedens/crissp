# Release notes

What changed in C.R.I.S.S.P., newest first. One entry per version (the version is in `VERSION`).

## 0.1.10 — 2026-11-26

- **A map of every screen, and the gaps (E7-F3-01).** `crissp ux --map` lists the product's screens in the UX page's new
  **Map** tab, so the team looks at more than the walks someone wrote. It crawls the running product read-only (its own
  links only, never one that signs out or deletes, at most `map.max` pages per device), adds the screenshots your E2E
  tests list in `crissp/uxsuite/results/test-shots/screens.json` (`map.tests` points elsewhere), and the walks' own. Per
  area you see every screen with its pictures, how it was found and its gaps: no link reaches it, the crawl could not
  open it, or no walk looks at it.
- **The dashboard opens with a verdict (F-70).** The Overview first says whether the last run is ready to release,
  and when it is not, which steps failed, each linked to its own log. Tiles have short names, say what is not right
  yet and link to it ("3 changes without a passing test" opens just those changes); line and branch coverage share
  one tile; steps and test suites sit side by side. On Runs & logs a failed step's log is open and a passed one folded.
- **A Security tile (F-73).** The CVE audit, the secrets scan and the unsafe-code scan get a tile with what each found
  ("nothing found", or how many findings block the release), next to the Lint tile. Scans and suites without tests no
  longer appear in the suites table as "0 tests".
- **The Tests tab shows failures first and stays in the page (F-71).** One long failing assertion no longer makes the
  table thousands of pixels wide.
- **Easier on a phone, and readable buttons (F-72).** The top bar no longer makes pages scroll sideways on a phone: the
  sections get a row of their own. Text on the purple accent is dark in the dark theme, so primary buttons pass WCAG AA
  contrast.
- **See the debate, and enlarge a design (F-80).** A round on the UX page now shows the debate itself, not only the
  moderator's summary: each persona's first look (score, what is good, the problems with a link to the screenshot,
  ideas) and every answer per debate round (who agrees, who disagrees with whom and why, who changed their mind), live
  while the round runs. Every screenshot and design opens big over the whole page: before, side by side or after, at
  fit, 100%, 150% or 200% (keys 1-3 switch the view, + - 0 zoom, Esc closes).
- **git lints before every commit (F-50).** `crissp init` writes `.githooks/pre-commit` and sets
  `core.hooksPath .githooks`, so a commit runs the project's lint steps first (`lint` and every `*-lint` step, such as
  `backend-lint` and `frontend-lint`) and a red lint stops it. The hook runs the crissp `.mcp.json` pins (the new
  `crissp hook` command), without fetching it when that version is installed. For projects brought in earlier, and in
  every fresh clone (`core.hooksPath` is not committed), `crissp repair --yes` makes the hook and turns it on. Neither
  ever switches off hooks a repository already has (its own `core.hooksPath`, or hooks in `.git/hooks`): they say
  what to do instead. `git commit --no-verify` skips the hook once.
- **Lint has its own tile on the dashboard (F-41).** The Overview shows a Lint tile next to the tests: "Clean", or
  how many problems each lint step found (ruff, Biome, ESLint, Stylelint and shellcheck are read from their logs),
  red when one failed. A lint step is a step whose key is `lint` or ends in `-lint`, like the template's
  `backend-lint` and `frontend-lint`. Lint steps no longer appear in the Suites table as "0 tests".
- **"Changes proven" on this repository's dashboard counts the package tests (F-40).** The `package` step now writes
  its test results for the dashboard, so the changes proven by `test_cli` and `test_package` no longer show as
  "missing" while they pass.
- **The UX suite's team and rules are yours to edit (E7-F1-01, E7-F2-01).** The UX page has a **Team** tab that adds,
  edits, switches off and removes a persona (name, role, device, moderator, the brief and the jobs they come to do),
  and a **Rules** tab that does the same for the rules the team judges by (title, weight must · should · could, on or
  off). Each persona is a file in `crissp/uxsuite/personas/` and each rule a file in `crissp/uxsuite/rules/`, in git
  and editable by hand; the first change in the page moves the personas out of `team.json` and the rules out of
  `PRINCIPLES.md` (which keeps its introduction), so there is one place for each. A persona that is off takes no part
  in a round and brings no device to a shoot; a rule that is off is left out. Every round and design gets the rules
  that hold, and the advice names the rule it is about. Projects that have not changed anything keep working as they
  are; `crissp repair` leaves both folders where they are.
- **Several backends and frontends, and the advice to split (F-60).** When a project is brought in, Claude now first
  asks how many backends and frontends the product has and will have, and advises a part of its own for each
  (`app/backend-<name>/`, `app/frontend-<name>/`, each with its own steps; CRISSP.md, *Several parts*). `crissp check
  --plan` advises splitting a part whose tests take more than about three minutes (the last run's time, else
  `suites.json`'s), because every change in that part runs all of them.
- **Static security analysis (SAST) for every project (F-44).** A new `sast` step runs Semgrep (pinned, offline, no
  metrics) with crissp's own rules on `app/`: Python, JavaScript, TypeScript and JSX. It blocks on eval or exec of a
  value, a shell command built from a value, `yaml.load`, switched-off TLS checks and a debug server, and lists for
  review pickle, SQL built from strings, HTML put into the page from a value and `dangerouslySetInnerHTML`. A project
  can add its own rules folders (`"sast_rules"` in `suites.json`'s `audit`); its `.semgrepignore` counts. The
  backend's lint now also runs ruff's security rules (`S`, from Bandit) on top of the backend's own ruff
  configuration (`ruff_check .`), with `assert` and made-up passwords allowed in tests. Projects brought in earlier
  can copy the `sast` step and change their `backend-lint` run to `ruff_check .`.
- **The git history is scanned for secrets (F-43).** A new `secrets` step runs gitleaks (pinned) over every commit
  and is red on a key, token or password that reached git. It says the file, line, commit and rule, never the value.
  It runs in `crissp check` for every change under `app/`. The project's own `.gitleaks.toml`, `.gitleaksignore` and
  `gitleaks:allow` count; a finding that is no secret is best allowed in `.gitleaks.toml` by its file
  and value, since a `.gitleaksignore` fingerprint names a commit and misses in a shallow clone (F-51). A step runs it as `audit secrets`.
- **Every project is audited in its full run (F-42).** `crissp init` now gives a project an `audit` step (full run
  only, once `app/` exists): pip-audit of `app/backend/requirements.txt`, npm audit of `app/frontend`, trivy for the
  dependencies, the Dockerfiles, the Helm chart, Terraform and the images the compose file and the chart name. A
  place the project does not have yet is listed as "not there yet", not red (`"missing": "skip"` in `suites.json`'s
  `audit`). Projects brought in earlier can copy the step and the `audit` section from the template. A step runs it
  as `audit run`.
- **The scanners are pinned, and checked before they run (F-42).** The audit no longer runs whatever `trivy` a machine
  has on its `PATH`: crissp fetches trivy 0.76.2 (and, for the new secrets step, gitleaks 8.30.1) once from the
  release, checks it against the SHA-256 crissp ships, and keeps it in its cache (`CRISSP_CACHE`, else
  `~/.cache/crissp`). A download that differs is refused. Linux and macOS, x86_64 and arm64; on Windows the guards
  run in WSL 2.
- **New projects lint the frontend too (F-30).** The project template gets a `frontend-lint` step next to
  `backend-lint`, there once `app/frontend/package.json` is and run by `crissp check` for every change under
  `app/frontend/`. It lints with crissp's own tools (F-34), so a frontend needs no lint setup of its own: ESLint
  9.39.5 with `@eslint/js`, typescript-eslint 8.72.2 (TypeScript 6.0.3), eslint-plugin-react-hooks 7.1.1,
  eslint-plugin-jsx-a11y 6.10.2 and eslint-plugin-react 7.37.5 (only `react/no-danger`), and stylelint 17.16.0 with
  stylelint-config-standard 40.0.0. They are pinned with their lockfile in crissp, installed once into crissp's cache
  (`~/.cache/crissp`) with `npm ci`, and never touch the project's `package.json`. It needs Node.js (`npm`).
  `crissp repair` gives projects with no steps the same default.
- **The dashboard no longer misses a change, and the board shows the open decisions and findings (F-32).** The open
  page already rebuilt its data when the backlog, `changes.json` or a run's results changed, but a change made while a
  rebuild ran was skipped until the next one; now it is picked up. When a rebuild fails, the page says "not current"
  with the reason instead of "live". The Backlog board lists the open decisions and the findings (newest first, with
  how many are not fixed yet) above the lanes.
- **A check started with `run` no longer stays a zombie, and `status` can wait (F-31).** The crissp MCP server now
  reaps every check it starts the moment it ends; before, a finished check stayed a zombie that `kill -0 <pid>` still
  found alive, so an agent waiting on the pid hung until its own timeout. `status` takes `wait: true` (and `timeout`,
  default 300 s, at most 3600 s) and answers as soon as the run has ended, with its exit code and the end of its log.
  `run` now says to wait with `status`, not on the pid.
- **`crissp init` onboards Mistral Vibe as well as Claude Code (F-24).** A new project also gets `.vibe/config.toml` —
  the same crissp MCP server, pinned `uvx crissp==<version> mcp` like `.mcp.json`.
  When Vibe is installed (`VIBE_HOME`, else `~/.vibe`), init also adds the project folder to `trusted_folders.toml`,
  so Vibe loads the project-local config; `crissp repair` puts the same in place in projects brought in earlier.
  Nothing is overwritten, nothing is committed.
- **The Vibe onboarding detects the system and the installation (F-25).** `crissp init` says one line — Windows,
  macOS or Linux, whether `vibe` was found on `PATH` or only its home (`VIBE_HOME`/`~/.vibe`) exists — and what it
  did: trusted, already trusted, start Vibe once first, or not installed. The project path lands in
  `trusted_folders.toml` as valid TOML on every system (Windows backslashes escaped, and Vibe's own forward-slash
  entry is matched, never duplicated). On native Windows init also says that the bash guards (`check`, `deploy`,
  `ux`, `dashboard`) run inside WSL 2 (F-14); the Vibe onboarding itself works natively.
- **Vibe's `trusted_folders.toml` is read, never patched line by line (F-26).** init and repair share one function
  that reads the file as TOML: a Windows folder is no longer added again on every run, a one-line `trusted = [...]`
  no longer turns into invalid TOML, a folder you marked untrusted stays untrusted, and a file in a shape crissp
  does not know is left alone (it says so; trust the folder from Vibe itself).
- **`crissp repair` moves the Vibe pin too (F-27).** After an update, `uvx crissp==<new> repair --yes` moved the
  crissp pinned in `.mcp.json` but not the one in `.vibe/config.toml`, so Vibe kept the old crissp tools. Both now
  move together; only the pin changes, the file's comments and other servers stay.
- **`crissp init` asks before it trusts the folder in Vibe (F-28).** Trusting a folder lets Vibe load its
  project-local config, which is exactly what Vibe's own prompt guards. Without `--yes`, init now asks
  (`[Y/n]`, Enter is yes); with `--yes` it trusts as before. When it trusts, it says how to undo it.
- **`.vibe/config.toml` is committed, like `.mcp.json` (F-29).** It holds the same pin and nothing tied to one
  machine, so a teammate's Vibe gets the crissp tools from the clone, without `crissp repair`. The `.gitignore`
  rules are `.vibe/*` and `!.vibe/config.toml`: whatever else Vibe keeps in `.vibe/` stays local.

## 0.1.9 — 2026-11-24

- **An option with a long dash works.** Teams, Outlook and Word turn `--` into `—`, so a copied
  `crissp repair —yes` stopped with "unrecognized arguments: —yes". crissp now reads a leading `—` or `–` as `--`.

## 0.1.8 — 2026-11-24

- **`crissp repair` brings the agreement's sessions section up to date.** A project brought in before 0.1.7 did not
  get "Sessions that stay small" in its `crissp/CLAUDE.md`. The section is crissp's own, so repair now puts this
  version's text in place: it replaces an older one, or adds it before "Working with the product owner" (else at the
  end). The rest of the agreement stays as the project wrote it.

## 0.1.7 — 2026-11-24

- **Sessions that stay small.** Every step Claude takes resends the whole conversation, so a long session costs more
  with every step. The framework and a new project's agreement now say how to keep sessions short: a fresh session per
  item (`/clear`), `/compact` in the middle of a long one, browser checks and screenshots in a subagent, the checks
  through `run` and `status`, searches in an Explore agent, narrow questions, and the lighter model for routine work.
- **The Activity page shows each session's history**: what its last request carried, measured as the sessions report
  does. Past 300k tokens the session gets a *long history* mark with what to do: `/clear` between items, `/compact` in
  the middle of one.

## 0.1.6 — 2026-11-24

- **The PyPI page is up to date.** It shows this README: `crissp repair` with its two new repairs (and to run it after
  an update), and the dashboard with the workers and the Activity page.
- **The website takes its version from `VERSION`** (it said 0.1.0 in its example) and lists `crissp repair`.

## 0.1.5 — 2026-11-24

- **The dashboard reads a change's source as you wrote it.** A plain path in `changes.json` is shown as that file from
  the top (it used to stop the dashboard), and a folder is found and shown by its files. The template's `changes.json`
  now says the format: `{file, symbol}`, where the symbol is the line of the fix to show.
- **`crissp repair` puts two more things in place**: plain-path sources in `changes.json` become `{file, symbol}`, and
  the crissp pin in `.mcp.json` moves to the crissp you run repair with, so the MCP tools follow the new version.

## 0.1.4 — 2026-11-24

- **One top bar on every page.** The Tests dashboard, the backlog board, the UX suite, the workers page and the Claude
  sessions pages now show the same sections in the same order (Tests · Backlog · UX · Workers · Activity · Sessions), with the
  open one marked. Backlog is a section of its own, and opens the board. The title follows the open section
  ("Shop · Backlog" on the board), the menu starts at the same place on every page, and a page's own tabs (Tests, UX)
  get a row of their own instead of wrapping.
- **The board shows how the backlog moves.** "Moved recently" above the lanes lists the newest moves (from → to, how long
  ago, and the commit, or "not committed" for a move in the working tree). Each card says how long it has stood in its
  column, and its details list every move. A commit shows on the board within seconds.
- **An Activity page** (`/activity`) shows live what Claude is doing in this repository: per session the last prompt,
  what the orchestrator (the main thread) is doing now and for how long, and every agent it started, running ones first,
  each with its own current step; agents that finished more than an hour ago are counted, not listed. It reads Claude
  Code's own transcripts on this machine and shows only what Claude sent to its tools.
- **New pictures** in the README and on the website, from a fresh 0.1.4 demo project, including the Activity page,
  the workers and the board's movement.

## 0.1.3 — 2026-11-24

- **The dashboard opens in every project, whatever its history holds.** An old commit with a backlog file saved in
  another encoding (Windows' cp1252) stopped it before it served anything; now that file is read as it was meant, with
  its items' statuses. The dashboard also reads and writes its pages as UTF-8 under any locale (a Latin-1 locale
  failed before).
- Tests that need a database share **one PostgreSQL server, with a database per worker** (named after
  `PYTEST_XDIST_WORKER`), never a server per worker. The framework and the template agreement say so, and the
  testsuite README has the session fixture.

## 0.1.2 — 2026-11-17

- **Tests run in parallel, sized to the machine.** A step that says `"parallel": true` spreads its tests over as many
  workers as this machine can take. That is the tightest of three limits: the CPUs less one, three quarters of the
  available memory per worker (`memory_mb`, default 256), and the step's test files. It works on a Mac and on Linux,
  including a CI runner's cgroup limits; `CRISSP_WORKERS=<n>` sets the count yourself.
  - Coverage still counts every worker, so the gate sees the same numbers.
  - The run says how many workers it used (`passed (11s, 15 workers)`), and `crissp check --plan` says how many a step
    will get and why.
  - The template's backend step is parallel. crissp's own tests run in 11 s instead of 37 s on a 16-CPU Mac.
- **A `/workers` page** on the dashboard server (`crissp dashboard`, linked from Tests and UX) shows the run spread over
  the machine, live:
  - the CPUs, the memory and what is available, and how many workers a parallel step gets here and why;
  - per step, how far it is, about how long is left, and what passed or failed;
  - one lane per worker: the test it runs now and for how long (marked quiet after a minute), what it finished, and
    how much of the step it was busy.

  Every test is recorded as it finishes, per worker, in `crissp/testsuite/results/timing/`.

## 0.1.1 — 2026-11-10

- **The product has a default place**: `app/backend/`, `app/frontend/` and `docker-compose.yml` at the root. A new
  project's steps (`backend`, `backend-lint`, `frontend`) appear once their part exists, so `crissp check-all` is green
  before there is any code. The UX suite walks the local stack (`http://127.0.0.1:8080`) instead of a dev server. Until
  that stack runs, a design is `crissp ux --propose`; `crissp/uxsuite/` holds only its configuration. CRISSP.md has a
  new section, *The product's place*.
- **`crissp repair`** says what a project brought in earlier has out of place, and `crissp repair --yes` puts it in
  place:
  - the old template's steps on `src/`;
  - a UX suite walking `127.0.0.1:5173`;
  - files such as a prototype in `crissp/uxsuite/`, which move to `docs/ux/`;
  - the agreement's old `crissp/tool` line;
  - template files missing from `crissp/`;
  - an old `crissp/CRISSP.md`;
  - missing `.gitignore` rules.

  It also says what needs you, such as no commit yet or no `docker-compose.yml`. It never deletes, never commits and
  never changes the backlog's content.
- **A design has the moderator's check**: the moderator now writes down what it found in a design (a verdict: ready,
  ready with remarks or not ready; what the designer fixed; what still stands), and the UX suite shows it under the
  design. A finished design without a check says so. Before, the check happened but left nothing behind.
- The template's agreement says the crissp tools come from the crissp MCP server in `.mcp.json`, not from a
  `crissp/tool` folder that an installed project does not have.

- `crissp dashboard` opens this project's dashboard, never another one. With a dashboard of another project already on
  the port (8766, or `CRISSP_DASHBOARD_PORT`), it leaves that one running, takes the next free port and says so
  ("Port 8766 serves the dashboard of …: this project gets port 8767."). Before, it opened the other project's
  dashboard, so this project's tests and UX results seemed missing. The crissp tool's `dashboard` action follows the
  same rule.
- The coverage baseline is rewritten only when a number moves, so a green `crissp check-all` no longer asks for an
  extra commit that only records a commit hash.

## 0.1.0 — 2026-11-05

The first standalone release of C.R.I.S.S.P. (Consistent, Repeatable, Innovative, Secure, Scalable, Programming), the
agentic SDLC framework for Claude Code: AI colleagues (Claude, its agents, the UX team and a designer) plan, build,
review and test the product, guards prove every change, and the product owner decides. Every piece of work can be
traced from the first observation to the release that delivered it.

- **Install it as a package**: `uvx crissp init` brings a folder in. It runs `git init` when the folder is not a
  repository yet, then writes the agreement, the backlog, the product's configuration and the deployment template. It
  never overwrites a file and never commits. Then `crissp check`, `check-all`, `deploy`, `dashboard`, `ux` and `mcp`
  run the framework for the project in the current folder, and every message names those commands. The first full
  run says what is left: commit the coverage baseline it wrote, then `crissp check`. `.mcp.json` pins the project's
  crissp version.
  Requires Python 3.12 or newer; the engine uses only the standard library.
- **The framework** (`crissp/CRISSP.md`): the six letters and how each one is checked, the artefacts every
  C.R.I.S.S.P. repository has, the formats of findings, decisions, epics, features and items, who does what, and the
  guards.
- **The agreement** (`crissp/CLAUDE.md`, loaded by a short root `CLAUDE.md`): how one product is built, tested,
  released and run, read first in every session. `crissp/AGENTS.md` tells an agent working next to the main session
  what its part is, where its limits are and how to report.
- **The backlog** (`crissp/backlog/`): PLAN, DECISIONS (D-xx), FINDINGS (F-xx) and one file per epic, in three levels
  (epic → feature → item), with statuses `todo` · `doing` · `review` · `done`. Only the product owner accepts work.
- **The crissp tool** (`crissp/tool/`, registered in `.mcp.json`): an MCP server that uses only the standard library.
  `brief` and `backlog` give Claude the lines it asks for, so it doesn't have to read the files. `finding`,
  `decision`, `epic`, `feature` and `item` write entries in the backlog's own format under the next free number. `run`,
  `status` and `dashboard` start the checks in the background. It never deploys and never marks work as done.
- **The guards**:
  - `crissp/check.sh` runs only what a change can affect (the impact plan). With `--plan` it shows what it would run.
  - `crissp/check-all.sh` is the full run.
  - The coverage gate only lets coverage go up.
  - The release certificate records exactly which commit was tested.
  - `crissp/deploy.sh` deploys only behind the release gate, which has no bypass: a green full run at most 7 days
    old, plus a green check for every change since.
- **The dashboard** (`crissp/test.sh --dashboard`): what the last runs proved, and the backlog board. It never runs a
  test.
- **The UX suite** (`crissp ux`): fictional users walk through the running product, debate it from their own point of
  view, and a moderator turns that into advice. A designer makes proposals on request. Every design shows **before and
  after** side by side (what people see now on a laptop or a phone, next to the design), with *Approve*, *Approve with
  a remark…*, *Again, with…* and *Reject* right under it. An approved design becomes a backlog item, and the remark is
  the first thing in it.
- **One dashboard, one look**: `crissp dashboard` serves the Tests dashboard, the backlog board and the UX suite on one
  local server (127.0.0.1), with links between them, in one dark theme (a light theme can be chosen and is
  remembered).
- **The deployment template** (`crissp/deploy/`): a Helm chart (backend, nginx frontend, PostgreSQL with a nightly
  backup, behind Traefik with security headers, redirects and NetworkPolicies, non-root and read-only) and Terraform for
  the cluster side (namespace, pull secret, default-deny, quota, limits). `crissp deploy --cluster` reads everything
  from `deploy.json`: the release gate, then terraform plan, a y/N, apply, the images, helm and the health check.
  `--cluster-plan` shows what it would do and changes nothing.
- The product's parts, its steps and its coverage rules are configured in `crissp/testsuite/suites.json`, so the
  guards work for any stack.
- **The template** (`crissp/template/`): what a repository gets when it is CRISSPified. It includes the agreement, the
  agents' rules, the backlog skeleton, the release notes, the ignore rules, the testsuite and the UX team, with
  placeholders Claude fills in from the real repository. Nothing is committed before the product owner has reviewed
  the diff.
