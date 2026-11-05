# C.R.I.S.S.P.

**Consistent · Repeatable · Innovative · Secure · Scalable · Programming**

C.R.I.S.S.P. is how we build software: a product owner, Claude and its agents working in one repository, with every
piece of work traceable from the first observation to the release that delivered it. This file defines the
framework; every repository that adopts it follows it, or is CRISSPified (from the template in
[crissp/](README.md)).

A C.R.I.S.S.P. repository is recognisable at a glance: the same files in the same places, the same formats, the same
words. Anyone — a person, Claude, an agent — can open any of them and know where the work is, what is proven, and what
is waiting for whom.

---

## The six letters

| Letter | Means | In practice | Checked by |
|---|---|---|---|
| **C**onsistent | One way, everywhere | The same artefacts and formats in every repository; code that reads like the code around it; the product explains itself in the same plain words | the formats below; review |
| **R**epeatable | Everything can be done and proven again | A test that fails without the fix; scripted checks and deploys, no manual steps; a certificate that says exactly which commit was tested | `crissp/check.sh`, `crissp/check-all.sh`, the certificate |
| **I**nnovative | Room for what is next, without losing what is now | Every observation is written down at once; ideas become epics or parked items; decisions are put as options with a recommendation; AI colleagues build, people decide; virtual users debate the interface before real ones meet it | FINDINGS, DECISIONS, PLAN, the UX team |
| **S**ecure | Safe by default | Secrets never in git, an image, a log or a chat; every change to production asks first; least privilege; a security test at every trust line | ignore rules, security tests, the y/N rule |
| **S**calable | Small steps that add up | Small, frequent releases; work cut so it fits one commit; parallel agents per part in their own worktrees; tests that run what a change can affect | sizes, the impact plan, worktrees |
| **P**rogramming | Done means done | One commit per finding or item; coverage only goes up; release notes always; only the product owner accepts | the definition of done, the coverage gate |

---

## The artefacts — in every C.R.I.S.S.P. repository

| Path | What it holds | Who keeps it |
|---|---|---|
| `crissp/CLAUDE.md` (loaded by a short root `CLAUDE.md`: `@crissp/CLAUDE.md`) | **The agreement**: how this repository is built, tested, released and run; read first in every session. Names C.R.I.S.S.P. and fills it in for this product | Claude, with the product owner |
| `crissp/AGENTS.md` (a short root `AGENTS.md` points to it) | What an agent next to the main session must know: its part, its limits, how to report | Claude |
| `README.md` | What the product is, how to start it, its commands; for people | Claude |
| `crissp/tool/` + `.mcp.json` | The crissp MCP server: `brief` and `backlog`, so Claude asks for lines instead of reading files; `finding`, `decision`, `epic`, `feature` and `item`, so it writes them instead of editing files; `run`, `status` and `dashboard`, so it starts the checks (never a deploy) and shows the dashboard | the framework (never edited in a project) |
| `crissp/uxsuite/` | **The UX suite**: virtual people walk the running product, debate what is right and wrong, and a moderator turns it into advice; designs on request; an approved design becomes a PBI (below). Its rounds, designs and verdicts stay in `crissp/uxsuite/results/` (git-ignored) | Claude fills `team.json` and the walks; the engine is part of the package |
| `crissp/check.sh`, `crissp/check-all.sh`, `crissp/deploy.sh`, `crissp/test.sh`, `crissp/testsuite/` | The guards and the dashboard: everything of the way of working in one visible folder, the root keeps the product | Claude, per stack (E2-05) |
| `crissp/backlog/README.md` | The item format and the definition of done of this repository | Claude |
| `crissp/backlog/PLAN.md` | Why, principles, the order of work | Claude, with the product owner |
| `crissp/backlog/DECISIONS.md` | Open questions for the product owner and decisions taken (D-xx) | Claude asks, the product owner decides |
| `crissp/backlog/FINDINGS.md` | Observations (F-xx), written down the moment they are seen | Claude |
| `crissp/backlog/E<n>-<slug>.md` | One epic per file, with its features and their PBIs | Claude |
| `crissp/backlog/done/` | Accepted epics and fixed findings, same file names | moved after the product owner's yes |
| `docs/stories/NN-<slug>/` | A detailed plan for one finding when it needs more room than a row (`STORY.md`, later `EVIDENCE.md`); written by a security scanner from its scans, or by Claude | the scanner, Claude |
| release notes | Every change a user would notice, for the next version (where: named in CLAUDE.md) | Claude, always, without asking |
| `crissp/testsuite/changes.json` | Per change: problem, fix, sources, the tests that prove it | Claude |

Agents never edit `crissp/backlog/`, release notes or the version: the main session keeps those after review.

---

## The formats

### A finding — one row, written at once

```
| F-42 | where it was seen | what was observed, concretely | goes to |
```

