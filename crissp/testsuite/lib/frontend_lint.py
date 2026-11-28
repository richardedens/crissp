"""A project's frontend, linted with crissp's own tools (F-31): the template's frontend-lint step (`frontend_lint`).

    python3 crissp/testsuite/lib/frontend_lint.py [<folder>]     the folder: the step's own (app/frontend), else here

The tools are crissp's, not the project's: frontend-lint/ (next to this lib) pins ESLint 9 and stylelint with their
plugins at exact versions and holds their lockfile and configs. They are installed once per toolkit into crissp's cache
(CRISSP_CACHE, else $XDG_CACHE_HOME/crissp, else ~/.cache/crissp), in frontend-lint/<hash of the toolkit>/ with npm ci,
so another crissp's pins land beside them and never mix. Then ESLint (flat config: @eslint/js, typescript-eslint, React
hooks, jsx-a11y, React's plugin only for react/no-danger; no warning allowed) and stylelint (its standard config, every
*.css) run on the folder with crissp's configs. Both always run; the step is red when either is. The project's
package.json, its node_modules and its files are never touched, and its own lint config is not read.
Exit 0: both are clean; 1: a finding, no npm, no folder or a failed install; 2: wrong arguments.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "frontend-lint"
FILES = ("package.json", "package-lock.json", "eslint.config.mjs", "stylelint.config.mjs")
DONE = ".crissp-installed"  # written after npm ci succeeded: a failed install is tried again


def cache(env: dict) -> Path:
    if env.get("CRISSP_CACHE"):
        return Path(env["CRISSP_CACHE"])
    if env.get("XDG_CACHE_HOME"):
        return Path(env["XDG_CACHE_HOME"]) / "crissp"
    return Path(env["HOME"]) / ".cache" / "crissp"


def place(env: dict) -> Path:
    """Where this toolkit is installed: its own folder in the cache, named after what it pins and configures."""
    digest = hashlib.sha256(b"".join((KIT / name).read_bytes() for name in FILES)).hexdigest()[:16]
    return cache(env) / "frontend-lint" / digest


def call(argv: list[str], cwd: Path) -> int:
    return subprocess.call(argv, cwd=cwd)


def install(where: Path, run: Callable[[list[str], Path], int], npm: str) -> bool:
    if (where / DONE).exists():
        return True
    where.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(KIT / name, where / name)
    if run([npm, "ci", "--no-audit", "--no-fund", "--loglevel=error"], where) != 0:
        print(f"frontend-lint: npm ci failed in {where} (network? it is tried again next time)")
        return False
    (where / DONE).write_text("")
    print(f"frontend-lint: crissp's lint tools installed in {where}")
    return True


def main(argv: list[str], env: dict, run: Callable[[list[str], Path], int] = call,
         which: Callable[[str], str | None] = shutil.which, cwd: Path | None = None) -> int:
    if len(argv) > 1:
        print("usage: frontend_lint.py [<folder>]")
        return 2
    here = Path(cwd or os.getcwd())
    folder = here / argv[0] if argv else here
    if not folder.is_dir():
        print(f"frontend-lint: {argv[0]} is not a folder")
        return 1
    npm = which("npm")
    if npm is None:
        print("frontend-lint: npm is missing. Install Node.js (brew install node)")
        return 1
    where = place(env)
    if not install(where, run, npm):
        return 1
    bin_ = where / "node_modules" / ".bin"
    eslint = run([str(bin_ / "eslint"), "--config", str(where / "eslint.config.mjs"), "--max-warnings", "0", "."],
                 folder)
    stylelint = run([str(bin_ / "stylelint"), "--config", str(where / "stylelint.config.mjs"), "--config-basedir",
                     str(where), "--allow-empty-input", "**/*.css"], folder)
    return 0 if eslint == 0 and stylelint == 0 else 1


if __name__ == "__main__":  # pragma: no cover — run by the frontend-lint step (lib/steps.sh); main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
