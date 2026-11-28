# E5 · Work with any agent CLI, Vibe first

Why: The guards, the crissp tool and the backlog formats are agent-agnostic; only the onboarding assumes Claude Code. A
project brought in with crissp init should work the same under Mistral Vibe: the MCP server registered, the folder
trusted, the agreement read via AGENTS.md.

## E5-F1 · crissp init and repair onboard Vibe                                           [todo]
Why        A Vibe session in a brought-in project gets the crissp tools and a trusted folder, without hand-editing
           ~/.vibe or writing .vibe/config.toml by hand.

### E5-F1-01 · init writes .vibe/config.toml and trusts the folder                       [review] [S]
Why        Today init writes only .mcp.json (Claude Code); a Vibe user must hand-write .vibe/config.toml and edit
           trusted_folders.toml themselves.
What       crissp init writes .vibe/config.toml from a new template file (uvx crissp==<version> mcp, the same pin as
           .mcp.json), merges .vibe/ into the project's .gitignore, and adds the project folder to
           $VIBE_HOME/trusted_folders.toml when a Vibe home exists (never removing entries, never overwriting the
           config); with no Vibe home it still writes the config and says so. crissp repair does the same for projects
           brought in earlier.
Done when  In a throwaway project with a tmp VIBE_HOME, crissp init --yes writes .vibe/config.toml pinning the running
           crissp, .gitignore holds .vibe/, and trusted_folders.toml trusts the project; with no Vibe home the config is
           still written and the skip is said; a second init keeps an existing .vibe/config.toml; crissp repair adds
           what is missing in an older project.
Tests      package_tests/test_cli.py (init), package_tests/test_package.py (the wheel's init), tests/test_repair.py
           (repair)
Depends    —

### E5-F1-02 · platform detection for the Vibe onboarding (Windows, macOS, Linux)        [review] [S]
Why        The onboarding must work the same on every system: on Windows the trust file stays valid TOML and init says
           itself that the bash guards run inside WSL 2 (F-14).
What       Detect the system (os.name/sys.platform: Windows, macOS, Linux) and whether vibe is installed
           (shutil.which('vibe') in addition to the VIBE_HOME/~/.vibe directory). Write the project path into
           trusted_folders.toml as a proper TOML basic string (json.dumps, so backslashes escape) and match both
           backslash and forward-slash spellings when checking whether the folder is already trusted. init prints one
           line: system, whether vibe was found, what was done (trusted / already trusted / start vibe once / not
           installed); on native Windows it also prints that the guards are bash scripts and run inside WSL 2. crissp
           repair's trust does the same escaping.
Done when  Tests with a faked Windows path prove the TOML stays valid and an existing forward-slash entry is not
           duplicated; tests with monkeypatched os.name/sys.platform and shutil.which prove each detection branch prints
           its line on Windows, macOS and Linux; init on native Windows also prints the WSL 2 note (F-14).
Tests      test_cli.py (system detection, vibe found/not found, TOML escaping), test_repair.py (trust escaping and both
           path spellings)
Depends    E5-F1-01

## E5-F2 · Mistral Vibe sessions work as Claude sessions do                              [review]
Why        A Vibe session, in the terminal or the desktop app, gets the crissp tools, shows on the Activity page with
           the same warnings, follows the same habits for small sessions, and can run the UX team.

### E5-F2-01 · The crissp tools load in a Vibe session, proven (F-100)                   [review] [S]
Why        Vibe's desktop app started the crissp server from its own folder with a stripped environment: no tools.
What       .vibe/config.toml names the project's folder (cwd, CRISSP_ROOT), uvx by full path, 60 s to start; init and
           repair write it per machine, .vibe/ out of git.
Done when  A real Vibe session in a project crissp init made finds brief and backlog with Vibe's tool search; the config
           started from another folder with Vibe's environment lists the tools.
Tests      tests/test_vibe.py, tests/test_repair.py, package_tests/test_cli.py, package_tests/test_vibe_session.py
           (needs vibe installed)
Depends    —

### E5-F2-02 · The Activity page reads Vibe sessions (F-101)                             [review] [M]
Why        /activity read only Claude Code's transcripts.
What       lib/vibesessions.py reads VIBE_HOME/logs/session/unified; /activity lists Vibe sessions with source, prompt,
           step, subagents and the 300k warning.
Done when  A Vibe session of the repository, written in the last half hour, shows on /activity with its latest step and
           history; another repository's, an old one and a subagent do not show as sessions.
Tests      tests/test_vibesessions.py, tests/test_activity_page.py
Depends    —

### E5-F2-03 · Sessions that stay small, the Vibe way (F-102)                            [review] [S]
Why        The agreement's habits named only Claude Code's commands.
What       The section (CRISSP.md, the agreement, the template's, synced by repair) names Vibe's: /clear or a new
           desktop session, /compact <what to keep>, auto_compact_threshold, the task tool's explore agent.
Done when  The section in all three names Vibe's commands.
Tests      tests/test_template.py
Depends    —

### E5-F2-04 · The UX team on any installed agent CLI (F-103)                            [review] [M]
Why        The personas ran only on claude -p.
What       CRISSP_UX_CLI, else Claude Code when installed, else Vibe; on Vibe read-only in the run's folder, no shell,
           web or MCP, never a .env.
Done when  A round on Vibe starts vibe -p in its folder with only read_file, write_file and edit, MCP off and reads
           limited to the UX suite and the agreement.
Tests      uxsuite/tests/test_ux_team.py
Depends    —

### E5-F2-05 · The context budget as checks (F-104)                                      [review] [S]
Why        The habits against screenshots and whole reads in the main thread were advice only.
What       /activity says per session when the main thread holds 10 or more images or read a file past 800 lines whole,
           for Claude and Vibe.
Done when  Ten screenshots and a whole read of a big file are flagged; a read with offset and limit, a small file and a
           subagent's read are not.
Tests      tests/test_activity.py, tests/test_vibesessions.py, tests/test_activity_page.py
Depends    —

### E5-F2-06 · Vibe uses crissp fully without exploring first                            [review] [M]
Why        A Vibe session explored for ten steps, hit the one-minute tool budget, started the full run on a vague wish,
           and its full run was red on a Mac for reasons outside the code (F-105 to F-112).
What       The root AGENTS.md gives the first moves; the crissp skill is the playbook; the tools answer within a minute;
           check-all needs asked: true; the Vibe config carries the terminal PATH; /activity reads packed Vibe sessions.
Done when  A Vibe session in a crissp project calls brief first, checks with run check and status within the budget,
           asks before the full run, and its check-all is green on a Mac.
Tests      test_template, test_repair, test_cli (agent files), test_crissp_tool (budget, asked), test_serve, test_vibe
           (PATH), test_lint (bash 3.2), test_vibesessions (packed)
Depends    —