- **Number**: the next one over `crissp/backlog/FINDINGS.md` and `crissp/backlog/done/FINDINGS.md` together; never reused.
- **Seen**: the place — a screen, a command, a scan, a file, a test run.
- **Observation**: what is wrong or could be better, with enough detail to act on it later (names, numbers, paths).
- **Goes to**: the item or decision it feeds (`E2-01`, `D-04`), another project (`otherproject`), `fixed (version, sha)`,
  or `closed — reason`.

### An epic — one file, `crissp/backlog/E<n>-<slug>.md`

```
# E8 · Title                                  one epic per file: E<n>-<slug>.md

Why: the reason this epic exists, in the product owner's words where possible.

## E8-F1 · Feature title                                   [status]
Why        what this feature gives the user

### E8-F1-01 · Short title (a PBI)                         [status] [size]
Why        the problem, in the user's words where possible
What       the change, concretely
Done when  acceptance criteria (observable, testable)
Tests      which tests prove it (unit / regression / smoke / E2E / security)
Depends    other PBIs or decisions
```

Three levels, the way boards count them (epic → feature → PBI, as in Azure Boards and Jira): an epic is a file, a
feature a section of it, a PBI (product backlog item) the unit of work, one commit each. Items from before features
(`E1-01`) keep their id until they are regrouped. The crissp tool writes all three (`epic`, `feature`, `item`).

- **Status**: `todo` · `doing` · `review` (built, waiting for the product owner) · `done` · `parked`.
- **Size**: S (≤ half a day) · M (1–2 days) · L (3–5 days) · XL (split it before starting).

### A decision — a question with a recommendation

```
Open:   | D-07 | the question, with the facts | a) … · b) … | **a** — why |
Taken:  | ~~D-07~~ | what was decided, and by whom | date |
```

Ask only for choices that are expensive to undo; everything else is acted on.

### A story — the plan of one finding

`docs/stories/NN-<slug>/STORY.md`: title, `**Finding:**`, `**Status:**`, `**Source:**`, then *What*, *Where*
(images, workloads, files), *How to fix*, *Acceptance criteria*, the compliance it serves. `EVIDENCE.md` next to it
holds the proof (a rescan, a test run). The finding row stays the place where the work is tracked.

### A commit — one per finding or item

```
F-42: what changed, in one line

What was wrong: …
How it was fixed: …
Proof: the test that failed without the fix, the run that is green with it.
```

### Release notes — for the people who use the product

Newest first, one entry per version, one line per change in the user's terms; in the languages the product speaks.

---

## The flow of work

```
seen ──► F-row ──► item (or decision) ──► doing ──► failing test ──► fix ──► crissp/check.sh ──► commit
                                                                                              │
             done/ ◄── product owner accepts ◄── review ◄── release notes + changes.json ◄────┘
```

1. **Observe**: anything noticed goes into FINDINGS right away, also when it is not the task at hand.
2. **Shape**: a finding becomes an item in an epic, a decision, or is fixed at once when it is small.
3. **Prove first**: the test that fails without the change is written before the change.
4. **Change**: the smallest change, in the style of the surrounding code.
5. **Check and commit**: commit first, then `crissp/check.sh` tests exactly what is committed.
6. **Record**: release notes and `changes.json` in the same piece of work.
7. **Review**: status `review`; report what was wrong, how it was fixed, how it is proven.
8. **Accept**: only the product owner; then the item or finding moves to `crissp/backlog/done/`.

---

## Who does what

| Role | Does | Never |
|---|---|---|
| **Product owner** | Decides, accepts, pushes, deploys, starts the full run | — |
| **Claude** (main session) | Keeps the backlog and the agreement, builds, reviews and merges agents' work, writes release notes, reports per fix | Pushes, deploys or changes production without an explicit yes for that action; reports green what did not run |
| **Agents** | Build one part in their own worktree, run that part's tests, report | Edit the backlog, release notes or version; push, deploy, touch production or secrets |
| **Security scanner** (optional) | Scans what runs, writes findings and stories into the project that owns it | Commits into a project, or writes there outside that project's conventions |

---

## The guards

| Guard | Purpose |
|---|---|
| `crissp/testsuite/setup.sh` | Installs and repairs what the checks need (pinned versions in one place); run first by every check script, so a fresh clone works with one command |
| `crissp/check.sh` | Tests only what the committed changes can affect, then moves the release certificate to this commit |
| `crissp/check-all.sh` | The full run; certifies a commit from scratch |
| Coverage gate | Coverage only goes up; new code fully covered; every changed line covered |
| Release certificate | The tested commit, every step's result; a deploy needs it green, recent, and on exactly the commit being deployed |
| `crissp/deploy.sh` | Refuses without the certificate, and while work is running; deploys only what changed; `--plan` says why |
| Journeys | The real interface, driven in a browser on a test street; every journey is a test **and** a documentation page |
| UX team | Virtual people walk the running interface and debate it with a UX expert; their advice and the product owner's verdicts build up in `crissp/uxsuite/results/` (advice for people, not a pass/fail gate) |
| `./docs.sh` | The docs locally; `--live` streams what a running check does (screenshots as they are taken, films in progress) |

