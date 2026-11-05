# C.R.I.S.S.P. backlog

The single source of truth for the work on C.R.I.S.S.P.: plain Markdown next to the code, versioned with it. *How* we
work is in [CLAUDE.md](../CLAUDE.md) and [CRISSP.md](../CRISSP.md); this directory holds *what*.

| File | What it holds |
|---|---|
| [PLAN.md](PLAN.md) | The why, the principles and the order of work |
| [DECISIONS.md](DECISIONS.md) | Open decisions that need the product owner, and decisions already taken |
| [FINDINGS.md](FINDINGS.md) | Observations collected while working (F-xx) |
| `E<n>-<slug>.md` | One epic per file, with its features and their PBIs |
| `done/` | Accepted epics and fixed findings (same file names) |

## How an epic, a feature and a PBI look

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

Status: `todo` · `doing` · `review` · `done` · `parked`. Size: S (≤ half a day) · M (1–2 days) · L (3–5 days) ·
XL (split it before starting).

## Definition of done (every item, no exceptions)

1. **Tested** — a test that failed without the change; new and changed code fully covered.
   The libraries that decide what is green are held at 100% lines and branches; `crissp/check.sh` for a change,
   `crissp/check-all.sh` for the full run.
2. **Documented** — the docs say what changed. The README and the Markdown files in `crissp/`.
3. **Safe** — nothing secret printed or stored in plain text; access changes need a person's yes.
4. **Recorded** — release notes in the same piece of work. `CHANGELOG.md`, for the version in `VERSION`.
5. **Reviewed** — the product owner has seen the result (`review` → `done`).
