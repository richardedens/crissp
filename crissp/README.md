# crissp/ — the framework, and how this repository uses it

This folder is the engine of the `crissp` package, exactly as it ships (`pyproject.toml` lists what goes into the wheel,
under `crissp/engine/`). It also holds this repository's own data, because C.R.I.S.S.P. is built the C.R.I.S.S.P. way:
its agreement, its backlog and its configuration. Those never go into the package.

| Path | What it is | In the package |
|---|---|---|
| [CRISSP.md](CRISSP.md) | The framework: Consistent, Repeatable, Innovative, Secure, Scalable, Programming | yes |
| `check.sh`, `check-all.sh`, `deploy.sh`, `test.sh`, `ux.sh` | The guards: test what changed, the full run, the deploy behind the release gate, the one local server, the UX suite. `crissp check`, `check-all`, `deploy`, `dashboard` and `ux` run them for a project | yes |
| [tool/](tool/server.py) | The crissp MCP server (`crissp mcp`): `brief` and `backlog` so Claude asks for lines instead of reading files; `finding`, `decision`, `epic`, `feature` and `item` write them in the backlog's own format (never `done`); `run`, `status` and `dashboard` start the checks in the background (never a deploy) | yes |
| [testsuite/](testsuite/README.md) | The impact map, the step runner, the coverage gate, the release certificate, the deploy plans and the Tests dashboard, all driven by a project's `testsuite/suites.json` | the engine (`lib/`, `dashboard/`, the scripts) |
| [uxsuite/](uxsuite/README.md) | Virtual people walk the running product, debate it and advise; designs on request; an approved design becomes a PBI | the engine (not `team.json`, `walks/` or `results/`) |
| [look/](look/) | One look for the dashboard and the UX suite: tokens, top bar, components, dark by default, the bundled Figtree font (OFL-1.1) | yes |
| [deploy/](deploy/README.md) | The deployment template: a Helm chart (backend, frontend, PostgreSQL with a nightly backup, behind Traefik), Terraform for the cluster side, `deploy.json`, and `check.sh` that proves them | yes; `crissp init` copies the chart, Terraform and `deploy.json` into a project |
| [template/](template/) | What `crissp init` writes into a project (below) | yes |
| [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md) | This repository's agreement and the rules for agents | no |
| [backlog/](backlog/README.md) | This repository's work: PLAN, DECISIONS, FINDINGS, one file per epic, done/ | no |
| `testsuite/suites.json`, `changes.json`, `accepted-risks.json`, `coverage-baseline.json`, `results/` | This repository's parts, fixes, accepted risks, coverage baseline and run results | no |
| `testsuite/tests/`, `testsuite/package_tests/`, `uxsuite/tests/`, `deploy/tests/` | The engine's own tests (`deploy/tests` ships: it proves a project's chart) | only `deploy/tests` |

## `crissp init` — bringing a project in

`crissp init` in an empty folder starts a project; in an existing repository it CRISSPifies it. It runs `git init` when
the folder is no repository yet (unless `--no-git`), writes only files that do not exist yet, merges the ignore rules
into `.gitignore`, and commits nothing: the product owner reviews the diff first.

| From the package | Lands in the project as | Filled by |
|---|---|---|
| `template/CLAUDE.md`, `template/AGENTS.md` | the short root files that point into `crissp/` | placeholders |
| `template/crissp/CLAUDE.md`, `template/crissp/AGENTS.md` | the agreement and the agents' rules for this product | placeholders + Claude (`<!-- CRISSP: … -->` blocks) |
| `template/crissp/backlog/` | `crissp/backlog/`: README, PLAN, DECISIONS, FINDINGS, done/ | placeholders + Claude (first findings: what is missing) |
| `template/crissp/testsuite/` | `crissp/testsuite/suites.json` (the product's parts), `changes.json`, `accepted-risks.json` | Claude, per stack |
| `template/crissp/uxsuite/` | `crissp/uxsuite/team.json` (the product, the personas) and a first walk | Claude |
| `CRISSP.md` | `crissp/CRISSP.md`, so the agreement's links work (never edited in a project) | copied as is |
| `deploy/helm`, `deploy/terraform`, `deploy/deploy.json`, `deploy/.env.production.example` | `crissp/deploy/`: the product's own chart and Terraform (skip with `--no-deploy`) | the product |
| `template/mcp.json` | `.mcp.json`: `uvx crissp==<version> mcp`, so the project pins its crissp | placeholders |
| `template/CHANGELOG.md`, `template/VERSION` | release notes and the version | placeholders |
| `template/gitignore.crissp` | rules **merged** into `.gitignore`, never replacing it | `crissp init` |

Placeholders: `{{PRODUCT}}` (`--product`, default the folder's name), `{{OWNER}}` (`--owner`), `{{REPOSITORY}}`,
`{{DATE}}`, `{{VERSION}}` (the product's first version, 0.1.0) and `{{CRISSP_VERSION}}`. Then Claude reads the
repository and fills every `<!-- CRISSP: … -->` block with what is true for the project.

A repository counts as CRISSPified when it has `crissp/CRISSP.md`, a root `CLAUDE.md` that imports `crissp/CLAUDE.md`,
and `crissp/backlog/FINDINGS.md`. A security scanner can then write its findings there as F-rows.

## Keeping the template right

- The template follows CRISSP.md: a change to the framework changes CRISSP.md **and** the template, in one commit.
- `<!-- CRISSP: … -->` blocks say what belongs there, so Claude (and a person) knows what to write; a CRISSPified
  repository has none left.
- The template never contains anything of a specific project: no product names, hosts, people or customer data
  (`testsuite/tests/test_generic_names.py` and `test_template.py` check it).
