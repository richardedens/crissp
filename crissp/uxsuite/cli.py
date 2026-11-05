"""The UX suite from the terminal (crissp/ux.sh calls this): what the team is, what it does, and asking it for work.

    python3 crissp/uxsuite/cli.py list                     the product, the team and the walks
    python3 crissp/uxsuite/cli.py status                   what runs, what waits, how many rounds, designs and verdicts
    python3 crissp/uxsuite/cli.py round <walk>             a round on a walk: now when a place is free, else queued
    python3 crissp/uxsuite/cli.py propose <walk> [focus]   a design for a walk, with an optional focus
    python3 crissp/uxsuite/cli.py shoot <walk>             take the walk's screenshots (the product must be running)

A queued request is started by the open suite (crissp/ux.sh, or crissp/test.sh --dashboard): its worker takes the queue.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ux_config  # noqa: E402
import ux_shoot  # noqa: E402
import ux_team  # noqa: E402
import ux_verdicts  # noqa: E402


def listing(conf: dict) -> str:
    lines = [f"{conf['product']}: {conf['about']}".rstrip(": "), f"Runs against {conf['url']}.", "", "The team:"]
    lines += [f"  {p['key']:<10} {p['name']}, {p['role']} ({p['device']}){' — moderator' if p['moderator'] else ''}"
              for p in conf["personas"]]
    lines += ["", "The walks:"] + [f"  {w['id']:<18} {w['title']}" for w in conf["walks"].values()]
    return "\n".join(lines if conf["walks"] else lines[:-1] + ["  none yet: add one to crissp/uxsuite/walks/"])


def status(suite: ux_config.Suite, conf: dict) -> str:
    st = ux_team.state(suite, conf)
    count = {k: sum(len(ux_team.versions(suite, k, w)) for w in conf["walks"]) for k in ux_team.KINDS}
    lines = [st["text"]] + [f"  running: {x}" for x in st["running"]] + [f"  waiting: {x}" for x in st["waiting"]]
    lines.append(f"{count['round']} round(s), {count['proposal']} design(s), {len(ux_verdicts.latest(suite))} verdict(s).")
    return "\n".join(lines)


def ask(suite: ux_config.Suite, conf: dict, kind: str, walk: str, focus: str) -> str:
    out = ux_team.request(suite, conf, kind, walk, focus)
    if "started" in out:
        return f"Started: {kind} {out['started']['version']} of {walk} (results/{ux_team.FOLDER[kind]}/{walk})."
    return (f"Queued as number {out['queued']} ({out['why']}). The open suite starts it as soon as it can: "
            "crissp/ux.sh opens it.")


def main(argv: list[str], suite: ux_config.Suite | None = None, run=None) -> int:
    suite = suite or ux_config.default_suite()
    cmd, args = (argv[0] if argv else ""), argv[1:]
    if cmd not in ("list", "status", "round", "propose", "shoot") or (cmd in ("round", "propose", "shoot") and not args):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        conf = ux_config.load(suite)
        if cmd == "list":
            print(listing(conf))
        elif cmd == "status":
            print(status(suite, conf))
        elif cmd == "shoot":
            code, text = ux_shoot.shoot(suite, conf, args[0], *([run] if run else []))
            print(text)
            return code
        else:
            print(ask(suite, conf, "round" if cmd == "round" else "proposal", args[0], " ".join(args[1:])))
    except ValueError as e:  # a wrong configuration, an unknown walk, the team busy with this very walk
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover — run by crissp/ux.sh; main() is tested
    sys.stdout, sys.stderr = ux_config.Speaking(sys.stdout), ux_config.Speaking(sys.stderr)  # F-04
    sys.exit(main(sys.argv[1:]))
