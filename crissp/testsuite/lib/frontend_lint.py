"""A project's frontend, linted with crissp's own tools (F-34): the template's frontend-lint step (`frontend_lint`).

    python3 crissp/testsuite/lib/frontend_lint.py [--react-compiler] [--baseline] [<folder>]
        <folder>            the step's own (app/frontend), else here
        --react-compiler    the project uses the React Compiler, so the compiler's rules apply too (F-151)
        --baseline          write the folder's lint baseline from what is found now (lib/lint_ratchet.py, F-152)

The tools are crissp's, not the project's: frontend-lint/ (next to this lib) pins ESLint 9 and stylelint with their
plugins at exact versions and holds their lockfile and configs. They are installed once per toolkit into crissp's cache
(CRISSP_CACHE, else $XDG_CACHE_HOME/crissp, else ~/.cache/crissp), in frontend-lint/<hash of the toolkit>/ with npm ci,
so another crissp's pins land beside them and never mix. Then ESLint (flat config: @eslint/js, typescript-eslint, React
hooks (rules-of-hooks and exhaustive-deps), jsx-a11y, React's plugin only for react/no-danger) and stylelint (its
recommended rules, as crissp's own CSS: mistakes, not layout) run on the folder with crissp's configs. Both always run.
The project's package.json, its node_modules and its files are never touched, and its own lint config is not read.
The tools get the project's own files by name (lib/sources.py, F-150): what git lists (its .gitignore counts), never a
build folder (dist, build, node_modules, .next, coverage, …). A tool with nothing to lint is skipped, and says so.
Before a commit (the pre-commit hook, CRISSP_STAGED) only the staged files are linted, and the baseline is left as it
is (F-154). Every finding counts, a warning too. With a baseline (crissp/testsuite/lint-baseline.json) the ratchet decides what
blocks (lib/lint_ratchet.py); without one, every finding does.
Exit 0: nothing blocks; 1: a finding that blocks, a tool that could not run, no npm, no folder or a failed install;
2: wrong arguments.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_ratchet
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
    """Run a command in its folder. A tool that writes its report to a file (--output-file) also prints it (stylelint
    on stderr): that copy is left out; anything else it says (why it could not run) is passed on."""
    if "--output-file" not in argv:
        return subprocess.call(argv, cwd=cwd, env=env)
    done = subprocess.run(
        argv, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False
    )
    try:
        copy = isinstance(json.loads(done.stderr), list)
    except ValueError:
        copy = False
    if done.stderr and not copy:
        sys.stderr.write(done.stderr)
    return done.returncode


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


def _relative(path: str, folder: Path) -> str:
    try:
        return Path(path).resolve().relative_to(folder.resolve()).as_posix()
    except ValueError:
        return path


def from_eslint(report: list, folder: Path) -> tuple[list[dict], list[str]]:
    found = [
        {
            "file": _relative(r["filePath"], folder),
            "line": m.get("line", 0),
            "column": m.get("column", 0),
            "rule": m.get("ruleId") or "parse-error",
            "message": m.get("message", ""),
        }
        for r in report
        for m in r.get("messages", [])
    ]
    return found, []


def from_stylelint(report: list, folder: Path) -> tuple[list[dict], list[str]]:
    found, problems = [], []
    for r in report:
        for w in r.get("warnings", []):
            text = w.get("text", "")
            suffix = f" ({w.get('rule')})"
            found.append(
                {
                    "file": _relative(r["source"], folder),
                    "line": w.get("line", 0),
                    "column": w.get("column", 0),
                    "rule": w.get("rule", "stylelint"),
                    "message": text[: -len(suffix)] if text.endswith(suffix) else text,
                }
            )
        problems += [f"stylelint: {w.get('text', '')}" for w in r.get("invalidOptionWarnings", [])]
    return found, problems


# per tool: what it lints, its report flags, the exit codes that mean it ran (with or without findings), its reader
TOOLS = {
    "eslint": ("JavaScript or TypeScript", SCRIPTS, ("--format", "json"), (0, 1), from_eslint),
    "stylelint": ("CSS", STYLES, ("--formatter", "json"), (0, 2), from_stylelint),
}


def lint(tool: str, argv: list[str], folder: Path, run, env: dict, names: list[str]) -> tuple[list[dict], list[str]]:
    """One tool over the names, in batches: its findings, and why it could not run (a problem: red, never a pass)."""
    what, _, report_flags, ran, read = TOOLS[tool]
    found, problems = [], []
    if not names:
        print(f"frontend-lint: no {what} to lint in {folder}")
    with tempfile.TemporaryDirectory(prefix="crissp-lint-") as tmp:
        for n, batch in enumerate(sources.batches(names, LIMIT)):
            out = Path(tmp) / f"{tool}-{n}.json"
            code = run([*argv, *report_flags, "--output-file", str(out), *batch], folder, env)
            try:
                report = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = None
            if code not in ran or not isinstance(report, list):
                problems.append(f"{tool} could not run (exit {code}): its output above says why")
                continue
            more, why = read(report, folder)
            found += more
            problems += why
    return found, problems


def commands(where: Path) -> dict[str, list[str]]:
    """The two tools as crissp runs them: its installed binaries with its configs."""
    bin_ = where / "node_modules" / ".bin"
    return {
        "eslint": [str(bin_ / "eslint"), "--config", str(where / "eslint.config.mjs"), "--no-warn-ignored"],
        "stylelint": [
            str(bin_ / "stylelint"),
            "--config",
            str(where / "stylelint.config.mjs"),
            "--config-basedir",
            str(where),
            "--allow-empty-input",
        ],
    }


def without_exceptions(root: Path, findings: list[dict]) -> tuple[list[dict], list[str]]:
    """F-153: the findings of the rules this project did not switch off; each rule that is off is said, with why."""
    off, wrong = lint_ratchet.exceptions(root)
    kept, dropped = lint_ratchet.without(findings, off)
    for e in off:
        print(
            f"frontend-lint: {e['rule']} is off ({lint_ratchet.EXCEPTIONS}): {e['why']} ({e['by']}, since "
            f"{e['since']}); {dropped.get(e['rule'], 0)} not counted"
        )
    return kept, wrong


def _folder(argv: list[str], here: Path) -> Path | int:
    """The folder to lint, or the exit code when the arguments are wrong (2) or it is no folder (1)."""
    if len(argv) > 1 or any(a.startswith("-") for a in argv):
        print("usage: frontend_lint.py [--react-compiler] [--baseline] [<folder>]")
        return 2
    folder = here / argv[0] if argv else here
    if not folder.is_dir():
        print(f"frontend-lint: {argv[0]} is not a folder")
        return 1
    return folder


def main(
    argv: list[str],
    env: dict,
    run: Callable[..., int] = call,
    which: Callable[[str], str | None] = shutil.which,
    cwd: Path | None = None,
) -> int:
    flags = {a for a in argv if a in ("--react-compiler", "--baseline")}
    folder = _folder([a for a in argv if a not in flags], Path(cwd or os.getcwd()))
    if isinstance(folder, int):
        return folder
    npm = which("npm")
    if npm is None:
        print("frontend-lint: npm is missing. Install Node.js (brew install node)")
        return 1
    where = place(env)
    if not install(where, run, npm):
        return 1
    # F-151: the React Compiler's rules only for a project that says it uses the compiler (eslint.config.mjs reads this)
    tools_env = {**env, "CRISSP_REACT_COMPILER": "1" if "--react-compiler" in flags else "0"}
    only = sources.staged(folder, env)  # F-154: before a commit, only what is staged
    findings, problems = [], []
    for tool, command in commands(where).items():
        names = [n for n in sources.files(folder, TOOLS[tool][1]) if only is None or n in only]
        found, why = lint(tool, command, folder, run, tools_env, names)
        findings += found
        problems += why
    root = lint_ratchet.root_of(folder, env)
    key = lint_ratchet.key_of(folder, root)
    findings, wrong = without_exceptions(root, findings)
    problems += wrong
    folders = lint_ratchet.load(root)
    if "--baseline" in flags:
        return write_baseline(root, folder, key, folders, findings, problems)
    blocking, allowed, shrunk = lint_ratchet.judge(folder, findings, folders.get(key), complete=only is None)
    return report(root, key, folders, blocking, allowed, shrunk, problems)


def write_baseline(root: Path, folder: Path, key: str, folders: dict, findings: list[dict], problems: list[str]) -> int:
    for p in problems:
        print(f"frontend-lint: {p}")
    if problems:
        print("frontend-lint: no baseline written: the lint must run first")
        return 1
    if key in folders:
        print(
            f"frontend-lint: {key} has a baseline already, and it only shrinks: each green run lowers it "
            f"({lint_ratchet.BASELINE})"
        )
        return 1
    folders[key] = lint_ratchet.baseline_of(folder, findings)
    lint_ratchet.save(root, folders)
    print(
        f"frontend-lint: baseline written for {key}: {len(findings)} findings in {len(folders[key]['files'])} files. "
        f"Commit {lint_ratchet.BASELINE}; from now on they only go down, and a new or changed file is clean."
    )
    return 0


def report(root: Path, key: str, folders: dict, blocking, allowed: int, shrunk, problems: list[str]) -> int:
    for f in blocking:
        why = f" ({f['why']})" if f["why"] else ""
        print(f"{f['file']}:{f['line']}:{f['column']}: error: {f['message']} [{f['rule']}]{why}")
    for p in problems:
        print(f"frontend-lint: {p}")
    known = f"; {allowed} more known in the baseline ({lint_ratchet.BASELINE})" if allowed else ""
    if blocking:
        print(f"Found {len(blocking)} {'error' if len(blocking) == 1 else 'errors'}{known}.")
        if key not in folders:
            print(
                "frontend-lint: a project with code can switch the lint on step by step: frontend_lint --baseline "
                "writes what is found now, and from then on it only goes down (lib/lint_ratchet.py)"
            )
        return 1
    if shrunk is not None:
        folders[key] = shrunk
        lint_ratchet.save(root, folders)
        print(f"frontend-lint: fewer findings than the baseline: it shrank, commit {lint_ratchet.BASELINE}")
    if problems:
        return 1
    print(f"frontend-lint: nothing blocks{known}")
    return 0


if __name__ == "__main__":  # pragma: no cover — run by the frontend-lint step (lib/steps.sh); main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
