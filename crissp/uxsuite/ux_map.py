"""The map of the product (E7-F3-01): one list of its screens, so the team looks at more than the walks someone wrote.

Three sources, merged by screen (the path without its query, ids folded: /orders/42 and /orders/43 are /orders/:id):
- a read-only crawl of the running product: it opens home and every walk's first page on the team's devices and follows
  the product's own links (same origin, no file downloads, never a link that signs out or deletes), at most map.max
  pages per device. Like a shoot, it runs this file under uv with Playwright pinned and writes results/map/crawl/;
- the project's own E2E test screenshots: a test may list what it took in a manifest, by default
  crissp/uxsuite/results/test-shots/screens.json, [{"path", "file" (beside the manifest), "title", "device", "test"}];
  the pictures are copied into results/map/tests/ so the suite serves only its own results;
- the walks: the pages they go to and the screens their shots show.

results/map/screens.json lists every screen with its area (the first part of its path), how it was found, which page
links to it, its shots and its gaps: a screen no link reaches (only a test or a walk gets there) or that the crawl could
not open, and a screen no walk looks at.

    python3 crissp/uxsuite/cli.py map                  (crissp/ux.sh --map, crissp ux --map)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import ux_shoot
import ux_team
from ux_config import Suite

HERE = Path(__file__).resolve().parent
PICTURES = (".png", ".jpg", ".jpeg", ".webp")
ID = re.compile(r"\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{12,}")
NEVER = re.compile(
    r"log-?out|sign-?out|delete|remove|destroy", re.IGNORECASE
)  # the crawl only looks: it never follows these
FILES = re.compile(r"\.(?!html?$)[a-z0-9]{2,5}$", re.IGNORECASE)  # a download (.pdf, .zip, .csv), not a page
SOURCES = ("crawl", "test", "walk")
REACH = ("no link reaches it", "the crawl could not open it")


def screen_key(path: str) -> str:
    """The screen a path shows: no query or fragment, lower case, no trailing slash, ids folded to :id."""
    path = urlsplit(path).path.lower().rstrip("/")
    return "/" + "/".join(":id" if ID.fullmatch(p) else p for p in path.split("/") if p)


def area(key: str) -> str:
    return key.split("/")[1] if key != "/" else "home"


def follow(base: str, hrefs: list[str]) -> list[str]:
    """The links on a page the crawl may open: the product's own pages (same scheme, host and port), one per screen."""
    own, out, seen = urlsplit(base), [], set()
    for href in hrefs:
        u = urlsplit(href)
        if (u.scheme, u.netloc) != (own.scheme, own.netloc) or NEVER.search(u.path) or FILES.search(u.path):
            continue
        key = screen_key(u.path)
        if key not in seen:
            seen.add(key)
            out.append(u.path + (f"?{u.query}" if u.query else ""))
    return out


def _gotos(walk: dict) -> list[str]:
    return [s["path"] for s in walk["steps"] if s["do"] == "goto"]


def plan(suite: Suite, conf: dict) -> dict:
    """What the browser does: where it starts (home, then every walk's pages), on which devices, how far."""
    start = list(dict.fromkeys(["/", *(p for w in conf["walks"].values() for p in _gotos(w))]))
    return {
        "url": conf["url"],
        "out": str(suite.results / "map" / "crawl"),
        "start": start,
        "max": conf["map"]["max"],
        "devices": {d: ux_shoot.VIEWPORTS[d] for d in ux_shoot.devices(conf) or ux_shoot.VIEWPORTS},
    }


