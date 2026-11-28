"""Put back in place what a project has out of place (F-10, D-02): `crissp repair` says it, `crissp repair --yes` does it.

    python3 crissp/testsuite/lib/repair.py [--yes]

The project is CRISSP_ROOT, or the current directory. What it puts in place:

    steps      suites.json still holds the old template's steps on src/ (and src/ is not there), or no steps at all:
               the default parts' steps from the template (app/backend, app/frontend; each exists once its part does).
               The project's own path rules and shared ground stay; the template's shared ground is added
    ux-url     the UX suite walks the old template's 127.0.0.1:5173 while app/frontend has no Vite dev server: the local
               stack's address (deploy.json compose.url with its default port, else 127.0.0.1:8080)
    ux-extra   anything in crissp/uxsuite/ that is not its configuration (a prototype, notes): moved to docs/ux/<name>.
               The product lives in app/; a design is `crissp ux --propose <walk>`
    agreement  crissp/CLAUDE.md says the tools come from `crissp/tool`, which an installed project does not have: the
               crissp MCP server, registered in .mcp.json
    missing    a file of the template's crissp/ folder is not there (the uxsuite's .gitignore, a backlog skeleton, the
               testsuite's changes.json …): made from the template, filled in as crissp init does; first-visit.json
               only while the project has no walks of its own
    crissp-md  crissp/CRISSP.md is not this crissp's: replaced by it (it is the framework's text, never a project's own)
    gitignore  .gitignore lacks some of the framework's rules (secrets, dumps, results): added, nothing removed
    sessions   crissp/CLAUDE.md's "Sessions that stay small" is not this crissp's (F-21): the section is crissp's own,
               so it is replaced by the template's, or added before "Working with the product owner" (else at the end)
    stages     crissp/CLAUDE.md's "The six stages" is not this crissp's (F-130: a session says the stage the work is in
               and offers help with it): replaced by the template's, or added before "Sessions that stay small"
               (else before "Working with the product owner", else at the end)
    vibe-pin   .vibe/config.toml pins an older crissp than the one that repairs (F-27): the pin moves, as in .mcp.json
    git-hook   .githooks/pre-commit is not there, or core.hooksPath is not set (F-50): the template's hook, and
               core.hooksPath .githooks, so git runs the lint steps before every commit; never over a core.hooksPath
               or .git/hooks of the project's own (said instead). The framework's own checkout: only turned on
    vibe       .vibe/config.toml is not there, does not name this folder (F-100: cwd and CRISSP_ROOT, which Vibe's
               desktop app needs; only a config that holds crissp's server alone is written anew), or the project is
               not trusted in Vibe's trusted_folders.toml
               (F-24; VIBE_HOME, else ~/.vibe): the config is made from the template with this crissp's pin, and the
               folder is added to the trusted list (never removed; a folder marked untrusted, or a file crissp does
               not know, is left as it is: lib/vibe.py); with no Vibe home only the config is made

And what needs a person, said but not done: not brought in (no crissp/: crissp init); no commit yet; no docker-compose.yml (nothing runs for the UX suite to walk);
a move whose place is taken. It never deletes, never overwrites what a project wrote (only the spots named above),
never changes the backlog's content and never commits. The framework's own repository is left as it is, but for
its git hook and its .vibe/config.toml.
Exit 0: nothing left to say, or --yes put it in place; 1: something is out of place or needs you; 2: wrong arguments.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import hook  # F-50: the lint before every commit, shared with crissp init
import vibe  # F-26: Vibe's trusted folders, shared with crissp init

ENGINE = Path(__file__).resolve().parents[2]  # the engine: crissp/ in the framework's checkout, crissp/engine/ installed
TEMPLATE = ENGINE / "template"
SUITES = Path("crissp/testsuite/suites.json")
TEAM = Path("crissp/uxsuite/team.json")
CHANGES = Path("crissp/testsuite/changes.json")
OLD_URL = "http://127.0.0.1:5173"
OLD_KEYS = {"unit", "lint"}
RENAMED = {"unit": "backend", "lint": "backend-lint"}  # a project's own path rule follows its step to the new name
OLD_PATHS = {"src/", "tests/"}
UX_CONFIG = {"team.json", "walks", "personas", "rules", "PRINCIPLES.md", "README.md", ".gitignore", "results", ".DS_Store", "__pycache__"}
SKIP = {"__pycache__", ".DS_Store", "results"}
FIRST_WALK = Path("uxsuite/walks/first-visit.json")
SESSIONS = "## Sessions that stay small"
STAGES = "## The six stages"
BEFORE = "## Working with the product owner"
OLD_TOOL = re.compile(r"`crissp/tool`,(\s+)registered(\s+)in `\.mcp\.json`")


@dataclass
class Repair:
    key: str
    what: str
    do: Callable[[], None]
    moves: list = field(default_factory=list)


def read(path: Path) -> dict | None:
    """A JSON object from the file; None when it is missing, broken or not an object (then it is not repaired)."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def is_engine(root: Path) -> bool:
    """The framework's own repository: its crissp/ is the engine, whose uxsuite holds code by design."""
    return (root / "crissp").resolve() == ENGINE.resolve()


