"""Code quality the way Sonar measures it, held by a ratchet: complexity and duplication may only get better.

    python3 crissp/testsuite/lib/quality.py                   measure, compare with the baseline, lower it where the code
                                                              got better; exit 1 on a regression or a problem
    python3 crissp/testsuite/lib/quality.py --accept "why"    take the numbers as they are as the new baseline, with why

What it measures (suites.json `audit.quality`: paths, default ["app"]; exclude, globs on top of tests and vendored code;
complexity, default 15; duplicate_lines, default 10):
- Complexity: the cyclomatic complexity of every function, by the pinned lizard (run through uv, as Semgrep is; it
  reads Python, JavaScript, TypeScript, Go, Java, C#, C/C++, Ruby, PHP, Rust, Swift, Scala, Lua and more). A function
  above the limit is complex.
- Duplication: the same `duplicate_lines` lines or more in two places, in one file or two, whatever their indent.
  Blank lines, comments and lines of only brackets do not count, so a run of closing braces is never a copy.

The ratchet (crissp/testsuite/quality-baseline.json, written by this step, never by hand): a complex function that is
new, or a complex function that got more complex, or more duplicated lines than the baseline, is a regression. Old code
does not block: the baseline holds what was there. A green run lowers the baseline where the code got better, so the
numbers only go down. The first run sets it.

Writes results/quality.json (for the dashboard's Code quality tile) and prints what it found.
"""

import csv
import datetime
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project

LIZARD = "lizard==1.26.1"  # complexity per function, many languages (MIT); pinned, run through uv
COMPLEXITY = 15  # Sonar's and lizard's limit for one function
DUPLICATE_LINES = 10  # Sonar's smallest copy
CODE = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".go", ".java", ".kt", ".cs", ".rb",
        ".php", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".swift", ".scala", ".lua"}
EXCLUDE = ("*/tests/*", "*/test/*", "*/__tests__/*", "*/test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*",
           "*/node_modules/*", "*/dist/*", "*/build/*", "*/vendor/*", "*/migrations/*", "*.min.js")
COMMENT = ("#", "//", "/*", "*", "<!--", "--")
MEANINGFUL = re.compile(r"[A-Za-z0-9_]")


class QualityError(Exception):
    """A measurement that could not be made: said as a problem, never a pass."""


