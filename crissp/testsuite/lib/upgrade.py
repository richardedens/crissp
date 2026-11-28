"""The steps a newer crissp brings, added to a project brought in earlier (F-153): shared by crissp init and repair.

A project's suites.json is its own once crissp init wrote it, so a step the template gained later (quality, licenses,
dast) never reached it: `crissp check` said nothing of DAST. This adds what is missing and nothing else: the template's
step, its audit settings, and quality on a path rule that runs sast (as the template's rules do). The project's own
steps, rules and settings stay as they are. Standard library only.
"""

NEW = ("quality", "licenses", "dast")  # the template's steps since 0.2.1, each with its audit.<key> settings
AFTER = {"quality": "sast"}  # a path rule that runs sast also measures the quality, right after it


def _audit(data: dict) -> dict | None:
    audit = data.get("audit")
    return {} if audit is None else audit if isinstance(audit, dict) else None


def missing(data: dict, template: dict) -> dict:
    """What the project's suites.json lacks: steps, audit settings and path rules that should run a new step."""
    have = {s.get("key") for s in data.get("steps", [])}
    audit = _audit(data)
    return {
        "steps": [k for k in NEW if k not in have],
        "audit": [] if audit is None else [k for k in NEW if k in template["audit"] and k not in audit],
        "rules": [
            i
            for i, r in enumerate(data.get("paths", []))
            for k, after in AFTER.items()
            if after in r.get("steps", []) and k not in r["steps"] and k not in have
        ],
    }


def said(gap: dict) -> str:
    """The gap in words, e.g. "without the steps quality, dast → added from the template, with audit.dast"."""
    steps, audit = gap["steps"], [f"audit.{k}" for k in gap["audit"]]
    named = " and ".join([", ".join(audit[:-1]), audit[-1]] if len(audit) > 1 else audit)
    text = f"without the steps {', '.join(steps)} → added from the template" if steps else f"without {named} → added"
    if steps and audit:
        text += f", with {named}"
    return text + (" (quality where sast runs)" if gap["rules"] else "")


def add(data: dict, template: dict) -> dict:
    """Adds the gap to data in place; returns the gap (empty lists: nothing was missing)."""
    gap = missing(data, template)
    for i in gap["rules"]:
        rule = data["paths"][i]
        for key, after in AFTER.items():
            rule["steps"].insert(rule["steps"].index(after) + 1, key)
    data["steps"] = data.get("steps", []) + [s for s in template["steps"] if s["key"] in gap["steps"]]
    if gap["audit"]:
        data["audit"] = {**_audit(data), **{k: template["audit"][k] for k in gap["audit"]}}
    return gap
