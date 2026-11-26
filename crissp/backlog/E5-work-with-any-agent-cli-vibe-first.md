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
