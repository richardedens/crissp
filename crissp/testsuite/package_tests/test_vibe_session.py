"""F-100: a real Mistral Vibe session in a project crissp brought in gets the crissp tools: brief and backlog.

The session is Vibe itself (the `vibe` command, headless), with everything else stood in: a throwaway project made by
crissp init, a throwaway VIBE_HOME, and a stand-in model on 127.0.0.1 that answers the way a model would. Vibe defers
MCP tools behind search_tool_functions, so the stand-in first searches for "crissp brief backlog" (what an agent does
when the agreement says to call brief) and then ends the turn; the test reads what Vibe answered that search. No
real model, no network, no ~/.vibe. Vibe is a dev tool, not pinned here: without it on PATH (or CRISSP_VIBE naming
it) the test is skipped, and says so.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))

import vibe  # noqa: E402

from crissp import cli  # noqa: E402

VIBE = os.environ.get("CRISSP_VIBE") or shutil.which("vibe")
pytestmark = pytest.mark.skipif(not VIBE, reason="Mistral Vibe is not installed (pip install mistral-vibe, or "
                                                 "CRISSP_VIBE=<path to vibe>): the real-session test did not run")


class Model(BaseHTTPRequestHandler):
    """A stand-in for an OpenAI-style chat endpoint: the first turn searches Vibe's tools, the next one ends."""

    seen: ClassVar[list[dict]] = []

    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):  # Vibe may list the models
        self._send({"data": [{"id": "stand-in"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Model.seen.append(body)
        first = not any(m.get("role") == "tool" for m in body.get("messages", []))
        delta = ({"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {
            "name": "search_tool_functions", "arguments": json.dumps({"query": "crissp brief backlog"})}}]}
                 if first else {"content": "done"})
        chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant", **delta}, "finish_reason": None}]},
                  {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if first else "stop"}]},
                  {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}}]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in chunks:
            c |= {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "stand-in"}
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

    def _send(self, data: dict) -> None:
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def model():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Model.seen = []
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


def test_a_vibe_session_in_a_brought_in_project_finds_brief_and_backlog(tmp_path, model, monkeypatch):
    project, home = tmp_path / "proj", tmp_path / "vibe-home"
    project.mkdir()
    home.mkdir()
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes"], env={"VIBE_HOME": str(home)}) == 0
    # The config init wrote, with the server of this checkout in place of `uvx crissp==<version> mcp` (the same
    # server, not on PyPI yet): what is proven is how Vibe reads it, finds the project and lists the tools.
    config = project / ".vibe" / "config.toml"
    config.write_text(vibe.config(project.resolve(), sys.executable, ["-I", str(REPO / "crissp/tool/server.py")]))
    (home / "config.toml").write_text(
        'active_model = "stand-in"\nenable_telemetry = false\nenable_update_checks = false\n'
        'enable_auto_update = false\nenable_model_catalog = false\n'
        f'[[providers]]\nname = "stand-in"\napi_base = "{model}"\napi_key_env_var = "STAND_IN_KEY"\n'
        '[[models]]\nname = "stand-in"\nprovider = "stand-in"\nalias = "stand-in"\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRISSP_", "VIBE_"))}
    env |= {"VIBE_HOME": str(home), "STAND_IN_KEY": "stand-in", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    done = subprocess.run([VIBE, "-p", "Call brief first.", "--output", "json", "--auto-approve"], cwd=project,
                          env=env, capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    answers = [m for body in Model.seen for m in body.get("messages", []) if m.get("role") == "tool"]
    assert answers, f"Vibe never answered the stand-in's tool search: {done.stdout[-2000:]}"
    found = json.dumps(answers)
    assert "mcp_crissp" in found and "brief" in found and "backlog" in found, found[:3000]
