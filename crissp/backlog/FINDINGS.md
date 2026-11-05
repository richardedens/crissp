# Findings — observations collected while working

Collected while working. Each becomes (part of) a backlog item or is closed with a reason.

| # | Seen | Observation | Goes to |
|---|---|---|---|
| F-01 | src/crissp/cli.py (2026-11-05) | crissp refused every option meant for a guard (crissp check --plan, crissp deploy --cluster, crissp ux --shoot <walk>): argparse's REMAINDER does not pass a leading --option on to a subcommand. Found while building the README's demo; the package test only ran commands without options. Fixed: crissp splits the command line at the guard's name and passes the rest untouched; test_cli.py proves every guard's options (red before, green after). | fixed (0.1.0, before the first commit) |
| F-02 | crissp/uxsuite/ux_backlog.py (2026-11-05) | Approving a design in an installed project (crissp init) failed with 400 "crissp/tool/server.py is missing": the UX suite only looked for the crissp tool inside the project, which a package-installed project no longer has. Its tests missed it because their example project carries a copy of the tool. Found by clicking Approve in the README demo. Fixed: the project's own tool, else the engine's (test_an_installed_project_writes_with_the_engines_tool, red before, green after). Also added: Before / After in every design (the walk's screenshot on laptop or phone next to the mockup, same size) with Approve right under it. | fixed (0.1.0, before the first commit) |
| F-03 | crissp/check-all.sh, the first full run (2026-11-05) | The CVE audit flagged pytest 8.4.2 (PYSEC-2026-1845: on UNIX it relies on /tmp/pytest-of-user directories, local users can cause a denial of service or worse); and test_ux_sh_lists_reports_and_refuses_what_it_does_not_know read the run's own project (inherited CRISSP_ROOT) instead of its copy, so it failed only inside a full run. Fixed in 07df295: pytest 9.0.3 pinned, the test starts ux.sh without CRISSP_ROOT; the next full run was green. | fixed (0.1.0, 07df295) |
<!-- CRISSP: the first findings — what CRISSPify noticed is missing or risky (no guards yet, secrets or dumps that
could reach git or an image, untested parts, missing release notes, docs that are out of date). -->
