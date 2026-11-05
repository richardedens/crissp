"""Where the UX suite keeps things, and its configuration: who the team is, what the product is, which walks they take.

The configuration is crissp/uxsuite/team.json and one file per walk in crissp/uxsuite/walks/; everything the suite
makes (screenshots, rounds, proposals, the queue, the verdicts) goes to crissp/uxsuite/results/, which git ignores.
load() checks the configuration and says exactly what is wrong, so a typo never becomes a confusing run.

team.json
    product          the product's name (required)
    monogram         one or two letters for the top bar (default: the product's first letter)
    about            what the product is and what people do with it
    audience         who uses it
    ui_language      the language of the product's own texts (default English)
    report_language  the language the team reports in (default English)
    url              where the running product is, e.g. http://127.0.0.1:5173 (required)
    rounds           debate rounds after the first look, 1-5 (default 2)
    parallel         how many runs at once, at least 1 (default 3; UXSUITE_PARALLEL overrides it)
    backlog          {"epic": "E<n>"} or {"epic_title": "..."}: where approved designs become PBIs
    personas         [{key, name, role, device: desktop|mobile|both, moderator: bool, brief}], one moderator at least
walks/<id>.json
    title            what the walk is about
    steps            [{do: goto (path) | click (text or selector) | fill (selector, value) | press (key) | wait (ms)
                       | shot (title)}], at least one shot
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "testsuite" / "lib"))  # the guards' shared module: how a message names the doors
from project import Speaking, speak  # noqa: E402,F401 — F-04: `crissp ux --shoot` when run as the crissp command
DEVICES = ("desktop", "mobile", "both")
NEEDS = {"goto": ("path",), "click": (), "fill": ("selector", "value"), "press": ("key",), "wait": ("ms",), "shot": ("title",)}
WALK_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


class ConfigError(ValueError):
    """The configuration is wrong; the message says where and what."""


def project_root(env=None) -> Path:
    """The project the suite works for: CRISSP_ROOT, or the current directory (the scripts export CRISSP_ROOT). Never
    this file's own place: the engine and the project's data may live apart."""
    env = os.environ if env is None else env
    return Path(env.get("CRISSP_ROOT") or os.getcwd()).resolve()


class Suite:
    """The places of one repository's UX suite: its configuration, its results, the check runs' lock."""

    def __init__(self, root: Path, here: Path | None = None) -> None:
        self.root = Path(root)
        self.here = here or self.root / "crissp" / "uxsuite"
        self.results = self.here / "results"
        self.lock = self.root / "crissp" / "testsuite" / "results" / ".run.lock"


def default_suite() -> Suite:
    """The suite of the project this process works for (project_root)."""
    return Suite(project_root())


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except OSError:
        raise ConfigError(f"{path.name} is missing") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path.name} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must hold one JSON object")
    return data


def _text(data: dict, key: str, where: str, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} must be a text" + ("" if default is None else " (or left out)"))
    return value.strip()


def _whole(data: dict, key: str, where: str, default: int, low: int, high: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ConfigError(f"{where}: {key} must be a whole number from {low} to {high}")
    return value


def personas(data: dict) -> list[dict]:
    listed = data.get("personas")
    if not isinstance(listed, list) or not listed:
        raise ConfigError("team.json: personas must be a list with at least one persona")
    out, keys = [], set()
    for i, p in enumerate(listed, 1):
        where = f"team.json: persona {i}"
        if not isinstance(p, dict):
            raise ConfigError(f"{where} must be an object")
        key = _text(p, "key", where)
        if not WALK_ID.fullmatch(key) or key in keys:
            raise ConfigError(f"{where}: key {key!r} must be unique, lower case letters, digits and -")
        keys.add(key)
        device = p.get("device", "desktop")
        if device not in DEVICES:
            raise ConfigError(f"{where}: device must be one of {', '.join(DEVICES)}")
        out.append({"key": key, "name": _text(p, "name", where), "role": _text(p, "role", where), "device": device,
                    "moderator": p.get("moderator") is True, "brief": _text(p, "brief", where)})
    if not any(p["moderator"] for p in out):
        raise ConfigError("team.json: one persona must be the moderator (\"moderator\": true)")
    return out


def walk(path: Path) -> dict:
    """One walk: its id (the file name), title and steps, checked."""
    where = f"walks/{path.name}"
    if not WALK_ID.fullmatch(path.stem):
        raise ConfigError(f"{where}: the file name must be lower case letters, digits and - (it is the walk's id)")
    data = _read(path)
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ConfigError(f"{where}: steps must be a list with at least one step")
    for n, step in enumerate(steps, 1):
        do = step.get("do") if isinstance(step, dict) else None
        if do not in NEEDS:
            raise ConfigError(f"{where}: step {n}: do must be one of {', '.join(NEEDS)}")
        missing = [k for k in NEEDS[do] if k not in step]
        if do == "click" and not ("text" in step or "selector" in step):
            missing = ["text or selector"]
        if missing:
            raise ConfigError(f"{where}: step {n} ({do}) needs {', '.join(missing)}")
    if not any(s["do"] == "shot" for s in steps):
        raise ConfigError(f"{where}: a walk needs at least one shot step (that is what the team looks at)")
    return {"id": path.stem, "title": _text(data, "title", where), "steps": steps}


def load(suite: Suite) -> dict:
    """The whole configuration, checked: team.json with defaults filled in, and every walk by id."""
    data = _read(suite.here / "team.json")
    product = _text(data, "product", "team.json")
    url = _text(data, "url", "team.json")
    if not re.match(r"https?://", url):
        raise ConfigError("team.json: url must start with http:// or https://")
    backlog = data.get("backlog", {})
    if not isinstance(backlog, dict) or ("epic" in backlog and not re.fullmatch(r"E\d+", str(backlog["epic"]))):
        raise ConfigError('team.json: backlog must be {"epic": "E<n>"} or {"epic_title": "..."}')
    walks = [walk(p) for p in sorted((suite.here / "walks").glob("*.json"))]
    return {"product": product, "monogram": _text(data, "monogram", "team.json", product[:1].upper()),
            "about": str(data.get("about", "")).strip(), "audience": str(data.get("audience", "")).strip(),
            "ui_language": _text(data, "ui_language", "team.json", "English"),
            "report_language": _text(data, "report_language", "team.json", "English"), "url": url.rstrip("/"),
            "rounds": _whole(data, "rounds", "team.json", 2, 1, 5),
            "parallel": _whole(data, "parallel", "team.json", 3, 1, 12),
            "backlog": {"epic": backlog.get("epic"), "epic_title": str(backlog.get("epic_title") or "UX: approved designs")},
            "personas": personas(data), "walks": {w["id"]: w for w in walks}}
