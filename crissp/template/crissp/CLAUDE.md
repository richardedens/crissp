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

<!-- CRISSP: first ask the product owner how many backends and frontends the product has and will have; advise a part
of its own (app/backend-<name>/, app/frontend-<name>/, CRISSP.md: Several parts) for each one with its own users,
release or team, and for any part whose tests would take more than about three minutes, so crissp/check.sh runs only
what changed. Then: what the product is in two sentences, who uses it; the parts of the repository (apps, packages, charts)
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

## The six stages

The work moves through six stages, the agentic SDLC (CRISSP.md, *The six stages*): **Discover** (the UX team walks the
product and finds what its users need) → **Plan** (findings and approved needs become PBIs, choices become decisions)
→ **Build** (the next PBI, test-first) → **Verify** (`crissp/check.sh`) → **Review** (what waits for the product
owner) → **Release** (the release notes; the product owner tags). The crissp tool `stage` says where the work is,
read from the backlog, the release certificate, git and the UX suite; the Stages page of the dashboard (`crissp
dashboard`, `/stages`) shows the same, with Ask Claude and Ask Vibe per stage.

- **At the start of a session, and on every `<!-- CRISSP … -->` prompt** (bringing the project in, filling a block):
  call `stage`, open with the stage the work is in and why, in a sentence or two, and offer the help for that stage;
  for example, when Discover is not set up yet, offer to set up the UX suite with the product owner.
- **"crissp: help me with <stage>"** (what Ask Claude and Ask Vibe start): call `stage` with that stage and do what it
  says.
- Mistral Vibe works the same: its crissp tools (`.vibe/config.toml`) include `stage`.
- Helping with a stage never pushes, tags, publishes or deploys, and never moves work to done.

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
- The Activity page (`crissp dashboard`, `/activity`) shows each session's history, Claude Code's and Vibe sessions too;
  past 300k tokens it says to start fresh.

The same in **Mistral Vibe** (the same habits, its own commands):

- A fresh session per item: `/clear` in the terminal, or a new session in the desktop app; `/compact <what to keep>`
  in the middle of a long item. Vibe compacts by itself at `auto_compact_threshold` (400k tokens unless set lower in
  `~/.vibe/config.toml`): start fresh before that, a summary loses what a new session asks for again.
- Heavy output in a subagent: the `task` tool starts one that reports text (the `explore` agent for searching the
  code, another for a browser check and its screenshots), so its files and images stay out of the main session.
- The crissp tools come from `.vibe/config.toml` (crissp repair writes it for this machine): `brief` and `backlog`
  instead of reading the backlog files; restart Vibe after a change to it.

## Working with the product owner

- Act when the intent is clear; ask only for real choices that are expensive to undo, with a recommendation.
- Be honest about what is and is not done; never report something as green that was not run.
- Anything that leaves the machine or cannot be undone (push, deploy, delete, a production change) waits for an
  explicit yes for that action.
