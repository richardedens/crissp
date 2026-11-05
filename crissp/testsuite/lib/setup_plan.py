"""What a run needs installed, and installing only what is missing or out of date (crissp/testsuite/setup.sh runs it).

Safe to run before every run: when everything is in place it costs a few file reads and prints nothing. It prints what
it changed; when something cannot be installed it says how to fix it and exits non-zero. What a project needs is in its
crissp/testsuite/suites.json (setup, lib/project.py):

- uv               runs the pinned test tools (crissp/testsuite/requirements.txt); never installed from here: the
                   command is printed
- Python 3.12+     the interpreter that runs this (CRISSP_PYTHON for the venvs, default this one)
- setup.venvs      a part's own Python environment, <dir>/.venv from <dir>/requirements-dev.txt. A venv is
                     missing  no .venv/bin/python
                     broken   its python points at an interpreter that is gone (Python was upgraded or removed)
                     moved    its scripts start with another folder's path (the repository was moved or copied)
                     stale    its requirements changed since it was installed (a stamp in .venv holds a hash of every
                              requirements file it was installed from, following -r)
                   a missing, broken or moved venv is made anew; a stale one gets pip install -r again
- setup.npm        a part's node_modules: missing, or stale when package-lock.json is newer than npm's own record of
                   what it installed (node_modules/.package-lock.json): then npm ci
- setup.needs      commands the steps need ({command, hint}): never installed from here; the hint says how

    python3 crissp/testsuite/lib/setup_plan.py plan     one line per thing to do ("venv <dir> <state>", "npm <dir> <state>",
                                                        "need <command> <hint>", "python too-old <version>", "uv missing")
    python3 crissp/testsuite/lib/setup_plan.py apply    do it (setup.sh)
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402

STAMP = ".testsuite-installed"
MIN_PYTHON = (3, 12)
BREW_UV = Path("/opt/homebrew/bin/uv")


def requirement_files(path: Path, seen: set[Path] | None = None) -> list[Path]:
    """This requirements file and every file it includes with -r (relative to the file that names it)."""
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen or not path.is_file():
        return []
    seen.add(path)
    out = [path]
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith(("-r ", "--requirement ")):
            out += requirement_files(path.parent / line.split(None, 1)[1].strip(), seen)
    return out


def fingerprint(app: Path, root: Path) -> str:
    digest = hashlib.sha256()
    for f in requirement_files(app / "requirements-dev.txt"):
        digest.update(str(f.relative_to(root) if f.is_relative_to(root) else f).encode() + b"\0" + f.read_bytes() + b"\0")
    return digest.hexdigest()


def venv_state(app: Path, root: Path) -> str:
    venv = app / ".venv"
    python = venv / "bin" / "python"
    if not python.is_symlink() and not python.exists():
        return "missing"
    if not python.exists():  # a symlink to an interpreter that is gone
        return "broken"
    for script in ("pip", "pytest", "ruff"):
        path = venv / "bin" / script
        if path.is_file():
            first = path.read_bytes().split(b"\n", 1)[0].decode(errors="replace")
            if first.startswith("#!") and not first[2:].strip().startswith(str(venv)):
                return "moved"
    stamp = venv / STAMP
    if not stamp.is_file() or stamp.read_text().strip() != fingerprint(app, root):
        return "stale"
    return "ok"


def npm_state(frontend: Path) -> str:
    record = frontend / "node_modules" / ".package-lock.json"
    if not record.is_file():
        return "missing"
    if (frontend / "package-lock.json").stat().st_mtime > record.stat().st_mtime:
        return "stale"
    return "ok"


def uv_path(which=shutil.which, brew: Path = BREW_UV) -> str | None:
    return which("uv") or (str(brew) if brew.is_file() else None)


def plan(root: Path, conf: dict, version: tuple = tuple(sys.version_info[:2]), which=shutil.which,
         brew: Path = BREW_UV) -> list[str]:
    """What to do, one line each; empty: everything is in place."""
    out = []
    if version < MIN_PYTHON:
        out.append(f"python too-old {'.'.join(map(str, version))}")
    if uv_path(which, brew) is None:
        out.append("uv missing")
    for app in conf["setup"]["venvs"]:
        state = venv_state(root / app, root)
        if state != "ok":
            out.append(f"venv {app} {state}")
    for app in conf["setup"]["npm"]:
        state = npm_state(root / app)
        if state != "ok":
            out.append(f"npm {app} {state}")
    for need in conf["setup"]["needs"]:
        if which(need["command"]) is None:
            out.append(f"need {need['command']} {need['hint']}")
    return out


def stamp(app: Path, root: Path) -> None:
    (app / ".venv" / STAMP).write_text(fingerprint(app, root) + "\n")


def apply(root: Path, conf: dict, runner=subprocess.run, which=shutil.which, brew: Path = BREW_UV,
          version: tuple = tuple(sys.version_info[:2]), python: str | None = None, out=None, err=None) -> int:
    """Install what plan() says is missing; 0 when everything is in place now, 1 with how to fix it when not."""
    out, err = out or sys.stdout, err or sys.stderr
    python = python or os.environ.get("CRISSP_PYTHON") or sys.executable
    log = project.results(root) / "setup.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")

    def fail(why: str) -> int:
        print(f"setup: {why}", file=err)
        tail = log.read_text().splitlines()[-15:]
        if tail:
            print("----- last lines of crissp/testsuite/results/setup.log -----", *tail, sep="\n", file=err)
        return 1

    def sh(argv: list[str], cwd: Path) -> bool:
        with open(log, "a") as f:
            return runner(argv, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode == 0

    for line in plan(root, conf, version, which, brew):
        what, target, state = (line.split(" ", 2) + ["", ""])[:3]
        if what == "python":
            return fail(f"this is Python {state}; the testsuite needs {'.'.join(map(str, MIN_PYTHON))} or newer "
                        "(set CRISSP_PYTHON, or run it with a newer python3)")
        if what == "uv":
            return fail("uv is missing. Install it: brew install uv   (or: curl -LsSf https://astral.sh/uv/install.sh | sh)")
        if what == "need":
            return fail(f"{target} is missing: {state}")
        app = root / target
        if what == "venv":
            if state != "stale":
                shutil.rmtree(app / ".venv", ignore_errors=True)
                if not sh([python, "-m", "venv", str(app / ".venv")], app):
                    return fail(f"could not make {target}/.venv ({python} -m venv)")
            if not sh([str(app / ".venv" / "bin" / "python"), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                       "-r", "requirements-dev.txt"], app):
                return fail(f"could not install {target}/requirements-dev.txt (network? try: cd {target} && "
                            ".venv/bin/pip install -r requirements-dev.txt)")
            stamp(app, root)
            print(f"setup: {target}/.venv " + ("updated (its requirements changed)" if state == "stale" else f"made anew ({state})"),
                  file=out)
        else:  # npm
            if which("npm") is None:
                return fail("npm is missing. Install Node.js: brew install node")
            if not sh(["npm", "ci", "--no-audit", "--no-fund", "--loglevel=error"], app):
                return fail(f"npm ci failed in {target} (network? try: cd {target} && npm ci)")
            print(f"setup: {target}/node_modules installed (npm ci: {state})", file=out)
    return 0


def main(argv: list[str], root: Path | None = None) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("plan", "apply"):
        print(__doc__, file=sys.stderr)
        return 2
    root = root or project.root()
    try:
        conf = project.load(root)
    except project.ConfigError as e:
        print(f"setup: {e}", file=sys.stderr)
        return 1
    if cmd == "plan":
        for line in plan(root, conf):
            print(line)
        return 0
    return apply(root, conf)


if __name__ == "__main__":  # pragma: no cover — run by setup.sh; main() is tested
    sys.exit(main(sys.argv))