def stack_url(root: Path) -> str:
    compose = (read(root / "crissp/deploy/deploy.json") or {}).get("compose") or {}
    port = (compose.get("port") or {}).get("default", 8080)
    return str(compose.get("url", "http://127.0.0.1:{port}")).replace("{port}", str(port))


def fix_steps(root: Path) -> Repair | None:
    data = read(root / SUITES)
    steps = data.get("steps", []) if data is not None else None
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        return None
    if steps and not ({s.get("key") for s in steps} <= OLD_KEYS and not (root / "src").exists()):
        return None
    template = read(TEMPLATE / SUITES)

    def do() -> None:
        own = [{**r, "steps": [RENAMED.get(k, k) for k in r.get("steps", [])]}
               for r in data.get("paths", []) if r.get("match") not in OLD_PATHS]
        shared = data.get("shared", [])
        data["steps"] = template["steps"]
        data["paths"] = template["paths"] + own
        data["shared"] = shared + [r for r in template["shared"] if r["match"] not in {s.get("match") for s in shared}]
        write(root / SUITES, data)

    why = "no steps" if not steps else "the old template's steps on src/, which is not there"
    return Repair("steps", f"{SUITES}: {why} → the default parts' steps (app/backend, app/frontend)", do)


def fix_ux_url(root: Path) -> Repair | None:
    team = read(root / TEAM)
    if team is None or team.get("url") != OLD_URL or list((root / "app/frontend").glob("vite.config.*")):
        return None
    url = stack_url(root)

    def do() -> None:
        team["url"] = url
        write(root / TEAM, team)

    return Repair("ux-url", f"{TEAM}: {OLD_URL} → {url}, the local stack (app/frontend has no Vite dev server)", do)


def extras(root: Path) -> list[Path]:
    ux = root / "crissp/uxsuite"
    if is_engine(root) or not ux.is_dir():
        return []
    return sorted(p for p in ux.iterdir() if p.name not in UX_CONFIG)


def fix_ux_extra(root: Path) -> Repair | None:
    moves = [p for p in extras(root) if not (root / "docs/ux" / p.name).exists()]
    if not moves:
        return None

    def do() -> None:
        (root / "docs/ux").mkdir(parents=True, exist_ok=True)
        for p in moves:
            shutil.move(str(p), str(root / "docs/ux" / p.name))

    said = ", ".join(f"{p.relative_to(root)} → docs/ux/{p.name}" for p in moves)
    return Repair("ux-extra", f"not the UX suite's configuration: {said} (the product lives in app/; a design is "
                              "crissp ux --propose)", do, moves)


def fix_agreement(root: Path) -> Repair | None:
    path = root / "crissp/CLAUDE.md"
    text = path.read_text() if path.is_file() else ""
    if (root / "crissp/tool").is_dir() or not OLD_TOOL.search(text):
        return None

    def do() -> None:
        path.write_text(OLD_TOOL.sub(r"the crissp MCP server,\1registered\2in `.mcp.json`", text))

    return Repair("agreement", "crissp/CLAUDE.md: the tools come from `crissp/tool`, which is not here → the crissp MCP "
                               "server in .mcp.json", do)


def brought_in(root: Path) -> bool:
    """A project of its own with a crissp/ folder (the framework's repository keeps its engine there by design)."""
    return (root / "crissp").is_dir() and not is_engine(root)


