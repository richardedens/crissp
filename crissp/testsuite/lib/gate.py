"""Coverage gate: coverage may only go up.

    python3 crissp/testsuite/lib/gate.py                      check the last run against the baseline; raise the baseline where
                                                       coverage went up (the ratchet); exit 1 on any drop
    python3 crissp/testsuite/lib/gate.py --suites backend     only the suites that ran (crissp/check.sh runs what a change touches);
                                                       the others keep their baseline as it is
    python3 crissp/testsuite/lib/gate.py --accept "reason"    accept the current numbers as the new baseline, also where they went
                                                       down (e.g. tested code removed); the reason is kept in the baseline

Rules
- The suites are the steps crissp/testsuite/suites.json marks `gate` (lib/project.py), each with the sources its
  coverage measures; a file is named by its path in the project, however coverage.py named it.
- Total line and branch coverage of each suite may not drop. A suite the baseline does not name yet (the first full
  run) sets its baseline from that run.
- A file may not drop below its baseline; a file at 100% stays at 100%.
- A file that is new (not in the baseline) must be at 100% line and branch coverage: new code is fully tested.
- `# pragma: no cover` (and `# pragma: no branch`) only with a reason after a dash: `# pragma: no cover — why`.
- Diff coverage: every line added or changed since the commit the baseline was taken at (`commit` in the baseline) in
  those packages must be covered, and every branch that starts on such a line must be taken both ways. So a file at 85%
  cannot take 50 untested new lines. Lines coverage does not count (comments, blank lines, continuation lines) and lines
  excluded with `# pragma: no cover — reason` are ignored. Each uncovered changed line is reported as file:line.
  Without a recorded commit (the first run, or a repository without commits) the rule is skipped with a message, and
  the first green run with a commit records one.
  The changed lines come from `git diff -U0 -M <commit>` against the checked-out tree, the code coverage measured (in
  crissp/check.sh and crissp/check-all.sh that is exactly HEAD: they only run on committed code).
- Only a green run (or --accept with a reason) moves the baseline: its numbers, and (when every suite was checked) its
  commit; a run that moves no number leaves the file as it is. A run of some suites keeps the commit, so the next diff rule looks back at least as far: stricter, never laxer.

Writes results/gate.json (everything above, for whoever reads it) and results/gate.log (what it printed).
"""

import fnmatch
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402

# Set by configure() from the project's suites.json: where it is, and per gated suite what its coverage measures
# (SOURCES), the folder its coverage runs in (DIRS: coverage.py names files relative to it) and what it leaves out.
ROOT = Path(".")
RESULTS = ROOT / "results"
BASELINE = ROOT / "coverage-baseline.json"
SOURCES: dict[str, list[Path]] = {}
DIRS: dict[str, Path] = {}
OMIT: dict[str, list[str]] = {}
PRAGMA = re.compile(r"#\s*pragma:\s*no\s+(cover|branch)\b(.*)$")
EPSILON = 0.05  # rounding noise (percentages are compared at one decimal)


def configure(root: Path) -> None:
    """The gate for this project: its results, its baseline and the suites its configuration gates."""
    global ROOT, RESULTS, BASELINE, SOURCES, DIRS, OMIT
    gated = [s for s in project.load(root)["steps"] if s["gate"]]
    ROOT, RESULTS = root, project.results(root)
    BASELINE = root / "crissp" / "testsuite" / "coverage-baseline.json"
    SOURCES = {s["key"]: [root / x for x in s["sources"]] for s in gated}
    DIRS = {s["key"]: root / s["dir"] for s in gated}
    OMIT = {s["key"]: s["omit"] for s in gated}


def named(key: str, name: str) -> str:
    """A file as coverage.py named it (relative to where it ran, or absolute) → its path in the project."""
    path = Path(name) if Path(name).is_absolute() else DIRS.get(key, ROOT) / name
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return name  # outside the project: as it was named


def files_of(key: str) -> list[Path]:
    """The Python files a suite measures, without what it leaves out."""
    out = []
    for src in SOURCES[key]:
        for path in ([src] if src.is_file() else sorted(src.rglob("*.py"))):
            if not any(fnmatch.fnmatch(str(path), pattern) for pattern in OMIT.get(key, [])):
                out.append(path)
    return out


def pct(covered: int, total: int) -> float:
    return round(100 * covered / total, 2) if total else 100.0


def report(key: str) -> dict | None:
    """The suite's coverage JSON, its files named by their path in the project."""
    path = RESULTS / f"coverage-{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data["files"] = {named(key, name): f for name, f in data["files"].items()}
    return data


def measure(key: str) -> dict | None:
    data = report(key)
    if data is None:
        return None
    files = {}
    for name, f in data["files"].items():
        s = f["summary"]
        files[name] = {"line": pct(s["covered_lines"], s["num_statements"]),
                       "branch": pct(s.get("covered_branches", 0), s.get("num_branches", 0))}
    t = data["totals"]
    return {"line": pct(t["covered_lines"], t["num_statements"]),
            "branch": pct(t.get("covered_branches", 0), t.get("num_branches", 0)), "files": files}


