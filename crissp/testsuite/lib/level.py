"""What crissp repair needs to bring a project level with the template (F-160 to F-162), next to repair.py.

- suites    suites.json lacks steps, path rules, shared ground or the audit block the template has (F-160): a missing
            step whose part is here is added (its path rules too); one whose part is not here is said, as is a step
            the project has under its own name (the same `run`: not missing)
- pins      tracked files still name an older `crissp==<version>` than the crissp that repairs (F-161): deploy
            scripts, a README, the agreement, deploy settings. Each one moves to this crissp and is listed; the
            history (CHANGELOG.md, crissp/backlog/, crissp/testsuite/changes.json) is left as it was, and .mcp.json and
            .vibe/config.toml have repairs of their own
- overlaps  the project runs a scan of its own that a crissp step already runs (F-162): bandit (backend-lint runs
            ruff's S rules, the same checks), gitleaks (the secrets step scans the whole history, which a scan of the
            tree misses) or Grype (the audit step scans the same images with trivy): said, with one recommended,
            never changed

Nothing here writes: repair.py does, with --yes. Standard library only.
"""

import re
import subprocess
from pathlib import Path

PIN = re.compile(r"crissp==(\d+(?:\.\d+)*)((?:\.?(?:a|b|rc|dev|post)\d*)*)")
HISTORY = ("CHANGELOG.md", "crissp/backlog/", "crissp/testsuite/changes.json")
OWN_REPAIR = (".mcp.json", ".vibe/config.toml")  # fix_pin and fix_vibe_pin
BIG = 1_000_000  # bytes: a file this large is no script or settings file


def tracked(root: Path) -> list[str]:
    """The files git tracks in the project; none without git."""
    try:
        done = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    except OSError:  # no git at all
        return []
    return sorted(p for p in done.stdout.decode(errors="replace").split("\0") if p) if done.returncode == 0 else []


def text_of(path: Path) -> str | None:
    """A small text file's text; None for a large, binary or unreadable one."""
    try:
        if not path.is_file() or path.stat().st_size > BIG:
            return None
        return path.read_bytes().decode()
    except (OSError, UnicodeDecodeError):
        return None


# --- suites: the template's steps, path rules, shared ground and audit block ---


def suites(root: Path, data: dict, template: dict) -> tuple[dict | None, list[str], list[str]]:
    """(the suites.json to write, or None when nothing is added; what is added; what needs a person)."""
    steps = data.get("steps") or []
    have = {s.get("key") for s in steps}
    runs = {s.get("run") for s in steps}
    added, said = [], []
    for step in template.get("steps", []):
        if step["key"] in have or step.get("run") in runs:
            continue
        part = step.get("when")
        if part is None or (root / part).exists():
            added.append(step)
        else:
            said.append(
                f"suites.json has no {step['key']} step ({step['label'].removeprefix('CRISSP: ')}): its part "
                f"{part} is not here; add one for the folder your project keeps it in (`run`: {step['run']})"
            )
    keys = have | {s["key"] for s in added}
    paths = [dict(r, steps=list(r.get("steps", []))) for r in data.get("paths", [])]
    for rule in template.get("paths", []):
        new = [k for k in rule["steps"] if k in {s["key"] for s in added}]
        if not new:
            continue
        own = next((r for r in paths if r.get("match") == rule["match"]), None)
        if own is None:
            paths.append({"match": rule["match"], "steps": [k for k in rule["steps"] if k in keys]})
        else:
            own["steps"] += [k for k in new if k not in own["steps"]]
    shared = data.get("shared", [])
    more = [r for r in template.get("shared", []) if r["match"] not in {s.get("match") for s in shared}]
    audit = "audit" not in data and "audit" in template
    what = []
    if added:
        what.append(f"the template's steps {', '.join(s['key'] for s in added)} (their parts are here)")
    if audit:
        what.append("its audit block (what the audit step scans; a place that is not there is skipped)")
    if more:
        what.append(f"its shared ground {', '.join(r['match'] for r in more)}")
    if not what:
        return None, [], said
    out = {**data, "steps": steps + added, "paths": paths, "shared": shared + more}
    if audit:
        out["audit"] = template["audit"]
    return out, what, said