def fix_missing(root: Path) -> Repair | None:
    if not brought_in(root):
        return None
    walks = list((root / "crissp/uxsuite/walks").glob("*.json"))
    values = {"PRODUCT": (read(root / SUITES) or {}).get("product") or root.name, "OWNER": "the product owner",
              "DATE": datetime.date.today().isoformat()}
    missing = [(src, rel) for src in sorted((TEMPLATE / "crissp").rglob("*"))
               if src.is_file() and not SKIP & set(src.parts)
               for rel in [src.relative_to(TEMPLATE / "crissp")]
               if not (root / "crissp" / rel).exists() and not (rel == FIRST_WALK and walks)]
    if not missing:
        return None

    def do() -> None:
        for src, rel in missing:
            text = src.read_text()
            for key, value in values.items():
                text = text.replace("{{" + key + "}}", value)
            (root / "crissp" / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / "crissp" / rel).write_text(text)

    said = ", ".join(f"crissp/{rel}" for _, rel in missing)
    return Repair("missing", f"not there: {said} → made from the template (as crissp init does)", do)


def fix_crissp_md(root: Path) -> Repair | None:
    if not brought_in(root):
        return None
    target, framework = root / "crissp/CRISSP.md", (ENGINE / "CRISSP.md").read_text()
    if target.is_file() and target.read_text() == framework:
        return None
    return Repair("crissp-md", "crissp/CRISSP.md is not this crissp's framework text → this crissp's",
                  lambda: target.write_text(framework))


def span(text: str, heading: str) -> tuple[int, int] | None:
    """Where the section under heading lies: from its heading up to the next one (or the end); None when absent."""
    m = re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE)
    if not m:
        return None
    nxt = re.search(r"^## ", text[m.end():], re.MULTILINE)
    return m.start(), m.end() + nxt.start() if nxt else len(text)


def section(text: str, heading: str) -> str:
    """The section under heading, ending in one blank line; '' when it is not there."""
    where = span(text, heading)
    return text[where[0]:where[1]].rstrip("\n") + "\n\n" if where else ""


def fix_section(root: Path, key: str, heading: str, before: tuple[str, ...]) -> Repair | None:
    """A section of the agreement that is crissp's own: this crissp's text, in place of an old one, or added before the
    first of the headings in before that is there (else at the end)."""
    path = root / "crissp/CLAUDE.md"
    if not brought_in(root) or not path.is_file():
        return None
    ours = section((TEMPLATE / "crissp/CLAUDE.md").read_text(), heading)
    have = section(path.read_text(), heading)
    if have == ours:
        return None

    def do() -> None:
        text = path.read_text()  # read again: the agreement repair may have changed it first
        old = span(text, heading)
        where = old or next((w for h in before if (w := span(text, h))), None)
        if where:
            end = where[1] if old else where[0]
            text = text[:where[0]] + ours + text[end:]
        else:
            text = text.rstrip("\n") + "\n\n" + ours
        path.write_text(text)

    return Repair(key, f'crissp/CLAUDE.md: "{heading[3:]}" is {"old" if have else "missing"} → this crissp\'s', do)


def fix_sessions(root: Path) -> Repair | None:
    """F-21: the agreement's sessions section is crissp's."""
    return fix_section(root, "sessions", SESSIONS, (BEFORE,))


def fix_stages(root: Path) -> Repair | None:
    """F-130: the agreement's six stages are crissp's: what a session says and offers on a <!-- CRISSP --> prompt."""
    return fix_section(root, "stages", STAGES, (SESSIONS, BEFORE))


def fix_gitignore(root: Path) -> Repair | None:
    if not brought_in(root):
        return None
    path = root / ".gitignore"
    have = set(path.read_text().splitlines()) if path.is_file() else set()
    rules = [x for x in (TEMPLATE / "gitignore.crissp").read_text().splitlines() if x and not x.startswith("#")]
    missing = [x for x in rules if x not in have]
    if not missing:
        return None

    def do() -> None:
        text = path.read_text() if path.is_file() else ""
        path.write_text(text + ("\n" if text and not text.endswith("\n") else "")
                        + "# --- C.R.I.S.S.P.: added by crissp repair\n" + "\n".join(missing) + "\n")

    return Repair("gitignore", f".gitignore lacks {len(missing)} of the framework's rules ({', '.join(missing[:3])}"
                               f"{' …' if len(missing) > 3 else ''}) → added", do)


def fix_changes(root: Path) -> Repair | None:
    """F-20: the dashboard reads a change's source as {file, symbol}; a plain path becomes the file from the top."""
    path = root / CHANGES
    data = read(path)
    entries = data.get("changes") if data else None
    if not isinstance(entries, list):
        return None
    plain = sum(isinstance(src, str) for c in entries if isinstance(c, dict) for src in c.get("sources", []))
    if not plain:
        return None

    def do() -> None:
        for c in entries:
            if isinstance(c, dict):
                c["sources"] = [{"file": src, "symbol": ""} if isinstance(src, str) else src for src in c.get("sources", [])]
        write(path, data)
    return Repair("changes", f"{CHANGES}: {plain} sources are plain paths → {{file, symbol}} (the file from the top; "
                             "name a symbol to show the fix itself)", do)