def crawl(suite: Suite, conf: dict, run=subprocess.run) -> tuple[int, str]:
    """Crawl the running product now and rebuild the map; (exit code, what to tell the person). A crawl that fails
    leaves the last map as it was."""
    p = plan(suite, conf)
    done_dir, new = Path(p["out"]), Path(p["out"] + ".new")
    shutil.rmtree(new, ignore_errors=True)
    new.mkdir(parents=True)
    (new / "plan.json").write_text(json.dumps({**p, "out": str(new)}, indent=1) + "\n")
    done = run(
        [
            "uv",
            "run",
            "--quiet",
            "--no-project",
            "--with",
            ux_shoot.PLAYWRIGHT,
            "python",
            str(HERE / "ux_map.py"),
            str(new / "plan.json"),
        ],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        return 1, (
            f"The product could not be crawled ({conf['url']} must be running): {(done.stderr or done.stdout).strip()[-600:]}\n"
            f"The browser comes once from: uv run --no-project --with {ux_shoot.PLAYWRIGHT} playwright install chromium"
        )
    if not (new / "crawl.json").is_file():
        return 1, "The browser ended without a list of pages (crawl.json)."
    shutil.rmtree(done_dir, ignore_errors=True)
    new.rename(done_dir)
    m = build(suite, conf)
    stuck = [f"  {s['key']}: {g}" for s in m["screens"] for g in s["gaps"] if g.startswith(REACH[1])]
    where = (suite.results / "map" / "screens.json").relative_to(suite.root)
    said = f"{len(m['screens'])} screen(s) in {len(m['areas'])} area(s), {m['gaps']} gap(s): {where}"
    return 0, "\n".join([said, *stuck, *m["skipped"]])


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _tests(suite: Suite, conf: dict) -> tuple[list[dict], list[str]]:
    """The project's test screenshots, copied into results/map/tests/; (the shots, what was skipped and why)."""
    manifest = suite.root / conf["map"]["tests"]
    target = suite.results / "map" / "tests"
    shutil.rmtree(target, ignore_errors=True)
    if not manifest.is_file():
        return [], []
    listed = _json(manifest)
    if not isinstance(listed, list):
        return [], [f"{conf['map']['tests']}: not a JSON list"]
    out, skipped, beside = [], [], manifest.parent.resolve()
    for i, e in enumerate(listed, 1):
        if not isinstance(e, dict) or not isinstance(e.get("path"), str) or not isinstance(e.get("file"), str):
            skipped.append(f"entry {i}: needs a path and a file")
            continue
        src = (manifest.parent / e["file"]).resolve()
        if beside not in src.parents or src.suffix.lower() not in PICTURES:
            skipped.append(f"{e['path']}: {e['file']} is not a picture beside {manifest.name}")
            continue
        if not src.is_file():
            skipped.append(f"{e['path']}: {e['file']} is not there")
            continue
        target.mkdir(parents=True, exist_ok=True)
        name = f"{len(out) + 1:02d}{src.suffix.lower()}"
        shutil.copyfile(src, target / name)
        out.append(
            {
                "path": e["path"],
                "title": str(e.get("title") or ""),
                "device": str(e.get("device") or "laptop"),
                "test": str(e.get("test") or ""),
                "url": f"/ux/results/map/tests/{name}",
            }
        )
    return out, skipped


def build(suite: Suite, conf: dict) -> dict:
    """Merge the crawl, the test screenshots and the walks into results/map/screens.json, and return it."""
    screens: dict[str, dict] = {}

    def screen(path: str) -> dict:
        k = screen_key(path)
        return screens.setdefault(
            k,
            {
                "key": k,
                "title": "",
                "area": area(k),
                "found_by": [],
                "tests": [],
                "walks": [],
                "linked_from": [],
                "shots": [],
                "errors": [],
            },
        )

    def found(s: dict, how: str, walk: str = "") -> None:
        if how not in s["found_by"]:
            s["found_by"].append(how)
        if walk and walk not in s["walks"]:
            s["walks"].append(walk)

    pages = _json(suite.results / "map" / "crawl" / "crawl.json")
    crawled = isinstance(pages, list)
    for pg in pages if crawled else []:
        s = screen(pg["path"])
        found(s, "crawl")
        s["title"] = s["title"] or pg.get("title", "")
        if pg.get("from") and screen_key(pg["from"]) != s["key"] and screen_key(pg["from"]) not in s["linked_from"]:
            s["linked_from"].append(screen_key(pg["from"]))
        if pg.get("error"):
            s["errors"].append(pg["error"])
        elif pg.get("file"):
            s["shots"].append(
                {
                    "device": pg["device"],
                    "url": f"/ux/results/map/crawl/{pg['file']}",
                    "source": "crawl",
                    "title": pg.get("title", ""),
                }
            )
    shots, skipped = _tests(suite, conf)
    for t in shots:
        s = screen(t["path"])
        found(s, "test")
        s["title"] = s["title"] or t["title"]
        if t["test"] and t["test"] not in s["tests"]:
            s["tests"].append(t["test"])
        s["shots"].append({"device": t["device"], "url": t["url"], "source": "test", "title": t["title"]})
    for w in conf["walks"].values():
        gotos = _gotos(w)
        for p in gotos:
            found(screen(p), "walk", w["id"])
        for sh in ux_team.shots(suite, w["id"]):
            if sh["url"] and (sh.get("at") or gotos):
                s = screen(sh.get("at") or gotos[0])
                found(s, "walk", w["id"])
                s["title"] = s["title"] or sh["title"]
                s["shots"].append({"device": sh["device"], "url": sh["url"], "source": "walk", "title": sh["title"]})
    out = []
    for k in sorted(screens):
        s = screens.pop(k)
        s["found_by"] = [x for x in SOURCES if x in s["found_by"]]
        s["title"] = s["title"] or k
        errors = s.pop("errors")
        s["gaps"] = (
            [f"{REACH[1]} ({errors[0]})"] if errors else [REACH[0]] if crawled and "crawl" not in s["found_by"] else []
        ) + ([] if s["walks"] else ["no walk looks at it"])
        out.append(s)
    areas: dict[str, int] = {}
    for s in out:
        areas[s["area"]] = areas.get(s["area"], 0) + 1
    m = {
        "at": ux_team.now(),
        "url": conf["url"],
        "crawled": crawled,
        "screens": out,
        "areas": dict(sorted(areas.items())),
        "gaps": sum(any(g.startswith(REACH) for g in s["gaps"]) for s in out),
        "skipped": skipped,
    }
    (suite.results / "map").mkdir(parents=True, exist_ok=True)
    (suite.results / "map" / "screens.json").write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    return m


def load(suite: Suite) -> dict | None:
    """The last map, or None when the product was never mapped."""
    return _json(suite.results / "map" / "screens.json")


def capture(
    plan_file: Path,
) -> None:  # pragma: no cover — drives a real browser; plan(), follow() and build() are tested
    from playwright.sync_api import sync_playwright

    p = json.loads(plan_file.read_text())
    out, pages = Path(p["out"]), []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        found: list[tuple[str, str | None]] = []  # the laptop finds the pages; every other device opens the same ones
        for device, vp in p["devices"].items():
            (out / device).mkdir(parents=True, exist_ok=True)
            ctx = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                has_touch=vp["touch"],
                is_mobile=vp["touch"],
                reduced_motion="reduce",
            )
            page = ctx.new_page()
            todo = list(found) if found else [(s, None) for s in p["start"]]
            seen = {screen_key(t[0]) for t in todo}
            n = 0
            while todo and n < p["max"]:
                path, parent = todo.pop(0)
                n += 1
                entry = {"path": path, "device": device, "from": parent, "title": "", "file": "", "links": []}
                try:
                    page.goto(p["url"] + path, wait_until="networkidle", timeout=20000)
                    entry["title"] = page.title()
                    entry["file"] = f"{device}/{n:02d}.png"
                    page.screenshot(path=str(out / entry["file"]))
                    entry["links"] = follow(
                        p["url"], page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
                    )
                except Exception as e:  # a page that does not open is a gap on the map
                    entry["error"] = str(e).splitlines()[0][:200]
                pages.append(entry)
                if found and device != next(iter(p["devices"])):
                    continue
                for link in entry["links"]:
                    if screen_key(link) not in seen:
                        seen.add(screen_key(link))
                        todo.append((link, path))
            if not found:
                found = [(e["path"], e["from"]) for e in pages]
            ctx.close()
        browser.close()
    (out / "crawl.json").write_text(json.dumps(pages, indent=1) + "\n")


if __name__ == "__main__":  # pragma: no cover — run by crawl() under uv with Playwright
    sys.exit(capture(Path(sys.argv[1])))