def pragmas(suites: list[str]) -> tuple[list[dict], list[dict]]:
    """Every coverage exception in the code, and the ones without a reason."""
    found, bare = [], []
    for key in suites:
        for path in files_of(key):
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                m = PRAGMA.search(line)
                if not m:
                    continue
                reason = m.group(2).strip().lstrip("—-–: ").strip()
                item = {"file": str(path.relative_to(ROOT)), "line": n, "kind": m.group(1), "reason": reason}
                found.append(item)
                if not reason:
                    bare.append(item)
    return found, bare


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), "-c", "core.quotePath=false", *args], capture_output=True, text=True)


def head_commit() -> str | None:
    """The commit checked out at ROOT, or None when ROOT is not the top of a git checkout (or has no commit yet)."""
    top = git("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != ROOT.resolve():
        return None
    head = git("rev-parse", "--verify", "-q", "HEAD")
    return head.stdout.strip() if head.returncode == 0 else None


HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str, suites: list[str]) -> dict[str, set[int]]:
    """Lines added or changed since `base` in these suites' packages, per path relative to ROOT (a rename follows the file)."""
    packages = sorted({str(src.relative_to(ROOT)) for key in suites for src in SOURCES[key]})
    out = git("diff", "-U0", "-M", "--no-color", "--no-ext-diff", base, "--", *packages)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or "git diff failed")
    lines: dict[str, set[int]] = {}
    current = None
    for row in out.stdout.splitlines():
        if row.startswith("+++ "):
            target = row[4:].strip()
            current = None if target == "/dev/null" else target.removeprefix("b/")  # a deleted file adds nothing
        elif current and (m := HUNK.match(row)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            lines.setdefault(current, set()).update(range(start, start + count))  # count 0: lines only removed
    return lines


def diff_coverage(base: str | None, suites: list[str] | None = None) -> dict:
    """Coverage of the lines (and the branches starting on them) changed since the baseline's commit."""
    suites = list(SOURCES) if suites is None else suites
    result: dict = {"base": base, "skipped": None, "lines": 0, "covered_lines": 0, "branches": 0, "covered_branches": 0,
                    "percent": 100.0, "uncovered": [], "files": {}}
    if not base:
        result["skipped"] = "no baseline commit recorded yet (first run): the rule starts from the commit a green run records"
        return result
    if head_commit() is None:
        result["skipped"] = "not a git checkout with a commit: the changed lines cannot be found"
        return result
    if git("cat-file", "-e", f"{base}^{{commit}}").returncode:
        result["skipped"] = f"the baseline commit {base[:10]} is not in this checkout (history rewritten?): the rule cannot run"
        return result
    try:
        changed = changed_lines(base, suites)
    except RuntimeError as e:  # pragma: no cover — git diff failing on a commit cat-file just found
        result["skipped"] = f"git diff failed: {e}"
        return result
    reports = {key: report(key) for key in suites}
    for path, numbers in sorted(changed.items()):
        key = next(k for k in suites for src in SOURCES[k]
                   if path == str(src.relative_to(ROOT)) or path.startswith(str(src.relative_to(ROOT)) + "/"))
        if not path.endswith(".py") or reports[key] is None or (ROOT / path) not in files_of(key):
            continue  # not Python, left out (tests), or that suite measured nothing (the gate already says so)
        f = reports[key]["files"].get(path)
        if f is None:
            result["uncovered"].append({"file": path, "line": min(numbers), "what": "changed, but not measured by coverage"})
            continue
        missing = set(f.get("missing_lines", []))
        executable = numbers & (set(f.get("executed_lines", [])) | missing)
        taken = [src for src, _ in f.get("executed_branches", []) if src in numbers]
        missed: dict[int, list[int]] = {}
        for src, dst in f.get("missing_branches", []):
            if src in numbers and src not in missing:  # an uncovered line is reported once, as a line
                missed.setdefault(src, []).append(dst)
        row = {"lines": len(executable), "covered_lines": len(executable - missing),
               "branches": len(taken) + sum(len(d) for d in missed.values()), "covered_branches": len(taken)}
        if row["lines"] or row["branches"]:
            result["files"][path] = row
        for name in row:
            result[name] += row[name]
        for n in sorted(executable & missing):
            result["uncovered"].append({"file": path, "line": n, "what": "changed line not covered"})
        for n, dsts in sorted(missed.items()):
            to = ", ".join("the exit" if d < 0 else f"line {d}" for d in dsts)
            result["uncovered"].append({"file": path, "line": n, "what": f"changed line: its branch to {to} is never taken"})
    result["percent"] = pct(result["covered_lines"] + result["covered_branches"], result["lines"] + result["branches"])
    return result


def check(accept_reason: str | None = None, suites: list[str] | None = None) -> int:
    every = suites is None or set(suites) >= set(SOURCES)
    suites = list(SOURCES) if suites is None else [k for k in SOURCES if k in suites]
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {"suites": {}}
    problems: list[str] = []
    raised: list[str] = []
    new_suites = dict(baseline.get("suites", {}))  # a suite that did not run keeps its baseline
    for key in suites:
        now = measure(key)
        if now is None:
            problems.append(f"{key}: no coverage measured (did the tests run?)")
            continue
        before = baseline.get("suites", {}).get(key)
        if before is None or accept_reason:
            new_suites[key] = now
            continue
        for metric in ("line", "branch"):
            if now[metric] + EPSILON < before[metric]:
                problems.append(f"{key}: total {metric} coverage dropped {before[metric]:.1f}% → {now[metric]:.1f}%")
        files = dict(before["files"])
        for name, cov in now["files"].items():
            old = before["files"].get(name)
            if old is None:
                if cov["line"] < 100 or cov["branch"] < 100:
                    problems.append(f"{key}: new file {name} is at {cov['line']:.1f}% lines / {cov['branch']:.1f}% branches "
                                    "(new code: 100%)")
                files[name] = cov
                continue
            for metric in ("line", "branch"):
                if cov[metric] + EPSILON < old[metric]:
                    problems.append(f"{key}: {name} {metric} coverage dropped {old[metric]:.1f}% → {cov[metric]:.1f}%")
            if cov["line"] > old["line"] + EPSILON or cov["branch"] > old["branch"] + EPSILON:
                raised.append(f"{key}: {name} {old['line']:.1f}/{old['branch']:.1f} → {cov['line']:.1f}/{cov['branch']:.1f}")
            files[name] = {m: max(cov[m], old[m]) for m in ("line", "branch")}
        for name in set(before["files"]) - set(now["files"]):
            files.pop(name, None)  # a removed file leaves the baseline
        new_suites[key] = {"line": max(now["line"], before["line"]), "branch": max(now["branch"], before["branch"]),
                           "files": files}
    exceptions, bare = pragmas(suites)
    problems += [f"{b['file']}:{b['line']}: '# pragma: no {b['kind']}' without a reason (write: # pragma: no {b['kind']} — why)"
                 for b in bare]
    diff = diff_coverage(baseline.get("commit"), suites)
    problems += [f"{u['file']}:{u['line']}: {u['what']} (new and changed code is fully covered)" for u in diff["uncovered"]]
    ok = not problems
    if ok or accept_reason:  # only a green run (or an explicit acceptance) moves the baseline
        history = baseline.get("accepted", [])
        if accept_reason:
            history.append({"at": time.strftime("%Y-%m-%d %H:%M"), "reason": accept_reason})
        moved = {"suites": new_suites, "accepted": history}
        commit = (head_commit() if every else None) or baseline.get("commit")
        if commit:
            moved["commit"] = commit  # the diff rule of the next run starts here
        # Only what moves is written: no baseline yet, an acceptance, a number that changed, or a commit the diff rule
        # needs (none recorded yet, or one this checkout no longer knows). A run that moves no number keeps the file as it is (its older commit makes the next diff rule look back
        # further: stricter, never laxer), so a green run never asks for a commit that only records a hash.
        if (not BASELINE.exists() or accept_reason or new_suites != baseline.get("suites", {})
                or (commit and diff["skipped"] and commit != baseline.get("commit"))):  # none recorded, or one git lost
            BASELINE.write_text(json.dumps(moved, indent=1, sort_keys=True) + "\n")
    out: list[str] = [f"✗ {p}" for p in problems]
    if raised:
        out.append(f"↑ coverage went up in {len(raised)} file(s); baseline raised")
    if diff["skipped"]:
        out.append(f"diff coverage: skipped: {diff['skipped']}")
    else:
        out.append(f"diff coverage since {diff['base'][:10]}: {diff['covered_lines']}/{diff['lines']} changed lines and "
                   f"{diff['covered_branches']}/{diff['branches']} branches covered ({diff['percent']:.1f}%)")
    out.append("coverage gate: " + ("accepted: " + accept_reason if accept_reason else ("green" if ok else "RED")))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "gate.json").write_text(json.dumps({"ok": ok or bool(accept_reason), "suites": suites, "problems": problems,
                                                     "raised": raised, "exceptions": exceptions,
                                                     "accepted": baseline.get("accepted", []), "diff": diff}, indent=1))
    (RESULTS / "gate.log").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0 if ok or accept_reason else 1


def main(argv: list[str], root: Path | None = None) -> int:
    try:
        configure(root or project.root())
    except project.ConfigError as e:
        print(f"gate: {e}", file=sys.stderr)
        return 2
    args = argv[1:]
    reason = suites = None
    if "--accept" in args:
        i = args.index("--accept")
        reason = args[i + 1] if len(args) > i + 1 and args[i + 1].strip() else None
        if not reason:
            print("--accept needs a reason", file=sys.stderr)
            return 2
    if "--suites" in args:
        i = args.index("--suites")
        suites = [s for s in (args[i + 1] if len(args) > i + 1 else "").split(",") if s]
        unknown = [s for s in suites if s not in SOURCES]
        if not suites or unknown:
            print(f"--suites takes a comma-separated list of {', '.join(SOURCES)}", file=sys.stderr)
            return 2
    return check(reason, suites)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
