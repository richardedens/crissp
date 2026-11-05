"""The screenshots a round looks at: a walk taken in a real browser (Playwright, Chromium) on the devices the team uses.

A persona on a desktop looks at the laptop (1440 × 900), one on a mobile at the phone (390 × 844, touch), one on both
at both. shoot() writes the plan (results/shots/<walk>/plan.json) and runs this file under uv with Playwright pinned, so
nothing is installed into the repository; the browser itself comes from `playwright install chromium` (once, by the
person who runs it: never from here). The shots go to results/shots/<walk>/<device>/NN-<title>.png and are listed in
shots.json; a step that fails ends the walk on that device as "Stuck at step n", which the team sees as a finding too.

    python3 crissp/uxsuite/cli.py shoot <walk>         (crissp/ux.sh --shoot <walk>)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ux_config import Suite

HERE = Path(__file__).resolve().parent
PLAYWRIGHT = "playwright==1.55.0"
VIEWPORTS = {"laptop": {"width": 1440, "height": 900, "touch": False}, "phone": {"width": 390, "height": 844, "touch": True}}
ON = {"desktop": ("laptop",), "mobile": ("phone",), "both": ("laptop", "phone")}


def slug(title: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", title.lower()))[:40] or "shot"


def devices(conf: dict) -> list[str]:
    """The devices the team looks on, laptop first."""
    used = {d for p in conf["personas"] for d in ON[p["device"]]}
    return [d for d in VIEWPORTS if d in used]


def plan(suite: Suite, conf: dict, walk_id: str) -> dict:
    """What the browser does: the walk's steps on each device, and where the pictures go."""
    walk = conf["walks"].get(walk_id)
    if walk is None:
        raise ValueError(f"unknown walk {walk_id!r} (known: {', '.join(conf['walks']) or 'none'})")
    return {"url": conf["url"], "walk": walk_id, "out": str(suite.results / "shots" / walk_id),
            "devices": {d: VIEWPORTS[d] for d in devices(conf)}, "steps": walk["steps"]}


def shoot(suite: Suite, conf: dict, walk_id: str, run=subprocess.run) -> tuple[int, str]:
    """Take the walk now (the old pictures of this walk go first); (exit code, what to tell the person)."""
    p = plan(suite, conf, walk_id)
    out = Path(p["out"])
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    (out / "plan.json").write_text(json.dumps(p, indent=1) + "\n")
    done = run(["uv", "run", "--quiet", "--no-project", "--with", PLAYWRIGHT, "python", str(HERE / "ux_shoot.py"),
                str(out / "plan.json")], capture_output=True, text=True)
    if done.returncode:
        return 1, (f"The walk could not be shot ({conf['url']} must be running): {(done.stderr or done.stdout).strip()[-600:]}\n"
                   f"The browser comes once from: uv run --no-project --with {PLAYWRIGHT} playwright install chromium")
    try:
        shots = json.loads((out / "shots.json").read_text())
    except (OSError, json.JSONDecodeError):
        return 1, "The browser ended without a list of shots (shots.json)."
    stuck = [f"{s['device']}: {s['error']}" for s in shots if s.get("error")]
    return 0, (f"{walk_id}: {len(shots) - len(stuck)} screenshot(s) in {out.relative_to(suite.root)}"
               + "".join(f"\n  {s}" for s in stuck))


def capture(plan_file: Path) -> None:  # pragma: no cover — drives a real browser; shoot() and plan() are tested with a stand-in
    from playwright.sync_api import sync_playwright

    p = json.loads(plan_file.read_text())
    out, shots = Path(p["out"]), []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for device, vp in p["devices"].items():
            (out / device).mkdir(parents=True, exist_ok=True)
            ctx = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]}, has_touch=vp["touch"],
                                      is_mobile=vp["touch"], reduced_motion="reduce")
            page, n = ctx.new_page(), 0
            for i, step in enumerate(p["steps"], 1):
                try:
                    if step["do"] == "goto":
                        page.goto(p["url"] + step["path"], wait_until="networkidle")
                    elif step["do"] == "click":
                        (page.get_by_text(step["text"]).first if "text" in step else page.locator(step["selector"])).click()
                    elif step["do"] == "fill":
                        page.locator(step["selector"]).fill(str(step["value"]))
                    elif step["do"] == "press":
                        page.keyboard.press(step["key"])
                    elif step["do"] == "wait":
                        page.wait_for_timeout(int(step["ms"]))
                    else:
                        n += 1
                        file = f"{device}/{n:02d}-{slug(step['title'])}.png"
                        page.screenshot(path=str(out / file))
                        shots.append({"device": device, "n": n, "title": step["title"], "file": file})
                except Exception as e:  # noqa: BLE001  a dead end is a finding: the team sees where it got stuck
                    shots.append({"device": device, "n": n + 1, "title": step.get("title", step["do"]), "file": "",
                                  "error": f"Stuck at step {i} ({step['do']}): {str(e).splitlines()[0][:200]}"})
                    break
            ctx.close()
        browser.close()
    (out / "shots.json").write_text(json.dumps(shots, indent=1) + "\n")


if __name__ == "__main__":  # pragma: no cover — run by shoot() under uv with Playwright
    capture(Path(sys.argv[1]))
