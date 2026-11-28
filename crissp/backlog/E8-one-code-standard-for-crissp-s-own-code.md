# E8 · One code standard for crissp's own code

Why: crissp asks every project to lint its backend and frontend; its own Python, JavaScript and CSS should be held to
one written standard too, read the same by the checks, an editor and an agent. Ported from the local branch backup-
local-main (its E6), on today's main.

## E8-F1 · crissp's own code held to one standard                                        [review]
Why        the rules live in one place (pyproject.toml, crissp/testsuite/lint/, .editorconfig), the steps pass no flags
           of their own, and the code is clean against them

### E8-F1-01 · More of ruff's rules, and the tests they found                            [review] [S]
Why        ruff ran its defaults plus three rules over crissp's own Python (F-90, F-91, F-92)
What       pyproject.toml selects E, W, F, B, S, SIM, I, N, UP, C4, RUF, PLW1510, D100; the 47 findings fixed, among
           them a test that could not fail and an unaudited URL open
Done when  ruff check is clean with the rules in pyproject.toml alone
Tests      test_python_lint, test_crissp_tool::test_served_opens_only_this_machines_address
Depends    —

### E8-F1-02 · The engine on the standard library, and no copied code                    [review] [S]
Why        only the wheel's metadata said the engine is standard library only, and nothing found copied code (F-93)
What       python-lint runs crissp/testsuite/lint/python_lint.py: ruff, an import scan of the runtime code, pylint's
           duplicate-code check (pinned, dev-only)
Done when  a foreign import or a six-line copy fails python-lint by file
Tests      test_python_lint
Depends    —

### E8-F1-03 · The session pages' CSS and script in files                                [review] [S]
Why        their CSS and JavaScript were Python strings no linter reads (F-94)
What       dashboard/sessions.css, measure.css and session-tabs.js, read at load and still inlined
Done when  no CSS left in sessionview.py or measure.py; ESLint lints session-tabs.js
Tests      test_measure::test_the_session_pages_css_and_script_live_in_files_a_linter_reads
Depends    —

### E8-F1-04 · An .editorconfig for crissp                                               [review] [S]
Why        editors wrote files with their own defaults (F-95)
What       .editorconfig at the root with the checks' choices
Done when  an editor writes UTF-8, LF, final newline, 4-space Python, 120
Tests      test_python_lint::test_an_editor_writes_files_the_way_the_checks_hold_them
Depends    —

### E8-F1-05 · One layout: ruff format, once, then checked                               [review] [M]
Why        crissp's Python has no layout standard and E501 is still off (157 lines over 130)
What       ruff format over src/, crissp/ and site/ in a commit of its own, listed in .git-blame-ignore-revs; python-
           lint adds ruff format --check; E501 on
Done when  ruff format --check and E501 clean; git blame skips the layout commit
Tests      test_python_lint: the step runs ruff format --check, E501 selected, the commit in .git-blame-ignore-revs
Depends    the open pull requests merged (it touches every Python file)

### E8-F1-06 · crissp's own CSS linted                                                   [review] [S]
Why        lint.sh runs ESLint on crissp's JavaScript but nothing reads its CSS (look.css, the dashboard's, the
           uxsuite's, the site's)
What       stylelint (pinned in crissp/testsuite/lint/) over every tracked CSS file, with the findings fixed
Done when  a CSS mistake fails the lint step by file
Tests      test_lint: every tracked CSS file is linted
Depends    —
