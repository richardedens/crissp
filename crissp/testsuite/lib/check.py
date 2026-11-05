"""crissp/check.sh and crissp/check-all.sh: test what changed since the last green state, or everything.

    python3 crissp/testsuite/lib/check.py changed [--plan]   crissp/check.sh: the plan (lib/impact.py), and without
                                                             --plan run it; on green the release certificate moves to
                                                             this commit (deploy.sh asks for that)
    python3 crissp/testsuite/lib/check.py all                crissp/check-all.sh: the full run (every step), the
                                                             certificate (lib/release.py)

Exit codes: 0 green · 1 red (or setup could not install) · 2 refused (no commit, uncommitted changes, no full run yet,
not a git checkout) · 3 the changes touch shared ground: run crissp/check-all.sh · 4 another run holds the lock.

Commit first: both test what is committed (that is what gets deployed). One run at a time: a lock in
crissp/testsuite/results/.run.lock (the plan only reads, it takes none). Without git there are no commits to compare:
check.sh says so and stops; check-all.sh still runs every step for proof, but writes no certificate.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import impact  # noqa: E402
import project  # noqa: E402
import release  # noqa: E402

GENERATED = ":(exclude)crissp/testsuite/coverage-baseline.json"
NOT_GIT = ("Not a git checkout: crissp/check.sh tests what changed since the last green commit, and there are no commits "
           "here. Run git init and commit (crissp/check-all.sh runs every step without one, for proof).")
GREEN = "Green: crissp/deploy.sh may go."


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def is_checkout(root: Path) -> bool:
    top = git(root, "rev-parse", "--show-toplevel")
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve()


def uncommitted(root: Path) -> list[str]:
    return git(root, "status", "--short", "--untracked-files=no", "--", ".", GENERATED).stdout.splitlines()


class Lock:
    """One run at a time: two runs share crissp/testsuite/results and would break each other."""

    def __init__(self, results: Path, what: str) -> None:
        self.path, self.what = results / ".run.lock", what

    def take(self) -> str | None:
        """None when this run holds the lock now, or why not."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.mkdir()
        except FileExistsError:
            pid = (self.path / "pid").read_text().strip() if (self.path / "pid").is_file() else ""
            if pid.isdigit() and _alive(int(pid)):
                what = (self.path / "what").read_text().strip() if (self.path / "what").is_file() else "a run"
                since = (self.path / "since").read_text().strip() if (self.path / "since").is_file() else "?"
                return f"A run is already in progress ({what}, started {since}). Wait for it, or stop it first."
            # left behind by a run that was killed
        (self.path / "pid").write_text(str(os.getpid()))
        (self.path / "what").write_text(self.what)
        (self.path / "since").write_text(time.strftime("%H:%M"))
        return None

    def free(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


SCRIPTS = ENGINE.parent  # setup.sh and run.sh: the testsuite's own scripts, next to this engine


def script(name: str) -> str:
    return str(SCRIPTS / name)


def say_plan(p: dict, since: str, out) -> None:
    print(f"Since {since[:8]}: {len(p['files'])} changed file(s).", file=out)
    if not p["files"]:
        print("  Nothing changed since the last green state.", file=out)
    if p["full"]:
        print("  Needs the full run (crissp/check-all.sh), because:", file=out)
        for r in p["full"][:6]:
            print(f"    - {r}", file=out)
        return
    if p["nothing"]:
        print(f"  Notes only, nothing to test: {len(p['nothing'])} file(s)", file=out)
    if p["light"]:
        print("  Light checks: " + ", ".join(p["light"]), file=out)
    if p["suites"]:
        print("  Suites: " + ", ".join(p["suites"]), file=out)
    print(f"  About {p['minutes']} min.", file=out)


def changed(root: Path, plan_only: bool, run=subprocess.run, out=None, err=None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    results = project.results(root)
    if not is_checkout(root):
        print(NOT_GIT, file=err)
        return 2
    lock = Lock(results, "check.sh" + (" --plan" if plan_only else ""))
    if not plan_only:
        busy = lock.take()
        if busy:
            print(busy, file=err)
            return 4
    try:
        cert_file = results / "release.json"
        if not cert_file.is_file():
            print("No full run yet: start with crissp/check-all.sh.", file=err)
            return 2
        loose = uncommitted(root)
        if loose:
            print("Commit your changes first: crissp/check.sh tests what is committed (that is what gets deployed).", file=err)
            print("\n".join(loose[:10]), file=err)
            return 2
        if not plan_only and run([script("setup.sh")], cwd=root).returncode != 0:
            return 1
        since = json.loads(cert_file.read_text())["commit"]
        try:
            p = impact.plan(impact.changed_since(since, root), project.load(root), root)
        except (subprocess.CalledProcessError, project.ConfigError) as e:
            print(f"The plan could not be made: {getattr(e, 'stderr', '') or e}".strip(), file=err)
            return 2
        say_plan(p, since, out)
        if p["full"]:
            return 3
        if plan_only:
            return 0
        ok = True
        for check in p["light"]:  # the one light check: the release notes
            problems = impact.check_release_notes(root)
            print(f"▸ {'Release notes (VERSION, CHANGELOG.md)':<44}" + ("FAILED" if problems else "passed"), file=out)
            for line in problems:
                print(f"  - {line}", file=out)
            ok = ok and not problems
        if p["suites"]:
            out.flush()
            ok = run([script("run.sh"), "--quick", *p["suites"]], cwd=root).returncode == 0 and ok
            gate_log = results / "gate.log"
            if gate_log.is_file() and "coverage gate: RED" in gate_log.read_text():
                for line in [x for x in gate_log.read_text().splitlines() if x.startswith("✗")][:40]:
                    print(line, file=out)
        if not ok:
            print("Not green: fix what failed above (logs in crissp/testsuite/results), commit, and run crissp/check.sh "
                  "again.", file=out)
            return 1
        why = release.advance({**p, "passed": True}, root, results)
        for line in why:
            print(f"  - {line}", file=out)
        print("Certificate not moved." if why else f"Certificate moved: green for this commit.\n{GREEN}", file=out)
        return 1 if why else 0
    finally:
        if not plan_only:
            lock.free()


def everything(root: Path, run=subprocess.run, out=None, err=None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    results = project.results(root)
    lock = Lock(results, "check-all.sh")
    busy = lock.take()
    if busy:
        print(busy, file=err)
        return 4
    try:
        if not is_checkout(root):
            print("Not a git checkout: this run proves the tree as it is, but writes no release certificate (run git init "
                  "and commit for one).", file=err)
            if run([script("setup.sh")], cwd=root).returncode != 0:
                return 1
            status = run([script("run.sh")], cwd=root).returncode
            print("Every step passed (no certificate: not a git checkout)." if status == 0
                  else "Not green: fix what failed above (logs in crissp/testsuite/results).", file=out)
            return status
        if git(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0:
            print("No commit yet: commit first. The run is only valid for committed code (that is what gets deployed).",
                  file=err)
            return 2
        loose = uncommitted(root)
        if loose:
            print("Commit your changes first: the run is only valid for committed code (that is what gets deployed).", file=err)
            print("\n".join(loose[:10]), file=err)
            return 2
        if run([script("setup.sh")], cwd=root).returncode != 0:
            return 1
        release.start(root, results)
        out.flush()
        status = run([script("run.sh")], cwd=root).returncode
        release.finish(root, results)
        print(file=out)
        why = release.check(root, results)
        for line in why:
            print(f"  - {line}", file=out)
        if why:
            print("Release gate: not green.", file=out)
            print("Not green: fix what failed above (logs in crissp/testsuite/results), commit, and run crissp/check-all.sh "
                  "again.", file=out)
        else:
            print(f"Release gate: green for this commit.\n{GREEN}", file=out)
            state = git(root, "status", "--porcelain", "--", "crissp/testsuite/coverage-baseline.json").stdout
            if state.startswith("??"):  # F-06: a new project's first full run wrote the baseline; say what is left, plainly
                print("This was the first full run: it wrote the coverage baseline. Commit it, then crissp/check.sh moves "
                      "the certificate to that commit:\n  git add crissp/testsuite/coverage-baseline.json && git commit -m "
                      "\"Coverage baseline\" && crissp/check.sh", file=out)
            elif state.strip():
                print("The coverage baseline went up: commit crissp/testsuite/coverage-baseline.json (crissp/check.sh then "
                      "moves the certificate to that commit).", file=out)
        return status
    finally:
        lock.free()


def main(argv: list[str], root: Path | None = None) -> int:
    root = root or project.root()
    args = argv[1:]
    if args[:1] == ["all"] and len(args) == 1:
        return everything(root)
    if args[:1] == ["changed"] and args[1:] in ([], ["--plan"]):
        return changed(root, args[1:] == ["--plan"])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover — run by crissp/check.sh and check-all.sh; main() is tested
    sys.stdout, sys.stderr = project.Speaking(sys.stdout), project.Speaking(sys.stderr)  # F-04: the names a person can type
    sys.exit(main(sys.argv))
