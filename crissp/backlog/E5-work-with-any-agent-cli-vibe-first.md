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

### E5-F1-02 · platform detection for the Vibe onboarding (Windows, macOS, Linux)        [doing] [S]
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
