"""Which port this project's dashboard uses (crissp/test.sh asks it): F-09.

    python3 crissp/testsuite/lib/place.py <port>   prints "<port> <state> <note>"

- this project's dashboard already answers there (its stamp names this project): `same`, reuse it;
- the port is free: `free`, start there;
- another project's dashboard (or one that does not say whose it is) holds it: leave it alone, try the next port, and
  say so in the note; the first free port, or this project's own dashboard further on, is the answer;
- a program that is no dashboard holds the asked port: `taken` (crissp/test.sh says so: stop it, or set
  CRISSP_DASHBOARD_PORT). The project is CRISSP_ROOT, or the current directory.
"""

import json
import socket
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402

TRIES = 20  # ports tried after the asked one


def whose(port: int) -> str | None:
    """What answers on the port: None when nothing listens, "" for a program that is no dashboard, the project a
    dashboard serves (or "?" when its stamp does not say)."""
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard/stamp", timeout=2) as answer:
            stamp = json.loads(answer.read(65536))
    except (OSError, ValueError):
        return ""
    return str(stamp.get("root") or "?") if isinstance(stamp, dict) and "stamp" in stamp else ""


def place(root: Path, port: int) -> tuple[int, str, str]:
    """(port, state, note) for this project's dashboard, starting at the asked port."""
    mine, note = str(Path(root).resolve()), ""
    for p in range(port, port + 1 + TRIES):
        found = whose(p)
        if found is None:
            return p, "free", note
        if found == mine:
            return p, "same", note
        if found == "" and p == port:
            return p, "taken", ""
        if found and not note:
            note = f"Port {p} serves the dashboard of {found if found != '?' else 'a project that does not say which'}"
    return port, "taken", note


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: place.py <port>", file=sys.stderr)
        return 2
    port, state, note = place(project.root(), int(argv[0]))
    print(f"{port} {state} {note}")
    return 0


if __name__ == "__main__":  # pragma: no cover — run by crissp/test.sh; main() is tested
    sys.exit(main(sys.argv[1:]))