def runner(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603 — fixed argv
    except FileNotFoundError as e:
        return 127, "", str(e)
    return done.returncode, done.stdout, done.stderr


def _paths(conf: dict) -> list[str]:
    return conf.get("paths") or ["app"]


def absent(root: Path, conf: dict) -> list[str]:
    return [p for p in _paths(conf) if not (root / p).exists()]


def files(root: Path, conf: dict) -> list[str]:
    """The code to measure: tracked files (every file without git) under the paths, without tests and vendored code."""
    here = [p for p in _paths(conf) if (root / p).exists()]
    if not here:
        return []
    if (root / ".git").exists():
        out = subprocess.run(["git", "ls-files", "-z", "--", *here], cwd=root, capture_output=True, text=True,  # noqa: S607
                             check=False).stdout
        found = [f for f in out.split("\0") if f]
    else:
        found = [str(f.relative_to(root)) for p in here for f in (root / p).rglob("*") if f.is_file()]
    skip = EXCLUDE + tuple(conf.get("exclude", []))
    return sorted(f for f in set(found) if Path(f).suffix in CODE and not any(fnmatch.fnmatch("/" + f, g) for g in skip))


def complexity(root: Path, code: list[str], run) -> dict:
    """file::function → its worst cyclomatic complexity (and where), from lizard --csv."""
    if not code:
        return {}
    status, out, err = run(["uv", "tool", "run", "--quiet", "--from", LIZARD, "lizard", "--csv", *code], root)
    rows = [r for r in csv.reader(out.splitlines()) if len(r) >= 11]
    if status and not rows:
        raise QualityError(f"lizard could not run (exit {status}): {(err or out).strip()[-300:]}")
    found: dict[str, dict] = {}
    for r in rows:
        file, function, ccn, line = r[6].removeprefix("./"), r[7], int(r[1]), int(r[9])
        key = f"{file}::{function}"
        if key not in found or ccn > found[key]["ccn"]:
            found[key] = {"file": file, "function": function, "line": line, "ccn": ccn}
    return found


def _lines(root: Path, file: str) -> list[tuple[int, str]]:
    """The lines that count for duplication: (line number, the line without its indent and inner spacing)."""
    out = []
    for n, raw in enumerate((root / file).read_text(errors="replace").splitlines(), 1):
        line = " ".join(raw.split())
        if MEANINGFUL.search(line) and not line.startswith(COMMENT):
            out.append((n, line))
    return out


def duplication(root: Path, code: list[str], size: int) -> dict:
    """Every run of `size` counted lines or more that is in two places or more."""
    lines = {f: _lines(root, f) for f in code}
    seen: dict[str, list[tuple[str, int]]] = {}
    for f, ls in lines.items():
        for i in range(len(ls) - size + 1):
            key = hashlib.sha1("\n".join(t for _, t in ls[i:i + size]).encode(), usedforsecurity=False).hexdigest()
            seen.setdefault(key, []).append((f, i))
    groups = {tuple(sorted(at)) for at in seen.values() if len(at) > 1}
    marked, blocks = set(), []
    for at in sorted(groups):
        for f, i in at:
            marked.update((f, j) for j in range(i, i + size))
        if tuple((f, i - 1) for f, i in at) in groups:
            continue  # the same copy, one line further: counted with the block it continues
        length = size
        while tuple((f, i + length - size + 1) for f, i in at) in groups:
            length += 1
        blocks.append({"lines": length, "at": [[f, lines[f][i][0]] for f, i in at]})
    total = sum(len(ls) for ls in lines.values())
    return {"min_lines": size, "lines": len(marked), "of": total,
            "percent": round(100 * len(marked) / total, 1) if total else 0.0, "blocks": blocks}


def judge(measured: dict, baseline: dict | None, limit: int = COMPLEXITY) -> tuple[list[str], dict]:
    """The regressions against the baseline, and the baseline to keep (lowered where the code got better)."""
    now = {"complex": {k: v["ccn"] for k, v in sorted(measured["complex"].items())},
           "duplicated_lines": measured["duplication"]["lines"]}
    if baseline is None:
        return [], now
    worse = []
    for key, ccn in now["complex"].items():
        was = baseline["complex"].get(key)
        if was is None:
            worse.append(f"{key} is new and too complex: cyclomatic complexity {ccn} (at most {limit})")
        elif ccn > was:
            worse.append(f"{key} grew more complex: cyclomatic complexity {ccn}, was {was}")
    if now["duplicated_lines"] > baseline["duplicated_lines"]:
        worse.append(f"more duplicated lines: {now['duplicated_lines']}, was {baseline['duplicated_lines']}")
    if worse:
        return worse, baseline
    same = now == {"complex": baseline["complex"], "duplicated_lines": baseline["duplicated_lines"]}
    return [], baseline if same else now


def accepted(measured: dict, reason: str, on: str) -> dict:
    _, now = judge(measured, None)
    return {**now, "accepted": {"reason": reason, "on": on}}


def render(report: dict) -> str:
    d = report["duplication"]
    lines = [f"Measured: {report['files']} files, {report['functions']} functions — {'; '.join(report['paths'])}"]
    lines += [f"note     not there yet, not measured: {p}" for p in report["absent"]]
    lines += [f"PROBLEM  {p}" for p in report["problems"]]
    lines += [f"complex  {c['file']}::{c['function']}  cyclomatic complexity {c['ccn']} (line {c['line']})"
              for c in report["complex"]]
    lines += [f"copy     {b['lines']} lines: " + ", ".join(f"{f} line {n}" for f, n in b["at"]) for b in d["blocks"]]
    lines += [f"REGRESSION {r}" for r in report["regressions"]]
    if report["problems"]:
        lines.append("Not green: the quality could not be measured.")
    elif report["regressions"]:
        lines.append("Not green: the code got worse. Simplify the function or remove the copy; for an honest reason "
                     "take the numbers as they are: python3 crissp/testsuite/lib/quality.py --accept \"why\".")
    elif not report["files"]:
        lines.append("Nothing to measure yet: none of the places suites.json names is here.")
    else:
        lines.append(f"{report['functions_over']} complex functions (above {report['threshold']}), "
                     f"{d['percent']}% duplicated ({d['lines']} of {d['of']} lines): {report['baseline']}.")
    return "\n".join(lines)


def main(argv: list[str], root: Path | None = None) -> int:
    reason = None
    if len(argv) == 3 and argv[1] == "--accept" and argv[2].strip():
        reason = argv[2].strip()
    elif len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root = root or project.root()
    try:
        conf = (project.load(root)["audit"] or {}).get("quality") or {}
    except project.ConfigError as e:
        print(f"quality: {e}", file=sys.stderr)
        return 2
    limit, size = conf.get("complexity", COMPLEXITY), conf.get("duplicate_lines", DUPLICATE_LINES)
    code, problems = files(root, conf), []
    try:
        functions = complexity(root, code, runner)
    except QualityError as e:
        functions, problems = {}, [str(e)]
    measured = {"complex": {k: v for k, v in functions.items() if v["ccn"] > limit},
                "duplication": duplication(root, code, size)}
    path = root / "crissp/testsuite/quality-baseline.json"
    baseline = json.loads(path.read_text()) if path.is_file() else None
    regressions, keep, said = [], baseline, "held"
    if not problems:
        if reason:
            keep, said = accepted(measured, reason, datetime.date.today().isoformat()), f"accepted ({reason})"
        else:
            regressions, keep = judge(measured, baseline, limit)
            said = "baseline set" if baseline is None else "held" if keep == baseline else "the baseline went down"
        if keep != baseline:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(keep, indent=1) + "\n")
    report = {"date": datetime.date.today().isoformat(), "paths": _paths(conf), "absent": absent(root, conf),
              "files": len(code), "functions": len(functions), "threshold": limit,
              "complex": sorted(measured["complex"].values(), key=lambda c: (-c["ccn"], c["file"], c["function"])),
              "functions_over": len(measured["complex"]), "max_ccn": max((v["ccn"] for v in functions.values()), default=0),
              "duplication": measured["duplication"], "regressions": regressions, "problems": problems,
              "baseline": said, "ok": not regressions and not problems}
    results = project.results(root)
    results.mkdir(parents=True, exist_ok=True)
    (results / "quality.json").write_text(json.dumps(report, indent=1) + "\n")
    print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":  # pragma: no cover — run by the quality step; main() is tested
    sys.exit(main(sys.argv))
