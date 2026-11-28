"""The lint ratchet (F-152): a project that already has code switches its lint on, and the findings only go down.

    crissp/testsuite/lint-baseline.json     committed, like coverage-baseline.json: per lint folder (app/frontend), per
                                            file its sha256 and how many findings of each rule it had

    python3 crissp/testsuite/lib/frontend_lint.py --baseline [<folder>]
                                            write the folder's baseline from what the lint finds now: once, to switch the
                                            lint on; a folder that has one already is refused (it only shrinks)

Rules, once a folder has a baseline:
- A file the baseline names, unchanged (the same sha256), may keep up to its count of each rule; one more is red.
- A new file, or a changed one, has no findings at all: what is written or touched now is clean.
- A green run that finds fewer shrinks the baseline (a file with none left, or gone, leaves it). It never grows.
- A run of some files only (the pre-commit hook: the staged ones) judges those and leaves the baseline as it is.
Without a baseline every finding is red, as before.
"""

import hashlib
import json
import subprocess
from pathlib import Path

BASELINE = "crissp/testsuite/lint-baseline.json"
COMMENT = (
    "The lint ratchet (lib/lint_ratchet.py): per lint folder, per file its sha256 and its findings per rule. "
    "Findings only go down: a changed or new file is clean. Written by frontend_lint.py --baseline, shrunk by green runs."
)


def root_of(folder: Path, env: dict) -> Path:
    """The project: CRISSP_ROOT (a run and the hook set it), else the folder's git repository, else the folder."""
    if env.get("CRISSP_ROOT"):
        return Path(env["CRISSP_ROOT"]).resolve()
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=folder, capture_output=True, text=True, check=False
    )
    return Path(done.stdout.strip()).resolve() if done.returncode == 0 else folder.resolve()


def key_of(folder: Path, root: Path) -> str:
    """The folder's name in the baseline: its path in the project."""
    try:
        return folder.resolve().relative_to(root).as_posix() or "."
    except ValueError:
        return folder.resolve().as_posix()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def load(root: Path) -> dict:
    path = root / BASELINE
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("folders", {}) if isinstance(data, dict) else {}


def save(root: Path, folders: dict) -> None:
    path = root / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"$comment": COMMENT, "folders": {k: folders[k] for k in sorted(folders)}}
    path.write_text(json.dumps(body, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def counts(findings: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in findings:
        rules = out.setdefault(f["file"], {})
        rules[f["rule"]] = rules.get(f["rule"], 0) + 1
    return out


def baseline_of(folder: Path, findings: list[dict]) -> dict:
    """A folder's baseline from what was found now."""
    return {
        "files": {
            file: {"sha256": digest(folder / file), "rules": dict(sorted(rules.items()))}
            for file, rules in sorted(counts(findings).items())
        }
    }


def judge(
    folder: Path, findings: list[dict], known: dict | None, complete: bool
) -> tuple[list[dict], int, dict | None]:
    """What blocks, how many findings the baseline still allows, and the shrunk baseline (None: leave it as it is).

    Each blocking finding gets `why`. complete: every file of the folder was linted (not only the staged ones)."""
    if known is None:
        return [{**f, "why": ""} for f in findings], 0, None
    files = known.get("files", {})
    blocking, allowed, kept = [], 0, {}
    found = counts(findings)
    for file, rules in found.items():
        was = files.get(file)
        mine = [f for f in findings if f["file"] == file]
        if was is None or was.get("sha256") != digest(folder / file):
            why = "a new file is clean" if was is None else "a changed file is clean"
            blocking += [{**f, "why": why} for f in mine]
            continue
        for rule, n in rules.items():
            limit = was.get("rules", {}).get(rule, 0)
            if n > limit:
                blocking += [
                    {**f, "why": f"{n} of {rule}, the baseline allows {limit}"} for f in mine if f["rule"] == rule
                ]
            else:
                allowed += n
        shrunk = {rule: n for rule, n in rules.items() if n <= was.get("rules", {}).get(rule, 0)}
        if shrunk:
            kept[file] = {"sha256": was["sha256"], "rules": dict(sorted(shrunk.items()))}
    if blocking or not complete:
        return blocking, allowed, None
    tighter = {"files": dict(sorted(kept.items()))}
    return [], allowed, (tighter if tighter != known else None)
