"""What deploy.sh rebuilds locally, and whether it may go at all: the decisions, kept out of the shell so they can be
tested. The product's Docker Compose stack is described in crissp/deploy/deploy.json (`compose`): the compose file, its
services and the paths that go into each one's image, the address and the health paths. A deploy is:
1. the release gate (release.py check): a green full run, at most 7 days old, of exactly this commit. No bypass.
2. the release notes (impact.py release-notes): VERSION is a version and CHANGELOG.md's top section is about it.
3. rebuild only what changed since the last deployed commit (crissp/testsuite/results/deploy.json): one service at a
   time with `docker compose up -d --build --no-deps <service>`, so a rebuild never recreates another as a dependency.
   Without a compose file there is nothing to deploy locally, and the plan says so.
4. health checks (deploy.sh), then the deployed commit and version are recorded here.

    python3 crissp/testsuite/lib/deploy_plan.py plan [--format text|shell]
        the plan: read-only (it reads the settings, the certificate, the release notes and git)
    python3 crissp/testsuite/lib/deploy_plan.py record <service…>
        after a healthy deploy: remember this commit and version as deployed (and what was rebuilt)
"""

import fnmatch
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CRISSP_ROOT") or os.getcwd()).resolve()  # the project; never this file's place
LIB = Path(__file__).resolve().parent
DEPLOYED = ROOT / "crissp" / "testsuite" / "results" / "deploy.json"
SETTINGS = Path("crissp") / "deploy" / "deploy.json"  # relative to the repository


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"deploy_{name}", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str, root: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _settings(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def load_compose(path: Path) -> dict:
    """The `compose` section of deploy.json; {} when there is none (no local stack)."""
    return _settings(path).get("compose", {}) or {}


def services(compose: dict) -> list[str]:
    return list(compose.get("services", {}))


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
    return path == pattern


def touches(compose: dict, service: str, path: str) -> bool:
    s = compose["services"][service]
    if any(_matches(path, p) for p in s.get("exclude", [])):
        return False
    return any(_matches(path, p) for p in s.get("inputs", []))


def rebuilds(compose: dict, changed: list[str] | None, why_all: str = "") -> dict[str, list[str]]:
    """service → why it is rebuilt (the changed files that go into it). `changed` None: everything (`why_all` says why)."""
    if changed is None:
        return {s: [why_all] for s in services(compose)}
    out: dict[str, list[str]] = {}
    for s in services(compose):
        files = [f for f in changed if touches(compose, s, f)]
        if files:
            out[s] = files
    return out


def port(compose: dict, root: Path, environ: dict[str, str]) -> str:
    """The local port: the setting from the environment, else from .env (only that key is read), else the default."""
    p = compose.get("port", {})
    key = p.get("setting")
    if key and environ.get(key):
        return environ[key]
    if key and (root / ".env").is_file():
        for line in (root / ".env").read_text().splitlines():
            k, _, v = line.strip().removeprefix("export ").partition("=")
            if k.strip() == key and v.strip():
                return v.strip().strip("\"'")
    return str(p.get("default", ""))


def plan(*, gate: list[str], notes: list[str], deployed: dict | None, changed: list[str] | None, head: str, version: str,
         compose: dict, product: str, port: str, has_file: bool, why_all: str = "") -> dict:
    """The whole decision. `deployed`: the last record or None; `changed`: the files changed since its commit, or None
    when every service is rebuilt (`why_all` says why); `has_file`: the compose file exists."""
    rebuild = rebuilds(compose, changed, why_all) if has_file else {}
    url = compose.get("url", "").replace("{port}", port)
    return {"version": version, "commit": head, "deployed": deployed, "product": product, "compose": has_file,
            "file": compose.get("file", ""),
            "stops": [f"Release gate: {r}" for r in gate] + [f"Release notes: {r}" for r in notes],
            "rebuild": rebuild, "services": [s for s in services(compose) if s in rebuild],
            "all": services(compose), "health": [url + h for h in compose.get("health", [])] if url else []}


def _short(commit: str) -> str:
    return commit[:8] if len(commit) == 40 else commit  # a hash, or a text such as "(no commit yet)"


def render_text(p: dict) -> str:
    d = p["deployed"]
    rows = [f"Deploy {p['product']} {p['version']} (commit {_short(p['commit'])})",
            f"  Last deployed: {d['version']} (commit {d['commit'][:8]})" if d else "  Last deployed: nothing recorded yet"]
    if not p["compose"]:
        where = f"({p['file']})" if p["file"] else "(deploy.json names none)"
        rows.append(f"  No compose file {where}: nothing to deploy locally. A cluster deploy: crissp/deploy.sh --cluster "
                    "(crissp/deploy.sh --cluster-plan shows it).")
        return "\n".join(rows)
    if p["stops"]:
        rows.append("  Stops, nothing is rebuilt:")
        rows += [f"    - {s}" for s in p["stops"]]
    if not p["rebuild"]:
        rows.append(f"  Nothing to rebuild: no file that goes into {', '.join(p['all'])} changed.")
    for c, why in p["rebuild"].items():
        rows.append(f"  Rebuild {c} (docker compose up -d --build --no-deps {c}), because: " + ", ".join(why[:6])
                    + (" …" if len(why) > 6 else ""))
    rows.append(f"  Then: health checks ({', '.join(p['health']) or 'none configured'}), and record this commit and "
                "version as deployed.")
    return "\n".join(rows)


def render_shell(p: dict) -> str:
    return "\n".join([f"PLAN_STOPS={len(p['stops'])}", f"PLAN_COMPOSE={1 if p['compose'] else 0}",
                      f"PLAN_FILE={shlex.quote(p['file'])}", f"PLAN_SERVICES={shlex.quote(' '.join(p['services']))}",
                      f"PLAN_VERSION={shlex.quote(p['version'])}", f"PLAN_COMMIT={shlex.quote(p['commit'])}",
                      f"PLAN_PRODUCT={shlex.quote(p['product'])}", f"PLAN_HEALTH={shlex.quote(' '.join(p['health']))}"])


def since_deployed(deployed: dict | None, root: Path = ROOT) -> tuple[list[str] | None, str]:
    """(files changed since the deployed commit, or None for everything; why everything)."""
    if not deployed:
        return None, "no deploy recorded yet (crissp/testsuite/results/deploy.json)"
    try:
        return [f for f in _git("diff", "--name-only", f"{deployed['commit']}..HEAD", root=root).splitlines() if f], ""
    except subprocess.CalledProcessError:
        return None, f"the deployed commit {deployed['commit'][:8]} is not in this checkout"


def collect(root: Path = ROOT, deployed_path: Path = DEPLOYED) -> dict:
    settings = _settings(root / SETTINGS)
    compose = settings.get("compose", {}) or {}
    deployed = json.loads(deployed_path.read_text()) if deployed_path.is_file() else None
    changed, why_all = since_deployed(deployed, root)
    try:
        version = (root / "VERSION").read_text().strip()
    except OSError:
        version = "(no VERSION)"
    try:
        head = _git("rev-parse", "--verify", "HEAD", root=root).strip()
    except subprocess.CalledProcessError:
        head = "(no commit yet)"
    has_file = bool(compose.get("file")) and (root / compose["file"]).is_file()
    return plan(gate=_load("release").check(root, root / "crissp" / "testsuite" / "results"),
                notes=_load("impact").check_release_notes(root), deployed=deployed, changed=changed, head=head,
                version=version, compose=compose, product=settings.get("product", "the product"),
                port=port(compose, root, dict(os.environ)), has_file=has_file, why_all=why_all)


def record(components: list[str], root: Path = ROOT, deployed_path: Path = DEPLOYED) -> dict:
    last = json.loads(deployed_path.read_text()) if deployed_path.is_file() else {}
    entry = {"commit": _git("rev-parse", "HEAD", root=root).strip(), "version": (root / "VERSION").read_text().strip(),
             "at": time.time(), "rebuilt": components}
    history = (last.get("history", []) + [{k: last[k] for k in ("commit", "version", "at", "rebuilt")}])[-20:] if last else []
    deployed_path.parent.mkdir(parents=True, exist_ok=True)
    deployed_path.write_text(json.dumps({**entry, "history": history}, indent=2))
    return entry


def _option(argv: list[str], name: str, default: str) -> str:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "plan":
        p = collect()
        print(render_shell(p) if _option(argv, "--format", "text") == "shell" else render_text(p))
        return 0
    if cmd == "record":
        settings = _settings(ROOT / SETTINGS)
        known = services(settings.get("compose", {}) or {})
        unknown = [c for c in argv[2:] if c not in known]
        if unknown:
            print(f"record: unknown service {', '.join(unknown)} (known: {', '.join(known)})", file=sys.stderr)
            return 2
        entry = record(argv[2:])
        print(f"Deployed: {settings.get('product', 'the product')} {entry['version']} (commit {entry['commit'][:8]})")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
