# E9 · Work in six stages, with help at every one

Why: The product owner asked to see where the work is in the stages of how we work (1 Discover, Plan, Build, Verify,
Review, Release), which until now were only a picture on the website, and to have Claude and Vibe help with each stage:
set up the UX suite and discover, plan, build, review. Every session, and every <!-- CRISSP --> prompt, should say the
stage and offer that help.

## E9-F1 · Where the work is, and help with each stage                                   [review]
Why        One look says which stage the work is in and what waits for whom, and one click starts Claude or Vibe on it.

### E9-F1-01 · The six stages, read from the repository                                  [review] [M]
Why        The stages were a picture (docs/images/agentic-sdlc.svg); nothing said where the work is now.
What       lib/stages.py: per stage what is in it and whose move it is (setup, work, yours, clear), read from the
           backlog through the crissp tool's parser, the release certificate, git, VERSION, CHANGELOG.md and the UX
           suite's state (its map and discovery round when it has them); the stage the work is in, following the flow; a
           prompt per stage for Claude and Vibe that keeps the product owner's rules.
Done when  Each stage's status and lines follow from a throwaway repository's backlog, certificate, tags and UX state;
           current follows the flow; every prompt says what never happens.
Tests      tests/test_stages.py
Depends    —

### E9-F1-02 · The crissp tool stage, for Claude and Vibe alike                          [review] [S]
Why        A session should say the stage and help with it without reading the backlog files.
What       The crissp tool stage: where the work is and every stage in a few lines; with a stage, what is in it and its
           instructions. The MCP instructions tell a session to call it at the start and on a <!-- CRISSP --> prompt.
           Vibe gets it through .vibe/config.toml (the same server).
Done when  stage answers over MCP from the project's lib/stages.py or the engine's; a wrong stage is an error answer,
           never a crash.
Tests      tests/test_crissp_tool.py
Depends    E9-F1-01

### E9-F1-03 · The Stages page on the dashboard                                          [review] [M]
Why        The product owner wants to see the stages and ask for help from the dashboard.
What       /stages (dashboard/stages.html, stages.js, stages.css; data /dashboard/stages.json): the stage the work is
           in, the six stages in order with their status and lines, and per stage Ask Claude, Ask Vibe and Copy the
           sentence (claude/vibe "crissp: help me with <stage>"); Discover starts the UX team's rounds as the UX page
           does. Stages comes first in the one top bar.
Done when  The page renders a state with the current stage marked, every stage's commands, escaped text and the Discover
           actions; the server serves the page and its data.
Tests      tests/test_stages_page.py, tests/test_serve.py, tests/test_look.py
Depends    E9-F1-01

### E9-F1-04 · Every session opens with the stage and offers its help                    [review] [S]
Why        On a <!-- CRISSP --> prompt Claude and Vibe should say which stage the work is in and help, for example set
           up the UX suite.
What       The agreement's own section The six stages (template and this repository), CRISSP.md's flow names them;
           crissp repair brings the section into projects brought in earlier; crissp init's last lines say it.
Done when  The template has the section; repair adds it before Sessions that stay small (else before Working with the
           product owner, else at the end) or replaces an old one.
Tests      tests/test_repair.py, tests/test_template.py
Depends    E9-F1-02
