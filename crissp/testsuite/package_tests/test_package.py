"""The package is the product: the wheel that goes to PyPI installs, initialises a project in its own git repository, and
that project's full run is green. Built from this checkout with uv, installed into a throwaway venv, used in a
throwaway folder: nothing here touches this repository or the network beyond what uv needs to build."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
VERSION = (REPO / "VERSION").read_text().strip()


def run(cmd, cwd, env=None, check=True):
    done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise AssertionError(f"{cmd} → {done.returncode}\n{done.stdout}\n{done.stderr}")
    return done


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    if not shutil.which("uv"):
        pytest.skip("uv is not installed")
    out = tmp_path_factory.mktemp("dist")
    run(["uv", "build", "--wheel", "--out-dir", str(out)], REPO)
    wheels = list(out.glob("crissp-*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


@pytest.fixture(scope="module")
def crissp(wheel, tmp_path_factory):
    venv = tmp_path_factory.mktemp("venv")
    run(["uv", "venv", "--quiet", str(venv)], REPO)
    run(["uv", "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"), str(wheel)], REPO)
    return venv / "bin" / "crissp"


def test_the_wheel_carries_the_licences_and_the_engine_but_no_project_data(wheel):
    names = zipfile.ZipFile(wheel).namelist()
    dist = next(n.split("/")[0] for n in names if n.endswith(".dist-info/METADATA"))
    licences = {n.rsplit("/", 1)[-1] for n in names if n.startswith(f"{dist}/licenses/")}
    assert {"LICENSE", "NOTICE", "LICENSE-figtree.txt"} <= licences
    meta = zipfile.ZipFile(wheel).read(f"{dist}/METADATA").decode()
    assert "License-Expression: Apache-2.0" in meta and f"Version: {VERSION}" in meta
    assert "Requires-Dist" not in meta  # the engine is standard library only
    engine = "crissp/engine/"
    for needed in ("CRISSP.md", "check.sh", "check-all.sh", "testsuite/lib/check.py", "tool/server.py",
                   "uxsuite/cli.py", "look/look.css", "template/crissp/CLAUDE.md", "deploy/helm/app/Chart.yaml",
                   "deploy/terraform/main.tf", "deploy/check.sh"):
        assert engine + needed in names, needed
    for never in ("backlog/", "testsuite/results/", "uxsuite/results/", "testsuite/tests/", "testsuite/suites.json",
                  "testsuite/coverage-baseline.json", "testsuite/changes.json", "CLAUDE.md", "AGENTS.md"):
        assert not any(n.startswith(engine + never) for n in names), never
    assert not any("__pycache__" in n for n in names)


def test_crissp_says_its_version(crissp, tmp_path):
    assert run([str(crissp), "--version"], tmp_path).stdout.strip() == f"crissp {VERSION}"


def test_init_makes_a_crissp_project_that_is_green(crissp, tmp_path):
    project = tmp_path / "example"
    project.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "Example", "GIT_AUTHOR_EMAIL": "example@example.org",
           "GIT_COMMITTER_NAME": "Example", "GIT_COMMITTER_EMAIL": "example@example.org"}
    env.pop("CRISSP_ROOT", None)
    said = run([str(crissp), "init", "--yes", "--product", "Example", "--owner", "the product owner"], project, env).stdout
    assert (project / ".git").is_dir() and "git init" in said
    for made in ("CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "VERSION", ".gitignore", ".mcp.json", "crissp/CRISSP.md",
                 "crissp/CLAUDE.md", "crissp/backlog/FINDINGS.md", "crissp/testsuite/suites.json",
                 "crissp/uxsuite/team.json", "crissp/deploy/deploy.json", "crissp/deploy/helm/app/Chart.yaml",
                 "crissp/deploy/terraform/main.tf"):
        assert (project / made).is_file(), made
    text = "".join(p.read_text() for p in project.rglob("*") if p.is_file() and ".git/" not in str(p)
                   and p.suffix in {".md", ".json", ".yaml", ".tf", ""})
    assert "{{PRODUCT}}" not in text and "{{OWNER}}" not in text and "Example" in text
    mcp = json.loads((project / ".mcp.json").read_text())["mcpServers"]["crissp"]
    assert mcp["command"] == "uvx" and mcp["args"] == [f"crissp=={VERSION}", "mcp"]  # the project pins its crissp
    assert run(["git", "log"], project, env, check=False).returncode != 0  # nothing committed: the owner reviews first

    # a second init keeps what is there
    (project / "crissp" / "CLAUDE.md").write_text("ours\n")
    again = run([str(crissp), "init", "--yes", "--product", "Other"], project, env).stdout
    assert (project / "crissp" / "CLAUDE.md").read_text() == "ours\n" and "kept" in again

    # a tiny product, then the full run in its own repository
    (project / "src").mkdir()
    (project / "src" / "example.py").write_text("def double(x):\n    return 2 * x\n")
    (project / "tests").mkdir()
    (project / "tests" / "conftest.py").write_text('import sys\n\nsys.path.insert(0, "src")\n')
    (project / "tests" / "test_example.py").write_text(
        "from example import double\n\n\ndef test_double():\n    assert double(2) == 4\n")
    run(["git", "add", "-A"], project, env)
    run(["git", "commit", "-q", "-m", "CRISSP: adopt C.R.I.S.S.P."], project, env)  # the owner reviewed and committed
    full = run([str(crissp), "check-all"], project, env, check=False)
    assert full.returncode == 0, full.stdout + full.stderr
    assert (project / "crissp" / "testsuite" / "results").is_dir()


def test_mcp_answers_for_the_project_it_is_started_in(crissp, tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "CRISSP_ROOT"}  # as Claude Code starts it: in the project
    run([str(crissp), "init", "--yes", "--product", "Example", "--no-git"], project, env)
    (project / "crissp" / "backlog" / "FINDINGS.md").write_text(
        (project / "crissp" / "backlog" / "FINDINGS.md").read_text() + "| F-01 | here | only in this project | E1 |\n")
    hello = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "backlog", "arguments": {"id": "F-01"}}}) + "\n"
    out = subprocess.run([str(crissp), "mcp"], cwd=project, env=env, input=hello, capture_output=True, text=True, timeout=30)
    assert "only in this project" in out.stdout, out.stdout + out.stderr  # this project's backlog, not another's


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
