"""The framework's one local server: the Tests dashboard and the UX suite side by side, in one look, kept current.

    python3 crissp/testsuite/lib/serve.py --port 8766      (crissp/test.sh --dashboard and crissp/ux.sh start it)

What it serves, only on 127.0.0.1:
- /dashboard/   the Tests dashboard (crissp/testsuite/dashboard): what the last runs proved, the backlog board. When the
                backlog, changes.json or a run's results are newer than the dashboard's data, the data is rebuilt
                (lib/collect.py) the moment the page asks for it: the page asks GET /dashboard/stamp every few seconds and
                reloads itself when the stamp changes, so a story moved on the board, a finding written or a check that
                finished shows up without anyone running anything.
- /results/     the project's run output: the dashboard's data (results/data.js, lib/collect.py), the Claude session
                pages (results/sessions/) and what the dashboard links to (screenshots).
- /look/        the shared look (crissp/look: the tokens, the font, the theme, the water).
- /ux/          the UX suite (crissp/uxsuite/api.py answers it: its page, its API, the team's designs), when the
                repository has one; its queue worker runs inside this server.
Nothing else of the repository. It never runs a test.
"""

import argparse
import functools
import http.server
import importlib.util
import json
import sys
import threading
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402

SUITE = ENGINE.parent  # the engine's own files: the dashboard page (dashboard/), the look is crissp/look beside it
LOOK = SUITE.parent / "look"


def watched(root: Path) -> list[Path]:
    """What the dashboard shows: the backlog, the proof of every change, and the results of the last runs."""
    out = sorted((root / "crissp" / "backlog").rglob("*.md"))
    out += [root / "crissp" / "testsuite" / name for name in ("changes.json", "threats.json", "suites.json")]
    results = project.results(root)
    out += sorted(p for p in results.iterdir() if p.is_file()) if results.is_dir() else []
    return out


def newest(paths: list[Path]) -> float:
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)


class Live:
    """The dashboard's data, rebuilt when what it shows changed; one rebuild at a time."""

    def __init__(self, root: Path, rebuild) -> None:
        self.root, self.rebuild = root, rebuild
        self.data = project.results(root) / "data.js"
        self.lock = threading.Lock()

    def built(self) -> float:
        return self.data.stat().st_mtime if self.data.exists() else 0.0

    def stamp(self) -> float:
        with self.lock:
            if newest([p for p in watched(self.root) if p != self.data]) > self.built():
                try:
                    self.rebuild()
                except Exception as err:  # noqa: BLE001  the page keeps the last good data; the reason goes to the log
                    print(f"dashboard data not rebuilt: {err}", file=sys.stderr)
            return self.built()


UX_API = SUITE.parent / "uxsuite" / "api.py"


def load_ux(path: Path = UX_API):
    """The UX suite's request handler (crissp/uxsuite/api.py, beside this engine), or None without a UX suite. It works
    for the project CRISSP_ROOT names, as this server does."""
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("crissp_uxsuite_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Handler(http.server.SimpleHTTPRequestHandler):
    live: Live
    look: Path
    pages: Path  # the dashboard page's files
    ux = None

    def translate_path(self, path: str) -> str:
        """/dashboard/ from the engine, /results/ from the project; nothing else is a file here."""
        path = path.split("?", 1)[0].split("#", 1)[0]
        for prefix, base in (("/dashboard/", self.pages), ("/results/", project.results(self.live.root))):
            if path.startswith(prefix):
                self.directory = str(base)
                return super().translate_path("/" + path[len(prefix):])
        return str(self.pages / ".nothing-here")

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802  (the name http.server calls)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/dashboard/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/dashboard/stamp":
            return self._json(200, {"stamp": self.live.stamp()})
        if path.startswith("/look/"):
            return self._look(path[len("/look/"):])
        if path == "/ux" or path.startswith("/ux/"):
            return self._ux("GET")
        if path == "/results/data.js":
            self.live.stamp()  # a first load gets current data too
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/ux" or path.startswith("/ux/"):
            return self._ux("POST")
        self._json(404, {"error": "not found"})

    def _ux(self, method: str) -> None:
        if not self.ux:
            return self._json(404, {"error": "this repository has no UX suite (crissp/uxsuite)"})
        self.ux.handle(self, method)

    def _look(self, name: str) -> None:
        """One file of the shared look, nothing beside it."""
        file = (self.look / name).resolve()
        if file.parent != self.look.resolve() or not file.is_file():
            return self._json(404, {"error": "not found"})
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(file)))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")  # the page always reads what is on disk now
        super().end_headers()

    def log_message(self, *args) -> None:  # quiet: the page asks every few seconds
        pass


def server(port: int, root: Path | None = None, suite: Path = SUITE, rebuild=None, ux=None,
           look: Path = LOOK) -> http.server.ThreadingHTTPServer:
    """The server, not started yet, for the project at root (default: CRISSP_ROOT or the current directory). suite: where
    the dashboard page is (the engine's); ux: the UX suite's handler (by default the project's own, when it has one)."""
    root = root or project.root()
    live = Live(root, rebuild or collect)
    handler = type("LiveHandler", (Handler,), {"live": live, "look": look, "pages": suite / "dashboard",
                                               "ux": load_ux() if ux is None else ux})
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(handler, directory=str(suite)))


def collect() -> None:
    """lib/collect.py, as crissp/test.sh runs it: the dashboard's data from the last runs and the backlog."""
    spec = importlib.util.spec_from_file_location("collect_for_the_live_dashboard", SUITE / "lib" / "collect.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the Tests dashboard and the UX suite and keep them current.")
    parser.add_argument("--port", type=int, default=8766)
    httpd = server(parser.parse_args(argv).port)
    ux = httpd.RequestHandlerClass.func.ux
    if ux is not None and hasattr(ux, "start_worker"):
        ux.start_worker()  # the UX team's queue: started from here, so it runs while the suite is open
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script by crissp/test.sh; main() is tested
    sys.exit(main())
