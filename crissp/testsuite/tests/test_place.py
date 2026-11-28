"""Which port the dashboard of this project uses (lib/place.py, asked by crissp/test.sh): this project's dashboard is
reused; another project's (or one that does not say whose it is) is left alone and the next port is taken, saying so;
a program that is no dashboard on the asked port stops it with a clear message (F-09)."""

import http.server
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import place


class Stamp(http.server.BaseHTTPRequestHandler):
    answer: bytes = b""

    def do_GET(self):
        if self.path.startswith("/dashboard/stamp") and self.answer:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.answer)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def listen(answer: dict | None):
    """A server on a free port: a dashboard whose stamp says `answer`, or (None) a program that is no dashboard."""
    handler = type("H", (Stamp,), {"answer": json.dumps(answer).encode() if answer is not None else b""})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_free_port_is_taken(tmp_path):
    port = free_port()
    assert place.place(tmp_path, port) == (port, "free", "")


def test_this_projects_dashboard_is_reused(tmp_path):
    httpd, port = listen({"stamp": 1.0, "root": str(tmp_path.resolve())})
    try:
        assert place.place(tmp_path, port) == (port, "same", "")
    finally:
        httpd.shutdown()


@pytest.mark.parametrize(
    "answer, whose",
    [
        ({"stamp": 1.0, "root": "/elsewhere/shop"}, "/elsewhere/shop"),
        ({"stamp": 1.0}, "a project that does not say which"),
    ],
)
def test_another_projects_dashboard_is_left_alone_and_the_next_port_taken(tmp_path, answer, whose):
    httpd, port = listen(answer)
    try:
        got, state, note = place.place(tmp_path, port)
        assert state == "free" and got != port and got > port
        assert note == f"Port {port} serves the dashboard of {whose}"
    finally:
        httpd.shutdown()


def test_a_program_that_is_no_dashboard_on_the_asked_port_stops_it(tmp_path):
    httpd, port = listen(None)
    try:
        assert place.place(tmp_path, port) == (port, "taken", "")
    finally:
        httpd.shutdown()


def test_no_port_left_is_said(tmp_path, monkeypatch):
    httpd, port = listen({"stamp": 1.0, "root": "/elsewhere"})
    monkeypatch.setattr(place, "TRIES", 0)  # only the asked port
    try:
        assert place.place(tmp_path, port) == (port, "taken", f"Port {port} serves the dashboard of /elsewhere")
    finally:
        httpd.shutdown()


def test_main_prints_port_state_and_note_for_test_sh(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path))
    port = free_port()
    assert place.main([str(port)]) == 0 and capsys.readouterr().out == f"{port} free \n"
    assert place.main([]) == 2 and "usage" in capsys.readouterr().err


def test_further_on_other_programs_and_dashboards_are_passed_by_and_the_first_note_kept(tmp_path, monkeypatch):
    """Past the asked port a program that is no dashboard is passed by too; the note names the first other dashboard."""
    answers = {9000: "/a", 9001: "", 9002: "/b", 9003: None}
    monkeypatch.setattr(place, "whose", answers.get)
    assert place.place(tmp_path, 9000) == (9003, "free", "Port 9000 serves the dashboard of /a")
    answers[9003] = str(tmp_path.resolve())  # this project's own dashboard further on: reused
    assert place.place(tmp_path, 9000) == (9003, "same", "Port 9000 serves the dashboard of /a")
