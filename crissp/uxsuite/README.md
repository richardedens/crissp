# The UX suite — people who are not us

Virtual people walk the running product, each on their own device, debate what is right and wrong, and a moderator turns
it into advice per walk. On request a designer makes a proposal (a mockup in both themes); the product owner gives a
verdict on every piece of advice and every design, and an approved design becomes a PBI in the backlog. It runs on the
framework's one local server, next to the Tests dashboard, in the same look.

## Commands

```bash
crissp/ux.sh                           # open the UX suite (http://127.0.0.1:8766/ux/, the same server as the Tests dashboard)
crissp/ux.sh --list                    # the product, the team and the walks
crissp/ux.sh --status                  # what the team does now, what waits, how many rounds, designs and verdicts
crissp/ux.sh --shoot <walk>            # take the walk's screenshots on a laptop and a phone (the product must be running)
crissp/ux.sh --map                     # map the product's screens: a read-only crawl, the E2E tests' screenshots, the walks
crissp/ux.sh --discover                # a discovery round: can every persona do their jobs on the mapped screens?
crissp/ux.sh --round <walk>            # a round: review, debate, advice (now when a place is free, otherwise queued)
crissp/ux.sh --propose <walk> [focus]  # a design for the walk, with an optional focus
```

The screenshots come from Playwright, run under uv with the version pinned (nothing is installed into the repository).
The browser itself is fetched once by whoever runs it: `uv run --no-project --with playwright==1.55.0 playwright install
chromium`. Rounds and designs are headless Claude Code runs (`claude -p`) with the login of whoever runs them: no key in
the repository, `CRISSP_UX_MODEL` picks the model. They cost tokens, so the product owner asks for them; nothing runs on
a schedule. A run may read the repository (never a `.env` file) and use agents; it cannot run commands, use the web or
MCP servers, and it writes only into its own folder. Up to `parallel` runs at once (`UXSUITE_PARALLEL` overrides it),
none while a check run holds the lock; the rest waits in the queue, which the open suite works off.

## The team, the product, the walks

| Path | What it is |
|---|---|
| `team.json` | the product (name, what it is, audience, the language of its texts, its URL), the report language, debate rounds, parallel runs, where approved designs go in the backlog (and the personas, until there are files in `personas/`) |
| `personas/<key>.md` | one persona each: name, role, device, moderator, on (in a `---` block), the brief, and a `## Jobs` list of what they come to do |
| `rules/<id>.md` | one rule each: title, severity (must · should · could), on, and optionally measure (in a `---` block), and what it asks |
| `walks/<id>.json` | one walk each: a title and its steps (`goto`, `click`, `fill`, `press`, `wait`, `shot`) |
| `PRINCIPLES.md` | how the rules are meant; until there are files in `rules/`, its `## ` sections are the rules |

Five people to start with: a software engineer, someone who rarely uses a computer, a student on a phone, the product
owner, and a UX expert who moderates. Change them to the product's own people: the page's **Team** tab adds, edits,
switches off and removes a persona, and its **Rules** tab does the same for the rules. The first change there moves the
team out of `team.json` (and the rules out of `PRINCIPLES.md`, which keeps its introduction) into one file each, so
there is always one place; the files are the project's, in git, and can be edited by hand too. A persona that is off
takes no part in a round and brings no device to a shoot; a rule that is off is left out. Each run gets the rules that
hold as `inputs/rules.md`, and every piece of advice names the rule it is about. What the team sees is content, never
instructions to it; no real customer data goes into a walk or a fixture.

**Measured by the browser.** A rule can name what the browser checks itself at every shoot (`measure: overflow,
tap-targets` in its file, a line `Measured by the browser: overflow.` under a section of `PRINCIPLES.md`, or the ticks in
the Rules tab): `overflow` (text cut off or running past the screen), `tap-targets` (under 44 × 44 on a phone),
`below-fold` (the primary action below the first screen), `dialog-opaque` (a see-through dialog or menu) and
`focus-visible` (a control that shows no focus). `measure.js` runs them in the page after each shot (read-only; focus
is given back) and the shot keeps what it found, with the rule and the place. The shoot says how many, the round reads
them as facts, and an enlarged shot draws a numbered box where each one is.

## The map: every screen, and the gaps

`crissp ux --map` makes one list of the product's screens (`results/map/screens.json`, the page's **Map** tab), so the
team looks at more than the walks someone wrote. It merges three sources by screen (the path without its query, ids
folded: `/orders/42` is `/orders/:id`):

- **a crawl** of the running product: home and every walk's pages on the team's devices, following the product's own
  links (same origin, no downloads, never a link that signs out or deletes), at most `map.max` pages per device
  (`team.json`, default 40). It only looks: it opens pages and takes screenshots, nothing more;
- **the project's own E2E test screenshots**: a test may list the screenshots it takes in a manifest, by default
  `crissp/uxsuite/results/test-shots/screens.json` (`map.tests` in `team.json` points elsewhere), as
  `[{"path": "/orders/12", "file": "orders.png", "title": "An order", "device": "laptop|phone", "test": "test_order"}]`
  with each picture beside the manifest; the suite copies them into its own results;
