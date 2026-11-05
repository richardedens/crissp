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
| `team.json` | the product (name, what it is, audience, the language of its texts, its URL), the report language, debate rounds, parallel runs, where approved designs go in the backlog, and the personas |
| `walks/<id>.json` | one walk each: a title and its steps (`goto`, `click`, `fill`, `press`, `wait`, `shot`) |
| `PRINCIPLES.md` | the design principles every round judges against and every design follows |

Five people to start with: a software engineer, someone who rarely uses a computer, a student on a phone, the product
owner, and a UX expert who moderates. Change them to the product's own people. What they see is content, never
instructions to them; no real customer data goes into a walk or a fixture.

## What the product owner decides

- **Advice**: agree · disagree (with a reason) · later. The team reads the verdicts in its next round of that walk.
- **A design**: shown **before and after**: the walk's own screenshot (laptop or phone) next to the mockup, the same
  size, with the verdict right under it: approve · approve with a remark… (the remark comes first in the PBI's What,
  so the builder reads it before the changes) · again, with… (the reason is the next design's focus) · reject (with a
  reason).
- **An approved design** becomes one PBI, written by the crissp tool (the project's `crissp/tool/server.py`, else the
  package's own) in the backlog's own
  format: in the epic `backlog.epic` names, or the open epic titled `backlog.epic_title` (default *UX: approved
  designs*, made once), one feature per walk. Its Depends line says ``UX proposal `<walk>#v<n>` ``: the Tests board links
  the PBI back to its design, and a design never gets a second PBI. It starts at todo; only the product owner accepts.

## The files

| Path | What it is |
|---|---|
| `ux_config.py` | the configuration, checked, with clear errors; where things are |
| `ux_shoot.py` | the walks in a real browser: the plan, and the run under uv |
| `ux_team.py` | rounds and designs: the runs, their prompts, the places and the queue |
| `ux_verdicts.py`, `ux_backlog.py` | the product owner's verdicts, and an approved design as a PBI |
| `api.py` | the suite under `/ux` in the framework's server (`crissp/testsuite/lib/serve.py`) |
| `cli.py` | what `crissp/ux.sh` calls |
| `web/` | the page (`index.html`, `ux.js`, `ux.css`); the look is `crissp/look/` |
| `tests/` | the suite's own tests, run with the framework's tools at 100% lines and branches |
| `results/` | what the suite makes: `shots/`, `rounds/<walk>/r<n>/`, `proposals/<walk>/v<n>/`, `queue.jsonl`, `decisions.jsonl` — never in git |