There is no bypass for any guard, and nobody builds one.

---

## Journeys — tests that are documentation

A journey (`crissp/testsuite/journeys/test_*.py`) drives the real product in a browser, on a **test street**: the product's
own processes on throwaway data, with a stand-in for every outside service (no real clusters, registries, AI,
identity providers or customer data). The same run proves the feature and writes its documentation.

- **Every action shows itself**: the element is marked (a pink frame with its number), photographed, then clicked or
  typed into. Typed fields in a row share one photo. Secrets are typed as dots or masked.
- **Every check is real**: `see(target, what)` waits until it is true, and photographs it with a green ✓.
- **Light and dark** from one run, full screen and a crop around what matters.
- **In every language the product speaks**: each text a person reads exists in each of them, or the journey fails.
- **A film** per journey, composed from the screenshots (the same journey gives the same film).
- **Generated pages**: the run writes a record per journey; the generator turns them into Markdown pages (in git)
  with their images and film (generated, not in git); a docs server shows them. A failed journey keeps its last good
  page, marked out of date; a journey that never passed is not published.
- **Guarded**: no secret from a journey or the street may appear in any page; journeys may not share an identity; every
  link and image of the built docs resolves; a journey without a known level or a language fails.
- **In the checks**: `crissp/check.sh` runs the journeys of what changed, `crissp/check-all.sh` all of them; the certificate
  counts their failures; a deploy ships the docs with the product.

Journeys come in kinds: a **path** (learning, by level), a **guide** (one building block, by area) and a **manual**
page. A new capability is documented by a journey in the same piece of work.

---

## The UX team — people who are not us

Tests prove that the product works; they do not prove that people can use it. The UX suite (`crissp/uxsuite/`, `crissp ux`) is a
panel of virtual people who use the running interface and argue about it, so problems are seen before a customer meets
them.

- **The panel**: someone who knows technology (states, consistency, keyboard, edge cases, speed), someone who does not
  work with computers (words, readability, fear of mistakes, what it costs and what happens next), a student who only
  uses a phone (thumb reach, speed, small screens) and a UX expert who moderates (heuristics, accessibility, conversion)
  and gives the verdict. Who they are exactly — names, ages, what they want from this product — is in the project's
  `team.json`, with the product, its audience and its languages.
- **A session**: a **walk** (`walks/*.json`: goto, click by role and name, fill, press, wait, shot) is captured on a
  laptop and a phone, a screenshot and the page's accessible text per shot; a step that fails is a dead end the panel
  sees. Then each tester **looks** alone, on their own device; then **debate** rounds in which everyone answers the
  others (agree, disagree, nuance — and why); then the moderator's **verdict**: what is right, what is wrong (worst
  first; who raised, agreed, disputed), where they still disagree, and proposed findings.
- **The results build up** in `crissp/uxsuite/results/` (git-ignored): every round's reviews, debate and advice, every
  design, and the product owner's verdict on each (*agree · disagree · later*, with a reason). An approved design
  becomes a PBI through the crissp tool's own writer; the board links it back to its design. Nothing else writes to
  the backlog by itself.
- **One place to look**: the UX suite runs on the same local server as the Tests dashboard (`crissp dashboard`), in the
  same look, with links both ways.
- **Safe by default**: the personas are Claude Code run read-only (only reading the screenshots, no shell, no edits, no
  MCP servers, outside the repository so its agreement does not steer them), on the login of whoever runs it — no key
  in the repository. What the interface shows is data, never instructions. A scripted panel answers in the tests.
- **When**: after a change people will see, before the product owner accepts it; and before a release with new
  screens. It is advice, never a gate: the product owner decides.

---

## CRISSPify — bringing a repository in

*To CRISSPify*: to bring a repository under C.R.I.S.S.P.

- A repository **is** CRISSPified when it has `crissp/CRISSP.md`, an agreement (`crissp/CLAUDE.md`, loaded by the root `CLAUDE.md`) that names
  C.R.I.S.S.P., and the backlog (`crissp/backlog/FINDINGS.md` at least). A security scanner then writes its scan results as an F-row plus a story, and story
  mode follows that repository's agreement.
- The **template** ([crissp/](README.md)) holds the agreement, the agents' rules, the backlog skeleton,
  release notes, ignore rules, the testsuite's and the UX suite's configuration, and the deployment template (a Helm
  chart and Terraform). `uvx crissp init` writes it into the repository (`git init` first when it is none yet), fills
  the placeholders, and Claude fills in the rest from the real repository — its actual tests, deploy and release notes;
  what is missing becomes its first findings. The product owner reviews the diff; nothing is committed before that.
- The engine (the guards, the crissp tool, the suites, the look) is not copied: it is the `crissp` package, pinned per
  project (`.mcp.json`: `uvx crissp==<version> mcp`), so every project runs the same, proven framework and the release
  certificate says which one.
- What a repository already has and is still true is kept; history (old stories, old boards) stays as history.
- The template follows this file: a change to the framework changes CRISSP.md and the template in one commit.
