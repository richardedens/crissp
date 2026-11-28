# {{PRODUCT}} — how we work in this repository

Read this first in every session (the root CLAUDE.md loads it). It is the agreement between the product owner ({{OWNER}}) and Claude on how
{{PRODUCT}} is built, tested, released and run. Keep it current: when a way of working changes, change it here (in
the same commit). The backlog (`crissp/backlog/`) holds *what* to build; this file holds *how*. It is the C.R.I.S.S.P.
framework ([CRISSP.md](CRISSP.md): Consistent, Repeatable, Innovative, Secure, Scalable, Programming) filled in for
{{PRODUCT}}. Where the work stands and the backlog: ask the crissp tools (`brief`, `backlog`; the crissp MCP server, registered
in `.mcp.json`) instead of reading the backlog files; write findings, decisions, epics, features and PBIs with `finding`,
`decision`, `epic`, `feature` and `item` instead of editing them.

## The product

- The parts, by default (CRISSP.md, *The product's place*): `app/backend/`, `app/frontend/`, and `docker-compose.yml`
  at the root that runs them together locally. The first PBIs build that skeleton; the UX suite walks it once it runs.
  A design before then is `crissp ux --propose <walk>`; `crissp/uxsuite/` holds only its configuration.

<!-- CRISSP: what the product is in two sentences, who uses it; the parts of the repository (apps, packages, charts)
with their stack; where it runs (production URL, cluster and namespace); the languages its texts are in; words the
product always or never uses. -->

## Testing — the product owner drives, never on a schedule

| Command | What it does |
|---|---|
| `crissp/check.sh --plan` | Shows what changed since the last green state, what it would run and how long |
| `crissp/check.sh` | Runs only what the changes can affect, then moves the release certificate to this commit |
| `crissp/check-all.sh` | The full run |

<!-- CRISSP: what crissp/check.sh runs per kind of change (notes → nothing; each part → its suites); what counts as shared
ground (→ the full run); the test runners of each part as they exist today; the stand-ins the tests use instead of
real services. Until the guards exist (template/testsuite), name the commands that do exist and add the missing
guards as findings. -->

- **Commit first**: the scripts test what is committed. **One run at a time.**
- **The lint runs before every commit**: git runs `.githooks/pre-commit` (`crissp hook`: the `lint` and `*-lint`
  steps). In a fresh clone, `crissp repair --yes` turns it on (`core.hooksPath .githooks`). Never `--no-verify` to
  get past a red lint; fix it.
- Tests never read a developer `.env`, never touch a real database, real AI keys or real identity providers.
- **Parallel tests share one PostgreSQL server, with a database per worker**: never a server per worker. A session
  fixture (`conftest.py`) creates the worker's own database on that one server, named after `PYTEST_XDIST_WORKER`
  (`test_gw0`, `test_gw1`, …, `test_main` without xdist), migrates it, and drops it at the end.

## Releasing — nothing goes to production untested

<!-- CRISSP: how a release happens today (deploy script, images, registry, helm chart), the release gate it needs,
where release notes go (and in which languages), the version scheme. -->

- Deploy only when the product owner asks. Never edit the tree while a deploy or a check run is busy.
- **Release notes are Claude's job, always, without asking**, in the same piece of work as the change.
- Git: the product owner pushes. Never commit generated or large files.

## Security

<!-- CRISSP: what never goes into git or an image for this product (secrets, dumps, customer data, uploads, local
storage); where secrets live instead; what needs a person's yes (access changes, keys, public access); the trust
lines that need a security test. -->

## Fixing — every fix proves itself

- Every fix starts with a test that **fails without the fix** (undo the fix, see it fail, restore).
- One commit per finding or item: `F-xx: <what>` or `E1-01: <what>`, with what was wrong, how it was fixed, the proof.
- Parallel work: agents in their own git worktrees, grouped by part, each running its part's tests before reporting.
  Claude reviews, merges, updates the findings and release notes. Agents never edit `crissp/backlog/`.
- Report to the product owner per fix: what was wrong, how it was fixed, how it is proven.

## Documentation

<!-- CRISSP: where the documentation lives and how it is made (journeys that are tests and docs at once, when the
template's testsuite is in place); what may never appear in public docs (real data, customer names). -->

## The backlog

- `crissp/backlog/`: README (item format, definition of done), PLAN, DECISIONS (D-xx), one file per epic
  (`E<n>-<slug>.md`), and FINDINGS (observations F-xx, collected while working).
- Status: `todo` · `doing` · `review` · `done`. Only the product owner accepts; accepted work moves to
  `crissp/backlog/done/`.
- New observations go to FINDINGS.md right away (`F-next | where seen | what | goes to`).
- A security scanner writes its findings here as F-rows, with `docs/stories/NN-<slug>/STORY.md` as their plan.

## Sessions that stay small

Every step Claude takes resends the whole conversation so far, so a long session costs more with every step; the fixed
context (this agreement, the tools) is small. Keeping sessions short saves the most:

- **A fresh session per item**: `/clear` when one item is done and the next starts; `brief`, `backlog` and git bring
  back what is needed. `/compact` in the middle of a long item, steered (`/compact keep E6-F1-02 and the failing test`).
- **Heavy output stays out of the conversation**: a browser check and its screenshots run in a subagent that reports
  what is wrong; the checks start with `run` and are read with `status`, only the failures; searching the code is an
  Explore agent's job, so the files it reads stay in its context.
- **Narrow questions**: name the file or the function, one screen or flow at a time. Every file read stays in the
  history for the rest of the session.
- **Agents on separate parts**, each briefed narrowly, so they do not each rediscover the same files.
- **The lighter model and effort for routine work** (release notes, small fixes), the strongest for design and hard bugs.
- The Activity page (`crissp dashboard`, `/activity`) shows each session's history; past 300k tokens it says to start
  fresh.

## Working with the product owner

- Act when the intent is clear; ask only for real choices that are expensive to undo, with a recommendation.
- Be honest about what is and is not done; never report something as green that was not run.
- Anything that leaves the machine or cannot be undone (push, deploy, delete, a production change) waits for an
  explicit yes for that action.
