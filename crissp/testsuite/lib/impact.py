"""What a change touches, and which steps prove it still works (crissp/check.sh).

Every changed file is sorted into one of these, in this order (the first that matches decides):
- shared ground: the full run, crissp/check-all.sh. What decides what is green (the check, run and setup scripts, the
  gate, the certificate, this map, the step runner), the pinned test tools, the project's configuration itself
  (crissp/testsuite/suites.json), .gitignore, and the product's own shared ground (suites.json `shared`: what goes into
  an image, the dependency and build files)
- a light check: the release notes (CHANGELOG.md and VERSION): `release-notes` below, seconds
- nothing to test: notes (the backlog, docs/, every Markdown file), the coverage baseline the run raises itself, and
  what the project lists in suites.json `notes`
- a part of the product: the steps suites.json `paths` names for it; a step the coverage gate holds brings the gate
- anything else: shared ground too, because a targeted run cannot vouch for a file no rule names. When in doubt the
  full run is the honest answer.

A rule is an exact path, a folder ("…/"), or a file name anywhere ("*/name").

    python3 crissp/testsuite/lib/impact.py plan [<since-commit>]   the plan as JSON (default: since the release certificate)
    python3 crissp/testsuite/lib/impact.py release-notes           check VERSION and the top of CHANGELOG.md
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402

# Shared ground of every C.R.I.S.S.P. project: (match, why). The deploy is not here: a project maps it to its own step.
FULL = [
    (".gitignore", "what git keeps (and what a fresh checkout has)"),
    ("crissp/testsuite/suites.json", "the product's parts: what every run and this map are made of"),
    ("crissp/testsuite/requirements.txt", "the pinned test tools"),
    ("crissp/check.sh", "the tool that decides what a change needs"),
    ("crissp/check-all.sh", "the full run itself"),
    ("crissp/test.sh", "how the dashboard is built and served"),
    ("crissp/testsuite/run.sh", "the steps every run is made of"),
    ("crissp/testsuite/setup.sh", "how the test tools are installed"),
    ("crissp/testsuite/lib/run.py", "the steps every run is made of"),
    ("crissp/testsuite/lib/steps.sh", "what every step's command can use"),
    ("crissp/testsuite/lib/project.py", "how the product's parts are read"),
    ("crissp/testsuite/lib/check.py", "the tool that decides what a change needs"),
    ("crissp/testsuite/lib/impact.py", "this map"),
    ("crissp/testsuite/lib/release.py", "the release certificate"),
    ("crissp/testsuite/lib/gate.py", "the coverage gate"),
]
NOTHING = ("crissp/backlog/", "docs/", "crissp/testsuite/coverage-baseline.json")
LIGHT = {"CHANGELOG.md": "release-notes", "VERSION": "release-notes"}


def _matches(path: str, rule: str) -> bool:
    if rule.startswith("*/"):
        return path == rule[2:] or path.endswith(rule[1:])
    return path == rule or (rule.endswith("/") and path.startswith(rule))


def classify(path: str, conf: dict) -> tuple[str, object]:
    """(kind, detail): ("nothing", "") | ("light", check) | ("suites", (step, …)) | ("full", reason)."""
    for rule, why in FULL + [(r["match"], r["why"]) for r in conf["shared"]]:
        if _matches(path, rule):
            return "full", f"{path}: {why}"
    if path in LIGHT:
        return "light", LIGHT[path]
    if path.startswith(NOTHING) or path.endswith(".md") or any(_matches(path, n) for n in conf["notes"]):
        return "nothing", ""
    for rule in conf["paths"]:
        if _matches(path, rule["match"]):
            return "suites", tuple(rule["steps"])
    return "full", f"{path}: not mapped to a part of {conf['product']} (crissp/testsuite/suites.json, paths)"


def plan(files: list[str], conf: dict, root: Path) -> dict:
    """What to run for these changed files."""
    out: dict = {"files": files, "nothing": [], "full": [], "light": [], "suites": [], "minutes": 0}
    light, suites = set(), set()
    for f in files:
        kind, detail = classify(f, conf)
        if kind == "nothing":
            out["nothing"].append(f)
        elif kind == "light":
            light.add(detail)
        elif kind == "suites":
            suites.update(detail)
        else:
            out["full"].append(detail)
    every = project.steps(conf, root)
    if any(s["gate"] and s["key"] in suites for s in every):
        suites.add(project.GATE)  # a gated part's coverage is held by the gate
    absent = sorted(k for k in suites if k not in {s["key"] for s in every})
    out["full"] += [f"step {k}: named in suites.json but not there now (its `when` is missing)" for k in absent]
    chosen = [s for s in every if s["key"] in suites]
    out["light"] = sorted(light)
    out["suites"] = [s["key"] for s in chosen]
    out["minutes"] = math.ceil((sum(s["seconds"] for s in chosen) + 2 * len(light)) / 60)
    return out


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def changed_since(commit: str, root: Path) -> list[str]:
    """Files changed in the commits since `commit` (crissp/check.sh only runs on a clean tree, so that is everything)."""
    return [f for f in _git(root, "diff", "--name-only", f"{commit}..HEAD").splitlines() if f]


SEMVER = re.compile(r"\d+\.\d+\.\d+")


def check_release_notes(root: Path) -> list[str]:
    """VERSION is a version (1.2.3); CHANGELOG.md's top section names it and says at least one thing (a bullet)."""
    why = []
    try:
        version = (root / "VERSION").read_text().strip()
    except OSError:
        return ["VERSION is missing (it holds the current version, e.g. 0.1.0)"]
    if not SEMVER.fullmatch(version):
        why.append(f"VERSION: {version!r} is not a version like 0.1.0")
    try:
        log = (root / "CHANGELOG.md").read_text()
    except OSError:
        return why + ["CHANGELOG.md is missing (its top section is the release notes of VERSION)"]
    sections = re.split(r"^## ", log, flags=re.M)[1:]
    if not sections:
        return why + ["CHANGELOG.md has no section (## <version> — <date or unreleased>)"]
    title, _, body = sections[0].partition("\n")
    named = SEMVER.match(title.strip())
    if not named or named.group(0) != version:
        why.append(f"CHANGELOG.md: the top section is {title.strip()!r}, it should name the version in VERSION ({version})")
    if not re.search(r"^\s*[-*] \S", body, re.M):
        why.append(f"CHANGELOG.md: the top section ({title.strip()}) has no bullet: say what changed")
    return why


def main(argv: list[str], root: Path | None = None) -> int:
    root = root or project.root()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "plan":
        since = argv[2] if len(argv) > 2 else json.loads((project.results(root) / "release.json").read_text())["commit"]
        print(json.dumps(plan(changed_since(since, root), project.load(root), root), indent=1))
        return 0
    if cmd == "release-notes":
        problems = check_release_notes(root)
        print("\n".join(f"  - {p}" for p in problems) or "release notes: ok")
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover — run as a script by crissp/check.sh; main() is tested
    sys.exit(main(sys.argv))
