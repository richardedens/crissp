"""A project's frontend, linted with crissp's own tools (F-34): the template's frontend-lint step (`frontend_lint`).

    python3 crissp/testsuite/lib/frontend_lint.py [--react-compiler] [<folder>]
                                    the folder: the step's own (app/frontend), else here; --react-compiler: the project
                                    uses the React Compiler, so its rules apply too (F-151)

The tools are crissp's, not the project's: frontend-lint/ (next to this lib) pins ESLint 9 and stylelint with their
plugins at exact versions and holds their lockfile and configs. They are installed once per toolkit into crissp's cache
(CRISSP_CACHE, else $XDG_CACHE_HOME/crissp, else ~/.cache/crissp), in frontend-lint/<hash of the toolkit>/ with npm ci,
so another crissp's pins land beside them and never mix. Then ESLint (flat config: @eslint/js, typescript-eslint, React
hooks (rules-of-hooks and exhaustive-deps), jsx-a11y, React's plugin only for react/no-danger; no warning allowed) and
stylelint (its recommended rules, as crissp's own CSS: mistakes, not layout; every *.css) run on the folder with crissp's configs. Both always run; the step is red when either is. The project's
package.json, its node_modules and its files are never touched, and its own lint config is not read.
The tools get the project's own files by name (lib/sources.py, F-150): what git lists (its .gitignore counts), never a
build folder (dist, build, node_modules, .next, coverage, …). A tool with nothing to lint is skipped, and says so.
Exit 0: both are clean; 1: a finding, no npm, no folder or a failed install; 2: wrong arguments.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources

KIT = Path(__file__).resolve().parents[1] / "frontend-lint"
FILES = ("package.json", "package-lock.json", "eslint.config.mjs", "stylelint.config.mjs")
SCRIPTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")  # what ESLint lints with crissp's config
STYLES = (".css",)
LIMIT = sources.LIMIT
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


def call(argv: list[str], cwd: Path, env: dict | None = None) -> int:
    return subprocess.call(argv, cwd=cwd, env=env)


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


def main(
    argv: list[str],
    env: dict,
    run: Callable[..., int] = call,
    which: Callable[[str], str | None] = shutil.which,
    cwd: Path | None = None,
) -> int:
    compiler = "--react-compiler" in argv
    argv = [a for a in argv if a != "--react-compiler"]
    if len(argv) > 1 or any(a.startswith("-") for a in argv):
        print("usage: frontend_lint.py [--react-compiler] [<folder>]")
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
    eslint = [str(bin_ / "eslint"), "--config", str(where / "eslint.config.mjs"), "--max-warnings", "0"]
    stylelint = [
        str(bin_ / "stylelint"),
        "--config",
        str(where / "stylelint.config.mjs"),
        "--config-basedir",
        str(where),
        "--allow-empty-input",
    ]
    # F-151: the React Compiler's rules only for a project that says it uses the compiler (eslint.config.mjs reads this)
    tools_env = {**env, "CRISSP_REACT_COMPILER": "1" if compiler else "0"}
    green = True
    for what, suffixes, argv in (
        ("JavaScript or TypeScript", SCRIPTS, [*eslint, "--no-warn-ignored"]),
        ("CSS", STYLES, stylelint),
    ):
        names = sources.files(folder, suffixes)
        if not names:
            print(f"frontend-lint: no {what} to lint in {folder}")
        for batch in sources.batches(names, LIMIT):
            green = run([*argv, *batch], folder, tools_env) == 0 and green
    return 0 if green else 1


if __name__ == "__main__":  # pragma: no cover — run by the frontend-lint step (lib/steps.sh); main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
