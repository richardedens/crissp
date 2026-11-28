---
name: crissp
description: How to work in a C.R.I.S.S.P. repository with the crissp tools. Use it when you start work, check work, write a finding, decision or backlog item, or want the dashboard.
---

# Working with the crissp tools

The crissp MCP server (`crissp mcp`; in Mistral Vibe the `mcp_crissp.*` tools) answers questions about the
repository so you do not have to read files for them. Each answer is a few lines. Use it instead of exploring.

## Which tool, when

| You want to know or do | Call | Never instead |
|---|---|---|
| Where the work stands (version, certificate, doing, review, next, open decisions) | `brief` | read the backlog files |
| One finding, decision or item; the items with a status; the open findings | `backlog` with `id`, `status` or `open` | grep `crissp/backlog/` |
| What a check would run and how long | `run` with `what: check-plan` | guess |
| Check your work (only what changed since the last green state) | `run` with `what: check`, then `status` | run the test scripts by hand |
| How a started check is doing | `status`; `wait: true` waits until it ends | wait on the pid |
| Note something you saw | `finding` (`seen`, `observation`, `goes_to`) | edit FINDINGS.md |
| A choice for the product owner | `decision` (`question`, `options`, `recommendation`) | decide it yourself |
| New work | `epic`, `feature`, `item` | edit an epic file |
| Move an item to doing or review | `item` with `id` and `status` | mark it done: that is the product owner's |
| See the results | `dashboard` (it answers the address) | start a second server |

## The order of a session

1. `brief`. If something is in `doing`, that is the work; otherwise ask which item, or take the first `todo`.
2. `backlog` with that item's id: what it needs and when it is done.
3. Write a failing test, then the change. Commit what you changed: the checks test what is committed.
4. `run` `check`, then `status` with `wait: true`. Red: read only the failing lines, fix, commit, check again.
5. Move the item to `review` with `item`, and tell the product owner what is done and how it is proven.

## What waits for the product owner's yes

- `run` with `what: check-all` (the full run, several minutes): only when the product owner asked for the full run.
- A push, a tag, a publish, a deploy: never through these tools; the product owner does them.
- Marking anything done.

## When a tool is slow or missing

- A call that does not answer within your tool time limit: call `status` (for a run) or `dashboard` again; a run or
  the dashboard keeps going in the background, it is not lost.
- No crissp tools at all: the project's `.vibe/config.toml` (Vibe) or `.mcp.json` (Claude Code) is missing or old.
  Ask the product owner to run `crissp repair --yes` in a terminal and restart the agent.

## Keep the session small

Every step resends the whole conversation. Ask the tools narrow questions, read the part of a file you need, and
start a fresh session per item (`/clear`). Heavy output (a browser check, screenshots, a wide code search) belongs in
a subagent that reports text.
