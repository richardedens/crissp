"""The crissp command: one door to the framework for the project in the current directory.

    crissp init [--product NAME] [--owner NAME] [--yes] [--no-git] [--no-deploy]
                              bring this folder in: git init when it is no repository yet, then the agreement, the
                              backlog, the configuration and the deploy template; never overwrites, never commits
    crissp check [--plan]     test what changed since the last green state (crissp/check.sh)
    crissp check-all          the full run (crissp/check-all.sh)
    crissp deploy [...]       behind the release gate (crissp/deploy.sh: --plan, --cluster, --cluster-plan)
    crissp dashboard          the Tests dashboard and the UX suite on one local server (crissp/test.sh --dashboard)
    crissp ux [...]           the UX suite (crissp/ux.sh: --list, --status, --shoot, --round, --propose)
    crissp mcp                the crissp MCP server on stdin/stdout (.mcp.json starts it)
    crissp --version

The engine (the guards, the tool, the suites, the look and the templates) is part of this package; a project keeps only
its own data. The project is --root, CRISSP_ROOT, or the nearest folder upwards with crissp/testsuite/suites.json
(else the current directory)."""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from crissp import __version__

HERE = Path(__file__).resolve().parent
# Installed: the engine is package data next to this file. In this repository's checkout: its crissp/ folder.
ENGINE = HERE / "engine" if (HERE / "engine").is_dir() else HERE.parents[1] / "crissp"
TEMPLATE = ENGINE / "template"
DEPLOY_TEMPLATE = ("helm", "terraform", "deploy.json", ".env.production.example", "README.md")
SCRIPTS = {"check": "check.sh", "check-all": "check-all.sh", "deploy": "deploy.sh", "ux": "ux.sh"}
SKIP = {"__pycache__", ".DS_Store", "results"}


def find_root(start: Path, env: dict) -> Path:
    """The project: CRISSP_ROOT, else the nearest folder upwards that holds crissp/testsuite/suites.json, else start."""
    if env.get("CRISSP_ROOT"):
        return Path(env["CRISSP_ROOT"]).resolve()
    for folder in (start, *start.parents):
        if (folder / "crissp" / "testsuite" / "suites.json").is_file():
            return folder
    return start


def fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def plan_init(root: Path, values: dict, deploy: bool) -> list[tuple[Path, Path, bool]]:
    """What init would write: (source, target, fill placeholders), for every target that does not exist yet."""
    files: list[tuple[Path, Path, bool]] = []

    def tree(src: Path, dst: Path, placeholders: bool = True) -> None:
        for path in sorted(src.rglob("*")):
            if path.is_file() and not SKIP & set(path.relative_to(src).parts):
                files.append((path, dst / path.relative_to(src), placeholders))

    for name in ("CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "VERSION"):
        files.append((TEMPLATE / name, root / name, True))
    files.append((TEMPLATE / "mcp.json", root / ".mcp.json", True))
    tree(TEMPLATE / "crissp", root / "crissp")
    files.append((ENGINE / "CRISSP.md", root / "crissp" / "CRISSP.md", False))
    if deploy:
        for name in DEPLOY_TEMPLATE:
            src = ENGINE / "deploy" / name
            if src.is_dir():
                tree(src, root / "crissp" / "deploy" / name, placeholders=False)
            else:
                files.append((src, root / "crissp" / "deploy" / name, False))
    return files


def merge_ignore(target: Path, rules: str) -> bool:
    """Add the framework's ignore rules a .gitignore lacks (never replacing what is there); True when it changed."""
    have = target.read_text().splitlines() if target.is_file() else []
    missing = [line for line in rules.splitlines() if line and line not in have]
    if not missing:
        return False
    text = "\n".join(have)
    text = (text + "\n\n" if text.strip() else "") + "\n".join(missing) + "\n"
    target.write_text(text)
    return True


def init(root: Path, args, out=sys.stdout, ask=input) -> int:
    values = {"PRODUCT": args.product or root.name, "OWNER": args.owner or "the product owner",
              "REPOSITORY": root.name, "DATE": datetime.date.today().isoformat(), "VERSION": "0.1.0",
              "CRISSP_VERSION": __version__}
    if not args.yes and ask(f"Bring {root} in as {values['PRODUCT']} (C.R.I.S.S.P. {__version__})? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.", file=out)
        return 1
    if not args.no_git and not (root / ".git").exists():
        if not shutil.which("git"):
            print("git is not installed: install it, or pass --no-git.", file=out)
            return 2
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        print(f"git init: {root}", file=out)
    made, kept = [], []
    for src, dst, placeholders in plan_init(root, values, deploy=not args.no_deploy):
        rel = dst.relative_to(root)
        if dst.exists():
            kept.append(str(rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if placeholders:
            dst.write_text(fill(src.read_text(), values))
        else:
            shutil.copyfile(src, dst)
        shutil.copymode(src, dst)
        made.append(str(rel))
    if merge_ignore(root / ".gitignore", (TEMPLATE / "gitignore.crissp").read_text()):
        made.append(".gitignore (rules added)")
    print(f"C.R.I.S.S.P. {__version__} for {values['PRODUCT']}: {len(made)} made, {len(kept)} kept as they were.", file=out)
    for rel in made:
        print(f"  made  {rel}", file=out)
    for rel in kept:
        print(f"  kept  {rel}", file=out)
    print("\nNext: fill in the <!-- CRISSP: … --> blocks (Claude does this with you), name the product's parts in\n"
          "crissp/testsuite/suites.json, review the diff, and commit when you are happy. Nothing was committed.", file=out)
    return 0


def engine_env(root: Path, env: dict) -> dict:
    """The environment the engine's scripts run in: the project, and this Python first on PATH (they call python3)."""
    return {**env, "CRISSP_ROOT": str(root), "PATH": os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")])}


def run_script(root: Path, name: str, argv: list[str], env: dict) -> int:
    return subprocess.run(["bash", str(ENGINE / name), *argv], cwd=root, env=engine_env(root, env)).returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crissp", description="C.R.I.S.S.P. for the project in this folder.")
    p.add_argument("--version", action="version", version=f"crissp {__version__}")
    p.add_argument("--root", help="the project (default: CRISSP_ROOT or the nearest crissp project upwards)")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("init", help="bring this folder in (git init, agreement, backlog, configuration, deploy template)")
    i.add_argument("--product", help="the product's name (default: the folder's name)")
    i.add_argument("--owner", help="the product owner's name")
    i.add_argument("--yes", action="store_true", help="do not ask")
    i.add_argument("--no-git", action="store_true", help="do not run git init")
    i.add_argument("--no-deploy", action="store_true", help="leave out the Helm chart and Terraform")
    for name, help_ in (("check", "test what changed (--plan)"), ("check-all", "the full run"),
                        ("deploy", "deploy behind the release gate (--plan, --cluster, --cluster-plan)"),
                        ("ux", "the UX suite (--list, --status, --shoot, --round, --propose)")):
        sub.add_parser(name, help=help_, add_help=False)  # its options belong to the guard: passed on untouched
    sub.add_parser("dashboard", help="the Tests dashboard and the UX suite on 127.0.0.1")
    sub.add_parser("mcp", help="the crissp MCP server on stdin/stdout")
    return p


def split(argv: list[str]) -> tuple[list[str], list[str]]:
    """crissp's own part of the command line (up to a guard's name) and the guard's part (after it, untouched)."""
    i = 0
    while i < len(argv):
        if argv[i] == "--root":
            i += 2
            continue
        if argv[i] in SCRIPTS:
            return argv[:i + 1], argv[i + 1:]
        i += 1
    return argv, []


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    env = dict(os.environ if env is None else env)
    own, passed = split(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(own)
    if args.command == "init":
        return init(Path(args.root or os.getcwd()).resolve(), args)
    root = Path(args.root).resolve() if args.root else find_root(Path(os.getcwd()).resolve(), env)
    if args.command == "dashboard":
        return run_script(root, "test.sh", ["--dashboard"], env)
    if args.command == "mcp":
        return subprocess.run([sys.executable, "-I", str(ENGINE / "tool" / "server.py")], cwd=root,
                              env=engine_env(root, env)).returncode
    return run_script(root, SCRIPTS[args.command], passed, env)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