def fix_pin(root: Path, version: str | None) -> Repair | None:
    """F-20: .mcp.json pins crissp for its MCP tools; the crissp that repairs moves the pin to itself."""
    path = root / ".mcp.json"
    data = read(path)
    server = ((data or {}).get("mcpServers") or {}).get("crissp")
    args = server.get("args") if isinstance(server, dict) else None
    pins = [i for i, a in enumerate(args or []) if isinstance(a, str) and a.startswith("crissp==")]
    if not version or not pins or args[pins[0]] == f"crissp=={version}":
        return None
    old = args[pins[0]]

    def do() -> None:
        args[pins[0]] = f"crissp=={version}"
        write(path, data)
    return Repair("mcp-pin", f".mcp.json: {old} → crissp=={version}, the crissp that repairs (its MCP tools)", do)


def fix_vibe_pin(root: Path, version: str | None) -> Repair | None:
    """F-27: .vibe/config.toml pins crissp like .mcp.json; the crissp that repairs moves that pin to itself too. Only
    the pin's text changes (comments and other servers stay); an unknown or ambiguous config is left as it is."""
    path = root / ".vibe" / "config.toml"
    try:
        text = path.read_text() if path.is_file() else ""
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    servers = data.get("mcp_servers")
    args = next((s.get("args") for s in servers if isinstance(s, dict) and s.get("name") == "crissp"),
                None) if isinstance(servers, list) else None
    pins = [a for a in args if isinstance(a, str) and a.startswith("crissp==")] if isinstance(args, list) else []
    if not version or not pins or pins[0] == f"crissp=={version}" or text.count(json.dumps(pins[0])) != 1:
        return None
    old, new = pins[0], f"crissp=={version}"

    def do() -> None:
        path.write_text(text.replace(json.dumps(old), json.dumps(new)))
    return Repair("vibe-pin", f".vibe/config.toml: {old} → {new}, the same pin as .mcp.json (Vibe's MCP tools)", do)


def only_crissp(text: str) -> bool:
    """F-100: a .vibe/config.toml that holds nothing but the crissp server, as crissp wrote it: safe to write anew.
    Asked only of a config vibe.pinned could read."""
    data = tomllib.loads(text)
    servers = data.get("mcp_servers")
    return set(data) == {"mcp_servers"} and isinstance(servers, list) and len(servers) == 1 \
        and isinstance(servers[0], dict) and servers[0].get("name") == "crissp"


def fix_vibe(root: Path, version: str | None, home: Path | None) -> Repair | None:
    """F-24: Vibe onboarding for a project brought in before it: .vibe/config.toml with the MCP pin, and the folder
    trusted when Vibe is installed (home None or not a folder: only the config). F-100: a config that does not name
    this folder (cwd and CRISSP_ROOT: Vibe's desktop app needs both) is written anew when it holds only crissp's
    server; the framework's own checkout gets one that starts its own server."""
    engine = is_engine(root) and (root / "crissp" / "tool" / "server.py").is_file()
    if not (engine or (brought_in(root) and version)):
        return None
    config = root / ".vibe" / "config.toml"
    db = home / vibe.FILE if home is not None and home.is_dir() else None
    trusted = db is None or vibe.state(home, root) != "absent"  # F-26: untrusted or unknown: left as it is
    text = config.read_text() if config.is_file() else None
    stale = text is not None and not vibe.pinned(text, root) and only_crissp(text)
    if (text is not None and not stale) and trusted:
        return None
    command, args = vibe.server(root, version, engine)
    parts = []
    if text is None:
        parts.append(f".vibe/config.toml is not there → {Path(command).name} {' '.join(args[-2:])}, started in this "
                     "folder (the server .mcp.json registers for Claude Code)")
    elif stale:
        parts.append(".vibe/config.toml does not name this folder (cwd, CRISSP_ROOT): Vibe's desktop app starts the "
                     "server elsewhere and gets no crissp tools → written anew for this folder")
    if not trusted:
        parts.append(f"not trusted in {db} → added (never removed)")

    def do() -> None:
        if text is None or stale:
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(vibe.config(root, command, args))
        if not trusted:
            vibe.trust(home, root)

    return Repair("vibe", "; ".join(parts), do)


