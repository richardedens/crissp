"""crissp/testsuite/lint/python_lint.py: this repository's `python-lint` step (F-35, F-93). Dev-only: never in the package.

    py crissp/testsuite/lint/python_lint.py      (crissp/testsuite/suites.json; py: the pinned test tools, lib/steps.sh)

Run in crissp's own checkout (CRISSP_ROOT, else the current directory). Three checks, each finding named:
- ruff check over src/, crissp/ and site/, with the rules in pyproject.toml ([tool.ruff]; ruff pinned in
  crissp/testsuite/requirements.txt), and ruff format --check: the one layout (F-97)
- the engine runs on the Python standard library only: an AST scan of every import (one inside a function too) in the
  runtime code fails on anything that is not the standard library, the crissp package or one of the engine's own
  modules. Playwright, a pinned tool, is allowed in ux_shoot.py alone: it imports it in the function that re-runs under
  uv with it
- no duplicate code: pylint's duplicate-code check (R0801, pinned in requirements.txt next to this file, run with uv;
  its settings in pyproject.toml [tool.pylint]) over the same Python as ruff

Exit 0: clean. 1: findings, each printed. Without uv the duplicate-code check is a finding, never a silent pass.
"""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINTED = ("src", "crissp", "site")  # what ruff and pylint read
RUNTIME = ("src/crissp", "crissp/tool", "crissp/testsuite/lib", "crissp/uxsuite")  # standard library only
SKIP = {"__pycache__", "results", "tests", "package_tests", "pytest_plugin"}  # run with the pinned test tools
EXCLUDED = ("crissp/testsuite/sast/tests/",)  # unsafe code on purpose, as pyproject.toml's extend-exclude says
LAZY = {"crissp/uxsuite/ux_shoot.py": {"playwright"}}
RUFF = ("-m", "ruff", "check", "--no-cache", "--quiet")
FORMAT = ("-m", "ruff", "format", "--check", "--no-cache")  # prints "Would reformat: <file>"
PYLINT = ("pylint", "--rcfile=pyproject.toml")


def own_modules(root: Path) -> set[str]:
    """The names the engine imports from itself: the crissp package and the modules beside one another."""
    return {"crissp"} | {p.stem for d in RUNTIME[1:] for p in (root / d).glob("*.py")}


def runtime_files(root: Path) -> list[Path]:
    return sorted(p for d in RUNTIME for p in (root / d).rglob("*.py") if not SKIP & set(p.relative_to(root).parts))


def foreign_imports(root: Path) -> list[str]:
    """Imports outside the standard library, the crissp package and the engine's own modules."""
    own, out = own_modules(root), []
    for path in runtime_files(root):
        rel = path.relative_to(root).as_posix()
        allowed = own | LAZY.get(rel, set()) | set(sys.stdlib_module_names)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=rel)):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:  # a relative import: the engine's own modules
                continue
            out += [f"{rel}:{node.lineno}: imports {n}, not the standard library" for n in names if n not in allowed]
    return out


def python_files(root: Path) -> list[str]:
    """Every tracked Python file ruff reads, so pylint compares the same code."""
    done = subprocess.run(
        ["git", "ls-files", "--", *(f"{d}/*.py" for d in LINTED)], cwd=root, capture_output=True, text=True, check=True
    )
    return [f for f in done.stdout.split() if not f.startswith(EXCLUDED)]


def tool(name: str, cmd: list[str], root: Path) -> list[str]:
    """A tool's output when it finds something (non-zero exit), each line named after the tool."""
    done = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    if done.returncode == 0:
        return []
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    return [f"{name}: {line}" for line in lines] or [f"{name}: exit {done.returncode}"]


def duplicates(root: Path) -> list[str]:
    uv = shutil.which("uv")
    if not uv:
        return ["pylint: uv is not installed: the duplicate-code check cannot run (https://docs.astral.sh/uv/)"]
    cmd = [uv, "run", "--quiet", "--no-project", "--with-requirements", str(HERE / "requirements.txt"), *PYLINT]
    return tool("pylint", [*cmd, *python_files(root)], root)


def check(root: Path) -> list[str]:
    """Every finding: ruff's rules and layout, imports outside the standard library, duplicate code."""
    rules = tool("ruff", [sys.executable, *RUFF, *LINTED], root)
    layout = tool("ruff format", [sys.executable, *FORMAT, *LINTED], root)
    return rules + layout + foreign_imports(root) + duplicates(root)


def main(env: dict) -> int:
    root = Path(env.get("CRISSP_ROOT") or Path.cwd())
    problems = check(root)
    if not problems:
        print(
            "python-lint: clean (ruff's rules and layout from pyproject.toml, the standard library only, no duplicates)"
        )
        return 0
    print(f"python-lint: {len(problems)} finding(s):")
    print("\n".join(f"  {p}" for p in problems))
    return 1


if __name__ == "__main__":  # pragma: no cover — run by the python-lint step; main() is tested
    sys.exit(main(dict(os.environ)))
