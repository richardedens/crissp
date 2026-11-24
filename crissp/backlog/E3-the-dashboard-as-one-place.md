# E3 · The dashboard as one place

Why: The product owner noticed that the menu differs on every page (Tests, Workers, UX, Sessions), that the backlog
shows where work stands but not how it moves, and that the dashboard does not tell what the orchestrator and its agents
are doing right now. One server, one top bar, and the work in motion visible while it happens.

## E3-F1 · One top bar on every page                                                     [todo]
Why        Every page of the dashboard server (Tests, Backlog, UX, Workers, Activity, Sessions) shows the same brand and
           the same sections in the same order, the open one marked, so moving between them never surprises.

### E3-F1-01 · The sections come from one list in the shared look                        [todo] [S]
Why        Each page wrote its own menu (Tests · UX · Workers · Sessions on one, Tests · UX · Workers on two, Tests · UX
           · Sessions on the sessions pages), so they drifted.
What       look.js holds the one list of sections (Tests, Backlog, UX, Workers, Activity, Sessions) with their addresses
           from the server's root, and fills every top bar's `<nav class="sections" data-current="…">`. The Tests
           dashboard, the workers page, the UX suite and the Python-built session and report pages have that empty nav
           and nothing hand-written; Backlog opens the board (the dashboard's #board). The brand reads "<product> ·
           <section>" everywhere.
Done when  On every page the same sections in the same order, the open one marked; no page holds its own section links;
           a test fails when one does.
Tests      test_look: look.js has the list once; every page (dashboard/index.html, workers.html, uxsuite/web/index.html,
           sessionview.top_bar, the measure report) has the empty sections nav with its data-current and no section
           links of its own.
Depends    —

## E3-F2 · Backlog movement                                                              [todo]
Why        The product owner sees what moved on the board, from where to where and when (committed or not yet), and how
           long a PBI has stood in its column.

### E3-F2-01 · Every PBI's moves, from git and the working tree, on the board            [todo] [M]
Why        The board is a snapshot: a PBI that went to review an hour ago looks the same as one that stands there for a
           week.
What       lib/movement.py replays the backlog's epic files through every commit that changed them, with the crissp
           tool's own parser (three-level ids too), and adds the working tree's not yet committed state: per PBI each
           move (from, to, when, commit or "not committed"). collect.py puts it into the data; the board shows on each
           card since when it stands in its column, a "Moved recently" strip above the lanes (newest first, from → to,
           when), and each card's moves in its details.
Done when  After a status change the board shows the move within seconds (not committed yet), after the commit with its
           commit; each card says how long it stands in its column; a new PBI shows as "new → todo".
Tests      test_movement: a throwaway repository with commits moving E1-F1-01 todo → doing → review and an uncommitted
           move to doing: the moves, their order and times, "not committed"; a file in cp1252 in history read (F-16).
           test_collect: the data carries the moves.
Depends    —

## E3-F3 · What the orchestrator and its agents do now                                   [todo]
Why        While Claude works, the product owner sees live which session is busy, what its main thread (the
           orchestrator) is doing and since when, which subagents run, what each does now, and which finished.

### E3-F3-01 · An Activity page: the live sessions, their orchestrator and agents        [todo] [M]
Why        The sessions pages are written afterwards; while Claude works, nothing shows what the main thread and its
           subagents are doing.
What       lib/activity.py reads this repository's Claude Code transcripts that changed in the last 30 minutes: per
           session the last prompt, what the orchestrator does now (its last tool call: the tool, the description, path
           or command, masked like the sessions pages) and since when, quiet after two minutes; every subagent it
           started (type and description), running (no result yet) with its own latest action from its transcript, or
           finished and when. Served as /dashboard/activity.json; /activity is a page (dashboard/activity.html) that
           asks it every two seconds. Only what Claude sent to its tools, never what came back.
Done when  While a session runs with two subagents, the page shows the session, the orchestrator's current step, both
           agents with their latest action, and an agent's finish within seconds; with nothing running it says so and
           links the Sessions pages.
Tests      test_activity: stand-in transcripts (a session with a running and a finished Agent call, the subagents'
           transcripts): the state; an old session left out; a secret in a command masked. test_serve: /activity and
           /dashboard/activity.json.
Depends    E3-F1-01
