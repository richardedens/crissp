"""The team and the rules as files the project owns: one Markdown file per persona (crissp/uxsuite/personas/<key>.md) and
per rule (crissp/uxsuite/rules/<id>.md), read and checked here with clear errors, and written by the page (api.py).

A persona file:                              A rule file:
    ---                                          ---
    name: Sam                                    title: Prices before commitment
    role: software engineer, 34                  severity: must            (must · should · could; default should)
    device: desktop    (desktop · mobile · both) on: true                  (false: the team leaves it out)
    moderator: false                             ---
    on: true           (false: takes no part)    A person sees what it costs before they commit.
    ---
    You are Sam, … (the brief: who they are and what they notice)

    ## Jobs
    - Find why a run is red   (what they come to do: discovery asks whether they can)

Older projects keep their personas in team.json and their rules as the `## ` sections of PRINCIPLES.md: those are read
as they are until the page writes the first persona or rule. That write moves them all into files first (team.json
loses its "personas", PRINCIPLES.md keeps its introduction and says where the rules are now), so there is always one
place for each. Nothing is ever deleted except the one file the product owner removes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ux_config import DEVICES, WALK_ID, ConfigError
from ux_config import personas as team_json_personas

SEVERITIES = ("must", "should", "could")
PERSONA_FIELDS = {"name", "role", "device", "moderator", "on", "order"}
RULE_FIELDS = {"title", "severity", "on", "measure"}
MEASURES = ("overflow", "tap-targets", "below-fold", "dialog-opaque", "focus-visible")  # what measure.js checks
MEASURED = re.compile(r"^Measured by the browser:\s*(.+?)\.?\s*$", re.MULTILINE)
JOBS = re.compile(r"^## Jobs\s*$", re.MULTILINE)
SECTION = re.compile(r"^## (?:(\d+)\.\s*)?(.+?)\s*$", re.MULTILINE)
MOVED = (
    "The rules themselves are in `rules/`, one file each: the UX suite's Rules tab adds, edits and switches them off.\n"
)


def _slug(text: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))[:48].strip("-")


# ------------------------------------------------------------------------------------------------------- the files


def split(text: str, where: str, fields: set[str], hint: str) -> tuple[dict, str]:
    """The --- block's fields (true and false as booleans) and the text under it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ConfigError(f"{where}: it must start with a --- block ({hint})")
    end = next((n for n in range(1, len(lines)) if lines[n].strip() == "---"), None)
    if end is None:
        raise ConfigError(f"{where}: the --- block is not closed")
    meta: dict = {}
    for n in range(1, end):
        line = lines[n]
        if not line.strip():
            continue
        if ":" not in line:
            raise ConfigError(f"{where}: line {n + 1} must be key: value")
        k, v = (x.strip() for x in line.split(":", 1))
        if k not in fields:
            raise ConfigError(f"{where}: unknown field {k} (known: {', '.join(sorted(fields))})")
        meta[k] = {"true": True, "false": False}.get(v.lower(), v)
    return meta, "\n".join(lines[end + 1 :]).strip()


def join(meta: dict, body: str) -> str:
    head = "\n".join(f"{k}: {str(v).lower() if isinstance(v, bool) else v}" for k, v in meta.items())
    return f"---\n{head}\n---\n{body.strip()}\n"


