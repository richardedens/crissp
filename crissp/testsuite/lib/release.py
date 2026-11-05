"""The release certificate: nothing is deployed that was not entirely tested, exactly as it is.

A full run (crissp/check-all.sh: every step of the project's suites, crissp/testsuite/suites.json) writes crissp/testsuite/results/release.json: the commit it tested,
whether tracked code had uncommitted changes, whether the code changed while it ran, and every step's result.
deploy.sh refuses unless that certificate is green, at most 7 days old, and about exactly the code being deployed: HEAD
is the certified commit and nothing tracked is changed. The one difference allowed is the coverage baseline the run
raises itself (crissp/testsuite/coverage-baseline.json).

    python3 crissp/testsuite/lib/release.py start            before the run: remember the commit and the uncommitted changes
                                                      (the last certificate stays, for its own commit, until finish)
    python3 crissp/testsuite/lib/release.py finish           after the run: write release.json (a red run keeps the last
                                                      green one as release-previous.json, for its older commit only)
    python3 crissp/testsuite/lib/release.py check [--max-age-hours 168]   for deploy.sh: exit 1 with the reasons when not allowed
    python3 crissp/testsuite/lib/release.py advance <ran.json>   after a green crissp/check.sh: move the certificate to HEAD, if allowed

crissp/check.sh tests only what changed since the certificate's commit (crissp/testsuite/lib/impact.py decides what that is) and
then advances the certificate to this commit. The full run stays the foundation: a deploy needs the last full run to be
at most 7 days old, and every change since covered by a green crissp/check.sh.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402

# written by the run itself: may differ between the tested and the deployed code
GENERATED = ("crissp/testsuite/coverage-baseline.json",)
MAX_AGE_HOURS = 7 * 24
INTERRUPTED = ("A full run was started after this certificate and did not finish: the certificate now only stands for "
               "its own commit, nothing can be built on it. Run crissp/check-all.sh.")


def _git(*args: str, root: Path) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _head(root: Path) -> str:
    return _git("rev-parse", "HEAD", root=root).strip()


def _changes(root: Path) -> str:
    """A fingerprint of the uncommitted changes to tracked code (the generated coverage baseline left out)."""
    diff = _git("diff", "HEAD", "--", ".", *(f":(exclude){p}" for p in GENERATED), root=root)
    return hashlib.sha256(diff.encode()).hexdigest() if diff else ""


def _code_since(commit: str, root: Path) -> list[str]:
    """Files changed in commits since `commit`, without the baseline the run generates itself."""
    return [f for f in _git("diff", "--name-only", f"{commit}..HEAD", root=root).splitlines()
            if f and not f.startswith(GENERATED)]


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def needed(root: Path) -> list[str]:
    """The steps a full run must have run: every step of the project's suites (lib/project.py), the gate too."""
    try:
        return [s["key"] for s in project.steps(project.load(root), root)]
    except project.ConfigError as e:
        return [f"(the configuration: {e})"]


def _where(root: Path | None, results: Path | None) -> tuple[Path, Path]:
    root = root or project.root()
    return root, results or project.results(root)


def start(root: Path | None = None, results: Path | None = None) -> None:
    root, results = _where(root, results)
    results.mkdir(parents=True, exist_ok=True)
    # the last certificate stays until this run has a result (finish), valid for its own commit only
    (results / "release-start.json").write_text(json.dumps({"commit": _head(root), "changes": _changes(root),
                                                            "started": time.time()}))


def finish(root: Path | None = None, results: Path | None = None) -> dict:
    """The run's certificate becomes release.json. When it is red, the last green certificate before it is kept as
    release-previous.json, valid only for its own (older) commit; not when this red run tested that same commit."""
    root, results = _where(root, results)
    began = json.loads((results / "release-start.json").read_text())
    steps = _load(results / "steps.json") or {}
    cert = {"commit": began["commit"], "changes": began["changes"], "started": began["started"], "finished": time.time(),
            "changed_during_run": bool(_code_since(began["commit"], root)) or _changes(root) != began["changes"],
            "steps": steps}
    previous = results / "release-previous.json"
    last = _load(results / "release.json")
    need = needed(root)
    green = last if last and not _faults(last, need) else _load(previous)
    if _faults(cert, need) and green and green["commit"] != cert["commit"]:
        previous.write_text(json.dumps(green, indent=2))
    else:
        previous.unlink(missing_ok=True)
    (results / "release.json").write_text(json.dumps(cert, indent=2))
    return cert


def interrupted(cert: dict, results: Path) -> bool:
    """A full run started after this certificate and did not finish: nothing may be built on the certificate any more."""
    began = _load(results / "release-start.json")
    return bool(began) and began.get("started", 0) > cert.get("started", 0)


