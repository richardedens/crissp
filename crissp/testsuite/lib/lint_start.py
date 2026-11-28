"""The frontend lint switched on without effort (F-155): every frontend_lint step gets its lint baseline.

    crissp lint --baseline                          (re)write the baseline of every frontend_lint step, no paths needed
    python3 crissp/testsuite/lib/lint_start.py [--redo]

crissp repair --yes and crissp init write the baseline of each frontend_lint step that has none yet (start()), so a
project that already has code is green from the first run and its findings only go down from there
(lib/lint_ratchet.py). --redo (crissp lint --baseline) writes every one again from what the lint finds now: an honest
reset, said, never done by a run. Each step runs as its suites.json says (its folder, --react-compiler).
Exit 0: every baseline is there; 1: one could not be written (the lint could not run: npm, the network); 2: arguments.
"""

import os
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frontend_lint
import lint_ratchet
import project


def lint_steps(root: Path) -> list[tuple[dict, list[str], Path]]:
    """Each frontend_lint step that is there now: the step, its arguments and the folder it lints."""
    try:
        steps = project.steps(project.load(root), root)
    except project.ConfigError:
        return []  # crissp repair says what is wrong with suites.json
    out = []
    for step in steps:
        words = shlex.split(step["run"])
        if words[:1] != ["frontend_lint"]:
            continue
        args = words[1:]
        folders = [a for a in args if not a.startswith("-")]
        out.append((step, args, (root / step["dir"] / (folders[0] if folders else "")).resolve()))
    return out


def pending(root: Path) -> list[str]:
    """The folders of frontend_lint steps without a baseline."""
    have = lint_ratchet.load(root)
    return [lint_ratchet.key_of(f, root) for _, _, f in lint_steps(root) if lint_ratchet.key_of(f, root) not in have]


def start(root: Path, env: dict, redo: bool = False, run=frontend_lint.call, which=shutil.which) -> int:
    """Write the baseline of every frontend_lint step that has none (redo: of every one). 1 when one failed."""
    root = root.resolve()
    tool_env = {k: v for k, v in env.items() if k != "CRISSP_STAGED"} | {"CRISSP_ROOT": str(root)}
    failed = 0
    for step, args, folder in lint_steps(root):
        key = lint_ratchet.key_of(folder, root)
        folders = lint_ratchet.load(root)
        if key in folders and not redo:
            continue
        if key in folders:
            del folders[key]
            lint_ratchet.save(root, folders)
        print(f"crissp lint: {step['label']}: the lint baseline of {key}")
        if frontend_lint.main(["--baseline", *args], tool_env, run=run, which=which, cwd=root / step["dir"]) != 0:
            print(f"crissp lint: no baseline for {key} yet; crissp lint --baseline writes it once the lint can run")
            failed += 1
    return 1 if failed else 0


def main(argv: list[str], env: dict) -> int:
    if argv not in ([], ["--redo"]):
        print("usage: lint_start.py [--redo]   (crissp lint --baseline)")
        return 2
    root = Path(env.get("CRISSP_ROOT") or os.getcwd())
    if not lint_steps(root):
        print("crissp lint: no frontend_lint step here (crissp/testsuite/suites.json): no baseline to write")
        return 0
    return start(root, env, redo=argv == ["--redo"])


if __name__ == "__main__":  # pragma: no cover — run by crissp lint --baseline; main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