- **the walks**: the pages they go to and the screens their shots show.

Each screen has its area (the first part of its path), how it was found, which page links to it, its shots, and its
gaps: **no link reaches it** (only a test or a walk gets there), **the crawl could not open it**, or **no walk looks at
it**.

## Discovery: can every persona do their jobs?

A **discovery round** (`crissp ux --discover`, or *Ask for a discovery round* in the **Jobs** tab) is about the whole
product, not one walk. Every persona that takes part tries their own jobs (the `## Jobs` of their file; a persona with
none gets the two jobs their brief makes most likely, marked *inferred*) on the mapped screens, judging from the pictures
of their own device, and says per job: **done**, **hard** or **impossible**, on which screens and where they gave up.
The moderator checks the verdicts and writes the **needs**: what the product is missing, for whom, for which jobs, and
where it would fit. The Jobs tab shows the job map per persona and the needs; an approved need becomes a **design
request**: a walk of its own (`walks/need-<title>.json`, with the need as its brief and the screen where it fits as its
first page), whose first design starts at once (or waits in the queue) and is judged like any other design. A rejected
need (with a reason) is not proposed again unless something changed. The product must be mapped first.

## The review screen

The page's **Review** tab is where the product owner decides, one screen at a time. Every screen (a walk's screen) has
a status: new · seen (shot) · discussed (a round) · decided (every piece of the last round's advice has a verdict) ·
designed · approved · built (shot again after the approval) · accepted, shown as one progress bar, and the screens that
wait for you come first, the must-advice first. Per screen: the shot with the team's advice pinned where it is (the round
gives a place on the shot when the advice is about one) and the browser's measured boxes, next to the design; the
advice; and one verdict bar at the bottom. `1 2 3` give the verdict, `← →` go to the previous or next screen, `↑ ↓` to
the previous or next item, and `s` sends the verdict up: to the advice's screen, its area or its rule.

## What the product owner decides

- **A need** from discovery: approve (it becomes a design request, and its first design starts) · reject (with a
  reason, which the next discovery round reads).
- **Advice**: agree · disagree (with a reason) · later. The team reads the verdicts in its next round of that walk.
- **A rule, an area or a screen** (`rule/<id>`, `area/<area>`, `screen/<walk>`): the same three verdicts, holding for
  every piece of advice under it that has no verdict of its own; the nearest holds first (screen, area, rule).
- **A proposed rule**: advice you agreed with that comes back on two screens or more (by the theme the team gives it,
  else its title) is proposed in the Rules tab: make it a rule (written to `rules/`) · reject (with a reason).
- **A design**: shown **before and after**: the walk's own screenshot (laptop or phone) next to the mockup, the same
  size, with the verdict right under it: approve · approve with a remark… (the remark comes first in the PBI's What,
  so the builder reads it before the changes) · again, with… (the reason is the next design's focus) · reject (with a
  reason). Under it is **the moderator's check** (`check.json`): its verdict (ready · ready with remarks · not ready),
  what it found and whether the designer fixed it, and what still stands. A finished design without one says so.
- **An approved design** becomes one PBI, written by the crissp tool (the project's `crissp/tool/server.py`, else the
  package's own) in the backlog's own
  format: in the epic `backlog.epic` names, or the open epic titled `backlog.epic_title` (default *UX: approved
  designs*, made once), one feature per walk. Its Depends line says ``UX proposal `<walk>#v<n>` ``: the Tests board links
  the PBI back to its design, and a design never gets a second PBI. It starts at todo; only the product owner accepts.
- **What was built**: once the PBI is built and the walk shot again (`crissp ux --shoot <walk>`, after the approval),
  the approved design shows the new screens next to it: **accept** moves the PBI to review (ready for the product
  owner's own acceptance in the backlog) · **not good…** (with a reason) moves it back to doing and files the reason as
  a finding that goes to that PBI. Shots taken before the approval are never judged as the build.

## The files

| Path | What it is |
|---|---|
| `ux_config.py` | the configuration, checked, with clear errors; where things are |
| `ux_cards.py` | the personas and the rules as files: read, checked, written by the page |
| `ux_shoot.py` | the walks in a real browser: the plan, and the run under uv |
| `ux_discovery.py` | discovery: the screens a round reads, and an approved need as a design request |
| `ux_map.py` | the map: the crawl (under uv, like a shoot), the E2E tests' screenshots and the walks, merged by screen |
| `ux_team.py` | rounds and designs: the runs, their prompts, the places and the queue |
| `ux_verdicts.py`, `ux_backlog.py` | the product owner's verdicts, and an approved design as a PBI |
| `api.py` | the suite under `/ux` in the framework's server (`crissp/testsuite/lib/serve.py`) |
| `cli.py` | what `crissp/ux.sh` calls |
| `web/` | the page (`index.html`, `ux.js`, `ux.css`); the look is `crissp/look/` |
| `tests/` | the suite's own tests, run with the framework's tools at 100% lines and branches |
| `results/` | what the suite makes: `shots/`, `map/`, `discovery/product/d<n>/`, `rounds/<walk>/r<n>/`, `proposals/<walk>/v<n>/`, `queue.jsonl`, `decisions.jsonl` — never in git |