# --- pins: every crissp==<old> in the tracked files ---


def key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def stale_pins(root: Path, version: str) -> dict[str, list[str]]:
    """Each tracked file that names an older crissp than version (outside the history), with the pins it names."""
    try:
        now = key(PIN.fullmatch(f"crissp=={version}").group(1))
    except AttributeError:  # not a version crissp could pin
        return {}
    found = {}
    for rel in tracked(root):
        if rel.startswith(HISTORY) or rel in OWN_REPAIR:
            continue
        text = text_of(root / rel)
        old = sorted({m.group(0) for m in PIN.finditer(text or "") if key(m.group(1)) < now})
        if old:
            found[rel] = old
    return found


def move_pins(root: Path, found: dict[str, list[str]], version: str) -> None:
    """The older pins found move to version; nothing else in a file changes."""
    for rel, old in found.items():
        path = root / rel
        stale = set(old)
        path.write_text(
            PIN.sub(
                lambda m, stale=stale: f"crissp=={version}" if m.group(0) in stale else m.group(0), path.read_text()
            )
        )


# --- overlaps: a project's own scans next to crissp's ---

# where a project runs its tools: CI, pre-commit, task runners, scripts, its dependency lists
RUNS = re.compile(
    r"(^|/)(\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.yml|\.pre-commit-config\.ya?ml|Makefile|Justfile|"
    r"Taskfile\.ya?ml|Jenkinsfile|azure-pipelines\.ya?ml|bitbucket-pipelines\.yml|tox\.ini|noxfile\.py|setup\.cfg|"
    r"pyproject\.toml|package\.json|requirements[^/]*\.txt|[^/]+\.sh|\.bandit)$"
)
BANDIT = re.compile(r"\bbandit\b")
TREE = re.compile(r"gitleaks\s+(dir\b|protect\b(?![^\n]*--staged)|detect\b[^\n]*--no-git)")
HISTORY_SCAN = re.compile(r"gitleaks/gitleaks-action|gitleaks\s+(git\b(?![^\n]*--staged)|detect\b(?![^\n]*--no-git))")
GRYPE = re.compile(r"\bgrype\b|anchore/scan-action")


def overlaps(root: Path) -> list[str]:
    """What the project's own scans do again of what crissp's steps do, with the one to keep."""
    hits: dict[str, list[str]] = {"bandit": [], "tree": [], "history": [], "grype": []}
    for rel in tracked(root):
        if rel.startswith("crissp/") or not RUNS.search(rel):
            continue
        text = text_of(root / rel) or ""
        for name, pattern in (("bandit", BANDIT), ("tree", TREE), ("history", HISTORY_SCAN), ("grype", GRYPE)):
            if pattern.search(text) or (name == "bandit" and rel.endswith(".bandit")):
                hits[name].append(rel)
    out = []
    if hits["bandit"]:
        out.append(
            f"bandit ({', '.join(hits['bandit'])}) and crissp's backend-lint run the same checks: ruff's S rules are "
            "bandit's. Recommended: keep ruff S (one tool and one configuration, much faster) and drop bandit"
        )
    if hits["tree"]:
        out.append(
            f"gitleaks on the files ({', '.join(hits['tree'])}) and crissp's secrets step: the step scans the whole "
            "git history, which also finds a secret committed once and deleted later. Recommended: keep the secrets "
            "step and drop the scan of the files (a pre-commit `gitleaks git --staged` can stay: it stops a secret "
            "before it lands)"
        )
    if hits["history"]:
        out.append(
            f"gitleaks on the history ({', '.join(hits['history'])}) and crissp's secrets step scan the same "
            "commits. Recommended: keep one; crissp's is pinned and reads your .gitleaks.toml and .gitleaksignore"
        )
    if hits["grype"]:
        out.append(
            f"Grype ({', '.join(hits['grype'])}) and crissp's audit step scan the same images (trivy). Recommended: "
            "keep trivy (pinned and checksum-checked, and it also checks the Dockerfiles and the chart) and drop "
            "Grype; or keep Grype and set audit.images to [] in crissp/testsuite/suites.json"
        )
    return out
