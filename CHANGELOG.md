# Release notes

What changed in C.R.I.S.S.P., newest first. One entry per version (the version is in `VERSION`).

## 0.1.0 — unreleased

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
