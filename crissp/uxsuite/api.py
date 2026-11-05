"""The UX suite in the framework's one local server (crissp/testsuite/lib/serve.py loads this file and hands it every
request under /ux): its page, what the team did and does, and the product owner's verdicts and requests.

    GET  /ux/                      the page (web/index.html, ux.js, ux.css; the shared look comes from /look/)
    GET  /ux/api/state             everything the page shows: the product, the team, every walk with its screenshots,
                                   rounds and designs (with the verdict that holds and the PBI of an approved one), the
                                   queue and what the team does now
    GET  /ux/results/shots/…       the walks' screenshots
    GET  /ux/results/proposals/…   the team's designs; their HTML in a sandbox of its own (never this origin)
    POST /ux/api/verdict           {id, verdict, reason}: a verdict (ux_verdicts), and what it sets going
    POST /ux/api/request           {kind: round|proposal, walk, focus}: start it now, or queue it

A write is accepted only from the suite's own page (the same Origin): no other web page open in the browser can write a
verdict or start a run. The server listens on 127.0.0.1 only.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ux_backlog  # noqa: E402
import ux_config  # noqa: E402
import ux_team  # noqa: E402
import ux_verdicts  # noqa: E402

WEB = HERE / "web"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
SANDBOX = "sandbox allow-scripts; default-src 'self' 'unsafe-inline' data:"
MAX_BODY = 20000


def state(suite: ux_config.Suite) -> dict:
    """What the page shows, in one answer; a broken configuration is an answer that says what is wrong."""
    try:
        conf = ux_config.load(suite)
    except ux_config.ConfigError as e:
        return {"error": str(e)}
    verdicts = ux_verdicts.latest(suite)
    try:
        pbis = ux_backlog.pbis(suite)
    except LookupError:
        pbis = {}
    walks = []
    for w in conf["walks"].values():
        designs = [{**v, "verdict": verdicts.get(v["key"]), "pbi": pbis.get(v["key"])}
                   for v in ux_team.versions(suite, "proposal", w["id"])]
        walks.append({"id": w["id"], "title": w["title"], "steps": len(w["steps"]), "shots": ux_team.shots(suite, w["id"]),
                      "rounds": ux_team.versions(suite, "round", w["id"]), "proposals": designs})
    return {"product": conf["product"], "monogram": conf["monogram"], "about": conf["about"], "url": conf["url"],
            "personas": conf["personas"], "walks": walks, "verdicts": verdicts, "queue": ux_team.queue(suite),
            "team": ux_team.state(suite, conf)}


def _send(handler, code: int, body: bytes, ctype: str = "application/json", extra: dict | None = None) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    for k, v in (extra or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def _json(handler, code: int, data) -> None:
    _send(handler, code, json.dumps(data, ensure_ascii=False).encode())


def _file(handler, path: Path, under: tuple[Path, ...]) -> None:
    path = path.resolve()
    if not any(u.resolve() in path.parents for u in under) or not path.is_file() or path.suffix not in TYPES:
        return _json(handler, 404, {"error": "not found"})
    extra = {"Content-Security-Policy": SANDBOX} if path.suffix == ".html" and WEB.resolve() not in path.parents else {}
    _send(handler, 200, path.read_bytes(), TYPES[path.suffix], extra)


def handle(handler, method: str, suite: ux_config.Suite | None = None) -> None:
    """Answer one request under /ux (serve.py calls this)."""
    suite = suite or ux_config.default_suite()
    path = unquote(urlparse(handler.path).path)
    if method == "POST":
        return _post(handler, path, suite)
    if path == "/ux":
        return _send(handler, 302, b"", "text/plain", {"Location": "/ux/"})
    if path == "/ux/":
        return _file(handler, WEB / "index.html", (WEB,))
    if path == "/ux/api/state":
        return _json(handler, 200, state(suite))
    if path.startswith("/ux/results/"):
        rest = path[len("/ux/results/"):]
        return _file(handler, suite.results / rest, (suite.results / "shots", suite.results / "proposals"))
    return _file(handler, WEB / path[len("/ux/"):], (WEB,))


def _post(handler, path: str, suite: ux_config.Suite) -> None:
    if path not in ("/ux/api/verdict", "/ux/api/request"):
        return _json(handler, 404, {"error": "not found"})
    if handler.headers.get("Origin") != f"http://127.0.0.1:{handler.server.server_address[1]}":
        return _json(handler, 403, {"error": "only the suite's own page may write"})
    try:
        size = int(handler.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            raise ValueError("too large")
        body = json.loads(handler.rfile.read(size) or b"{}")
        if not isinstance(body, dict):
            raise ValueError("send one JSON object")
        conf = ux_config.load(suite)
        if path == "/ux/api/verdict":
            line = ux_verdicts.record(suite, conf, body)
            return _json(handler, 200, {"line": line, **ux_verdicts.after(suite, conf, line)})
        focus = str(body.get("focus") or "").strip()
        if len(focus) > 1500:
            raise ValueError("the focus is too long (at most 1500 characters)")
        return _json(handler, 200, ux_team.request(suite, conf, str(body.get("kind")), str(body.get("walk")), focus))
    except (ValueError, LookupError) as e:  # a ConfigError and a JSON error are ValueErrors too
        return _json(handler, 400, {"error": str(e)})


def work(suite: ux_config.Suite, stop: threading.Event, interval: float) -> None:
    """The queue's worker: every interval, start what waits while places are free (never during a check run)."""
    while not stop.wait(interval):
        try:
            conf = ux_config.load(suite)
            ux_team.drain(suite, conf, lambda e: ux_team.start(suite, conf, e["kind"], e["walk"], e.get("focus", "")))
        except Exception as e:  # noqa: BLE001  the queue must not stop; the reason goes to the log
            print("ux queue:", e, file=sys.stderr)


def start_worker(suite: ux_config.Suite | None = None, interval: float = 10.0) -> threading.Event:
    """Start the worker beside the server; set the returned event to stop it."""
    stop = threading.Event()
    threading.Thread(target=work, args=(suite or ux_config.default_suite(), stop, interval), daemon=True).start()
    return stop