def _flag(value, where: str, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{where}: {name} must be true or false")
    return value


def _line(value, where: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {name} must be a text")
    if "\n" in value.strip():
        raise ConfigError(f"{where}: {name} must be one line")
    return value.strip()


def _key(value: str, where: str, what: str) -> str:
    if not WALK_ID.fullmatch(value):
        raise ConfigError(
            f"{where}: key {value!r} must be lower case letters, digits and - (it names the {what}'s file)"
        )
    return value


# ------------------------------------------------------------------------------------------------------- personas


def persona(key: str, meta: dict, body: str, where: str) -> dict:
    """One persona, checked: its fields, the brief, and its jobs (the `- ` lines under ## Jobs)."""
    device = meta.get("device", "desktop")
    if device not in DEVICES:
        raise ConfigError(f"{where}: device must be one of {', '.join(DEVICES)}")
    found = JOBS.search(body)
    brief = (body[: found.start()] if found else body).strip()
    jobs = [x[1:].strip() for x in body[found.end() :].splitlines() if x.strip().startswith("-")] if found else []
    if not brief:
        raise ConfigError(f"{where}: the brief (the text under the --- block) is empty")
    return {
        "key": key,
        "name": _line(meta.get("name"), where, "name"),
        "role": _line(meta.get("role"), where, "role"),
        "device": device,
        "moderator": _flag(meta.get("moderator"), where, "moderator", False),
        "on": _flag(meta.get("on"), where, "on", True),
        "brief": brief,
        "jobs": [j for j in jobs if j],
    }


def read_persona(path: Path) -> dict:
    where = f"personas/{path.name}"
    if not WALK_ID.fullmatch(path.stem):
        raise ConfigError(f"{where}: the file name must be lower case letters, digits and - (it is the persona's key)")
    meta, body = split(path.read_text(), where, PERSONA_FIELDS, "name, role, device …")
    return persona(path.stem, meta, body, where)


def persona_text(p: dict, order: int) -> str:
    jobs = "\n\n## Jobs\n\n" + "\n".join(f"- {j}" for j in p["jobs"]) if p["jobs"] else ""
    meta = {
        "name": p["name"],
        "role": p["role"],
        "device": p["device"],
        "moderator": p["moderator"],
        "on": p["on"],
        "order": order,
    }
    return join(meta, p["brief"] + jobs)


def check_team(team: list[dict], where: str) -> list[dict]:
    if not any(p["on"] and p["moderator"] for p in team):
        raise ConfigError(f"{where}: one persona that is on must be the moderator (moderator: true)")
    return team


def _from_team_json(data: dict) -> list[dict]:
    out = team_json_personas(data)
    for n, (p, raw) in enumerate(zip(out, data["personas"], strict=True), 1):
        where = f"team.json: persona {n}"
        jobs = raw.get("jobs", [])
        if not isinstance(jobs, list) or not all(isinstance(j, str) for j in jobs):
            raise ConfigError(f"{where}: jobs must be a list of texts")
        p.update(on=_flag(raw.get("on"), where, "on", True), jobs=[j.strip() for j in jobs if j.strip()])
    return out


def team(here: Path, data: dict) -> tuple[list[dict], str]:
    """The team and where it comes from: the persona files when there are any, else team.json's personas."""
    files = sorted((here / "personas").glob("*.md"), key=lambda f: (_order(f), f.name))
    if files:
        return check_team([read_persona(f) for f in files], "personas/"), "files"
    return check_team(_from_team_json(data), "team.json"), "team.json"


def _order(path: Path) -> int:
    """Where a persona stands in the team (its order: field; a file without one goes last, by name)."""
    try:
        return int(split(path.read_text(), "", PERSONA_FIELDS, "")[0].get("order", 10**6))
    except (ConfigError, ValueError):
        return 10**6  # read_persona names what is wrong with it


def _team_json(suite) -> dict:
    return json.loads((suite.here / "team.json").read_text())


def _personas_to_files(suite) -> None:
    """The first write from the page: team.json's personas become files, and team.json holds them no longer."""
    if (suite.here / "personas").is_dir() and any((suite.here / "personas").glob("*.md")):
        return
    data = _team_json(suite)
    (suite.here / "personas").mkdir(exist_ok=True)
    for n, p in enumerate(_from_team_json(data), 1):
        (suite.here / "personas" / f"{p['key']}.md").write_text(persona_text(p, n))
    data.pop("personas")
    (suite.here / "team.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def _jobs(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list) or not all(isinstance(j, str) for j in value):
        raise ValueError("jobs must be a text or a list of texts")
    return [j.strip().lstrip("-").strip() for j in value if j.strip()]


def save_persona(suite, body: dict) -> dict:
    """Add or change one persona (the page's Team tab); checked whole, with the team it makes, before anything is
    written."""
    where = "the persona"
    p = persona(
        "",
        {
            "name": body.get("name"),
            "role": body.get("role"),
            "device": body.get("device") or "desktop",
            "moderator": body.get("moderator"),
            "on": body.get("on"),
        },
        str(body.get("brief") or ""),
        where,
    )
    key = str(body.get("key") or _slug(p["name"]))
    if not key:
        raise ValueError("give the persona a key (or a name to make one from)")
    p.update(key=_key(key, where, "persona"), jobs=_jobs(body.get("jobs")))
    current = {x["key"]: x for x in team(suite.here, _team_json(suite))[0]}
    check_team(list({**current, key: p}.values()), "the team")
    _personas_to_files(suite)
    path = suite.here / "personas" / f"{key}.md"
    order = _order(path) if path.is_file() else max(_order(f) for f in (suite.here / "personas").glob("*.md")) + 1
    path.write_text(persona_text(p, order))
    return {"personas": team(suite.here, {})[0]}


def remove_persona(suite, key: str) -> dict:
    current = {x["key"]: x for x in team(suite.here, _team_json(suite))[0]}
    if key not in current:
        raise LookupError(f"no persona {key!r}")
    check_team([p for k, p in current.items() if k != key], "the team")
    _personas_to_files(suite)
    (suite.here / "personas" / f"{key}.md").unlink()
    return {"personas": team(suite.here, {})[0]}


# ------------------------------------------------------------------------------------------------------- rules


def rule(rid: str, meta: dict, body: str, where: str) -> dict:
    severity = meta.get("severity", "should")
    if severity not in SEVERITIES:
        raise ConfigError(f"{where}: severity must be one of {', '.join(SEVERITIES)}")
    if not body.strip():
        raise ConfigError(f"{where}: the rule's text (under the --- block) is empty")
    out = {
        "id": rid,
        "title": _line(meta.get("title"), where, "title"),
        "severity": severity,
        "on": _flag(meta.get("on"), where, "on", True),
    }
    measure = _measure(meta.get("measure"), where)
    return {**out, **({"measure": measure} if measure else {}), "text": body.strip()}


def _measure(value, where: str) -> list[str]:
    """What the browser checks for a rule at every shoot (E7-F2-02): a list, or "a, b" in a rule's file."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [x.strip() for x in value.split(",") if x.strip()]
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError(f"{where}: measure must be a list of checks ({', '.join(MEASURES)})")
    for x in value:
        if x not in MEASURES:
            raise ConfigError(f"{where}: measure: {x} is not a check the browser runs ({', '.join(MEASURES)})")
    return list(dict.fromkeys(value))


def read_rule(path: Path) -> dict:
    where = f"rules/{path.name}"
    meta, body = split(path.read_text(), where, RULE_FIELDS, "title, severity, on, measure")
    return rule(_key(path.stem, where, "rule"), meta, body, where)


def rule_text(r: dict) -> str:
    measure = {"measure": ", ".join(r["measure"])} if r.get("measure") else {}
    return join({"title": r["title"], "severity": r["severity"], "on": r["on"], **measure}, r["text"])


def _sections(text: str) -> tuple[str, list[dict]]:
    """PRINCIPLES.md: its introduction, and every `## ` section as a rule (`## 3. Title` gets the id 03-title)."""
    found = list(SECTION.finditer(text))
    intro = text[: found[0].start()] if found else text
    out = []
    for i, m in enumerate(found):
        body = text[m.end() : found[i + 1].start() if i + 1 < len(found) else len(text)].strip()
        number, title = m.group(1), m.group(2)
        rid = (f"{int(number):02d}-" if number else "") + _slug(title)
        said = MEASURED.search(body)
        meta = {"title": title, "measure": said.group(1) if said else None}
        said_text = MEASURED.sub("", body).strip()
        out.append({**rule(rid, meta, said_text or "-", f"PRINCIPLES.md, section {title}"), "text": said_text})
    return intro, out


def rules(suite) -> list[dict]:
    """The rules the team judges by: the rule files when there are any, else PRINCIPLES.md's sections."""
    files = sorted((suite.here / "rules").glob("*.md"))
    if files:
        return [read_rule(f) for f in files]
    path = suite.here / "PRINCIPLES.md"
    return _sections(path.read_text())[1] if path.is_file() else []


def rules_from(suite) -> str:
    """Where the rules are read from now: "files" (rules/), "PRINCIPLES.md" (its sections) or "none"."""
    if any((suite.here / "rules").glob("*.md")):
        return "files"
    return "PRINCIPLES.md" if (suite.here / "PRINCIPLES.md").is_file() else "none"


def _rules_to_files(suite) -> None:
    """The first write from the page: PRINCIPLES.md's sections become rule files; it keeps its introduction."""
    if any((suite.here / "rules").glob("*.md")):
        return
    (suite.here / "rules").mkdir(exist_ok=True)
    path = suite.here / "PRINCIPLES.md"
    if not path.is_file():
        return
    intro, found = _sections(path.read_text())
    for r in found:
        (suite.here / "rules" / f"{r['id']}.md").write_text(rule_text(r))
    path.write_text(intro.rstrip() + "\n\n" + MOVED)


def save_rule(suite, body: dict) -> dict:
    """Add or change one rule (the page's Rules tab), checked before anything is written."""
    where = "the rule"
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        text = ""
    if isinstance(body.get("measure"), str):
        raise ValueError(f"{where}: measure must be a list of checks ({', '.join(MEASURES)})")
    r = rule(
        "",
        {
            "title": body.get("title"),
            "severity": body.get("severity") or "should",
            "on": body.get("on"),
            "measure": body.get("measure"),
        },
        text or "-",
        where,
    )
    if not text:
        raise ValueError(f"{where}: text must be a text")
    rid = str(body.get("id") or _slug(r["title"]))
    if not rid:
        raise ValueError("give the rule an id (or a title to make one from)")
    r["id"] = _key(rid, where, "rule")
    _rules_to_files(suite)
    (suite.here / "rules" / f"{rid}.md").write_text(rule_text(r))
    return {"rules": rules(suite)}


def remove_rule(suite, rid: str) -> dict:
    if rid not in {r["id"] for r in rules(suite)}:
        raise LookupError(f"no rule {rid!r}")
    _rules_to_files(suite)
    (suite.here / "rules" / f"{rid}.md").unlink()
    return {"rules": rules(suite)}


def rules_for_a_run(found: list[dict]) -> str:
    """The rules that are on, as a run reads them (inputs/rules.md): id, title, weight and what each asks."""
    held = [r for r in found if r["on"]]
    if not held:
        return "(no rules yet: judge by the principles alone)\n"

    def head(r):
        return (
            f"{r['severity']}, measured by the browser: {', '.join(r['measure'])}"
            if r.get("measure")
            else r["severity"]
        )

    return "".join(f"## {r['id']} · {r['title']} ({head(r)})\n\n{r['text']}\n\n" for r in held)