def vibe_needs(root: Path) -> list[str]:
    """F-100: what only a person can do for Vibe: a config with servers of its own that does not name this folder,
    and a config still in git (it names one machine's folder now)."""
    config = root / ".vibe" / "config.toml"
    if not (brought_in(root) or is_engine(root)) or not config.is_file():
        return []
    out = []
    text = config.read_text()
    if not vibe.pinned(text, root) and not only_crissp(text):
        out.append(f".vibe/config.toml has servers of its own: give the crissp server cwd = \"{root}\" and "
                   f"[mcp_servers.env] CRISSP_ROOT = \"{root}\" by hand, so Vibe's desktop app finds it")
    try:
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", ".vibe/config.toml"],
                                 capture_output=True, check=False).returncode == 0
    except OSError:  # no git at all
        tracked = False
    if tracked:
        out.append("`.vibe/config.toml` is in git, but it names this machine's folder now: git rm --cached "
                   ".vibe/config.toml and commit (each clone's crissp repair --yes writes its own)")
    return out


def fix_hook(root: Path) -> Repair | None:
    """F-50: .githooks/pre-commit (the template's) and core.hooksPath on it, so git lints before every commit. The
    framework's own checkout commits its hook: there it is only turned on. Hooks of the project's own: needs()."""
    if not (brought_in(root) or is_engine(root)):
        return None
    path = root / hook.HOOKS / "pre-commit"
    make = not is_engine(root) and not path.exists()
    on = hook.state(root) == "off"
    if not make and not on:
        return None
    parts = [f"{hook.HOOKS}/pre-commit is not there → from the template (the lint steps before every commit)"] * make
    parts += [f"core.hooksPath is not set → {hook.HOOKS} (git runs the lint before every commit)"] * on

    def do() -> None:
        if make:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TEMPLATE / "githooks" / "pre-commit", path)
            path.chmod(0o755)
        if on:
            hook.turn_on(root)

    return Repair("git-hook", "; ".join(parts), do)


def find(root: Path, version: str | None = None, home: Path | None = None) -> list[Repair]:
    """What is out of place, in the order it is put in place."""
    return [r for r in (fix_steps(root), fix_ux_url(root), fix_ux_extra(root), fix_agreement(root), fix_sessions(root), fix_stages(root),
                        fix_missing(root),
                        fix_crissp_md(root), fix_gitignore(root), fix_changes(root), fix_pin(root, version),
                        fix_vibe_pin(root, version), fix_vibe(root, version, home), fix_hook(root)) if r]


def committed(root: Path) -> bool:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"],
                              capture_output=True, check=False).returncode == 0
    except OSError:  # no git at all
        return False


def needs(root: Path) -> list[str]:
    """What a person has to do: said, never done."""
    out = [f"docs/ux/{p.name} is already there: {p.relative_to(root)} stays; move it by hand"
           for p in extras(root) if (root / "docs/ux" / p.name).exists()]
    if not (root / "crissp").is_dir():
        out.append("not brought in: no crissp/ here; crissp init brings it in")
    if hook.needs(root):
        out.append(hook.needs(root))
    out += vibe_needs(root)
    if not committed(root):
        out.append("no commit yet: the checks test what is committed; review the diff and commit")
    if not is_engine(root) and not (root / "docker-compose.yml").exists():
        out.append("no docker-compose.yml: nothing runs for the UX suite to walk; build app/backend, app/frontend and "
                   "the stack first (not a prototype in crissp/uxsuite/)")
    return out


def main(argv: list[str], env: dict) -> int:
    if argv not in ([], ["--yes"]):
        print("usage: crissp repair [--yes]")
        return 2
    root = Path(env.get("CRISSP_ROOT") or os.getcwd()).resolve()
    fixes, yes = find(root, env.get("CRISSP_VERSION"), vibe.home(env)), argv == ["--yes"]
    print(f"crissp repair: {len(fixes)} out of place." if fixes else "crissp repair: nothing out of place.")
    for r in fixes:
        print(f"  {r.key:<10} {r.what}")
        if yes:
            r.do()
    left = needs(root)
    if left:
        print("Needs you:")
        for line in left:
            print(f"  - {line}")
    if fixes and yes:
        print(f"Repaired {len(fixes)}. Review the diff and commit when you are happy.")
    elif fixes:
        print("crissp repair --yes puts them in place. Nothing is committed.")
    return 0 if yes or not (fixes or left) else 1


if __name__ == "__main__":  # pragma: no cover — run by the crissp command (crissp repair); main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