def _faults(cert: dict, need: list[str], max_age_hours: float | None = None) -> list[str]:
    """What is wrong with a certificate in itself, whatever the code is now."""
    why = []
    if cert["changes"]:
        why.append("The run tested code with uncommitted changes: commit everything and run crissp/check-all.sh again.")
    if cert["changed_during_run"]:
        why.append("The code changed while the run went on: run crissp/check-all.sh again on a tree that stands still.")
    red = [k for k, v in cert["steps"].items() if v != "passed"]
    red += [f"{step} (did not run)" for step in need if step not in cert["steps"]]
    if red:
        why.append("Not green: " + ", ".join(red) + ".")
    if max_age_hours is not None and time.time() - cert["finished"] > max_age_hours * 3600:
        why.append(f"The last full run is older than {max_age_hours / 24:g} days: run crissp/check-all.sh.")
    return why


def _why(cert: dict, root: Path, max_age_hours: float) -> list[str]:
    why = _faults(cert, needed(root), max_age_hours)
    head = _head(root)
    if head != cert["commit"]:
        try:
            since = _code_since(cert["commit"], root)
        except subprocess.CalledProcessError:
            since = ["(the tested commit is not in this checkout any more)"]
        listed = ", ".join(since[:8]) + (" …" if len(since) > 8 else "") if since else "only the coverage baseline"
        why.append(f"HEAD ({head[:8]}) is not the tested commit {cert['commit'][:8]} (changed since: {listed}). "
                   "Run crissp/check.sh: it tests what changed and moves the certificate to this commit.")
    if _changes(root):
        why.append("There are uncommitted changes: what you deploy must be exactly what was tested.")
    return why


def check(root: Path | None = None, results: Path | None = None, max_age_hours: float = MAX_AGE_HOURS) -> list[str]:
    """Why this code may not be deployed; empty means it may. While a new full run goes on, or after one ended red, the
    last green certificate before it still stands for exactly its own commit (never for newer code)."""
    root, results = _where(root, results)
    cert = _load(results / "release.json")
    if cert is None:
        return ["No full run found: run crissp/check-all.sh on this code."]
    why = _why(cert, root, max_age_hours)
    previous = _load(results / "release-previous.json")
    if why and previous and not _why(previous, root, max_age_hours):
        return []
    return why


def advance(ran: dict, root: Path | None = None, results: Path | None = None) -> list[str]:
    """After crissp/check.sh ran its plan green: the certificate moves to HEAD. `ran` is the plan it carried out (impact.plan)
    plus {"passed": true}. Returns why not; empty means the certificate is now about HEAD."""
    root, results = _where(root, results)
    cert = _load(results / "release.json")
    if cert is None:
        return ["No full run to build on: run crissp/check-all.sh first."]
    if interrupted(cert, results):
        return [INTERRUPTED]
    why = []
    if cert["changes"] or cert["changed_during_run"]:
        why.append("The last full run was not valid (changes before or during the run): run crissp/check-all.sh.")
    red = [k for k, v in cert["steps"].items() if v != "passed"] + [n for n in needed(root) if n not in cert["steps"]]
    if red:
        why.append("The last full run was not green (" + ", ".join(red) + "): run crissp/check-all.sh.")
    if ran.get("full"):
        why.append("These changes touch shared ground, only a full run can vouch for them: " + "; ".join(ran["full"][:3]))
    if not ran.get("passed"):
        why.append("The targeted tests were not green.")
    planned = sorted(f for f in ran.get("files", []) if not f.startswith(GENERATED))
    if planned != sorted(_code_since(cert["commit"], root)):  # the plan was made for exactly these changes, nothing since
        why.append("The plan does not belong to the changes since the certificate: run crissp/check.sh again.")
    if _changes(root):
        why.append("There are uncommitted changes: commit them and run crissp/check.sh again.")
    if why:
        return why
    head = _head(root)
    cert.setdefault("increments", []).append({"from": cert["commit"], "to": head, "at": time.time(),
                                              "suites": ran.get("suites", []), "light": ran.get("light", []),
                                              "files": len(ran.get("files", []))})
    cert["commit"] = head
    (results / "release.json").write_text(json.dumps(cert, indent=2))
    return []


def _say(reasons: list[str], good: str, bad: str) -> int:
    for r in reasons:
        print(f"  - {r}")
    print(bad if reasons else good)
    return 1 if reasons else 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "start":
        start()
        return 0
    if cmd == "finish":
        finish()
        return 0
    if cmd == "advance" and len(argv) > 2:
        return _say(advance(json.loads(Path(argv[2]).read_text())), "Certificate moved: green for this commit.",
                    "Certificate not moved.")
    if cmd == "check":
        hours = float(argv[argv.index("--max-age-hours") + 1]) if "--max-age-hours" in argv else MAX_AGE_HOURS
        return _say(check(max_age_hours=hours), "Release gate: green for this commit.", "Release gate: not green.")
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover — run as a script by the check scripts; main() is tested
    sys.stdout, sys.stderr = project.Speaking(sys.stdout), project.Speaking(sys.stderr)  # F-04: the names a person can type
    sys.exit(main(sys.argv))
