"""F-31: a project's frontend is linted with crissp's own tools (lib/frontend_lint.py, frontend-lint/): ESLint and
stylelint pinned at exact versions with their lockfile, installed once per toolkit into crissp's cache with npm ci, and
run with crissp's configs on the frontend's folder. The project's package.json and its files stay untouched. npm and the
tools are stand-ins here: no test reaches the network."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import frontend_lint  # noqa: E402

KIT = LIB.parent / "frontend-lint"
PINS = {"eslint": "9.39.5", "@eslint/js": "9.39.5", "typescript-eslint": "8.72.2", "typescript": "6.0.3",
        "globals": "17.14.0", "eslint-plugin-react-hooks": "7.1.1", "eslint-plugin-jsx-a11y": "6.10.2",
        "eslint-plugin-react": "7.37.5", "stylelint": "17.16.0", "stylelint-config-standard": "40.0.0"}


def test_the_toolkit_pins_every_tool_at_one_exact_version_and_its_lockfile_agrees():
    package = json.loads((KIT / "package.json").read_text())
    assert package["private"] is True and package["devDependencies"] == PINS
    lock = json.loads((KIT / "package-lock.json").read_text())
    assert lock["packages"][""]["devDependencies"] == PINS
    for name, version in PINS.items():
        assert lock["packages"][f"node_modules/{name}"]["version"] == version, name
    eslint = (KIT / "eslint.config.mjs").read_text()
    for name in set(PINS) - {"eslint", "typescript", "stylelint", "stylelint-config-standard"}:
        assert f'from "{name}"' in eslint, name  # every ESLint package pinned is used by the config
    assert '"react/no-danger": "error"' in eslint and "react.configs" not in eslint  # React's plugin: no-danger only
    assert '"stylelint-config-standard"' in (KIT / "stylelint.config.mjs").read_text()


class Npm:
    """Stand-in for npm and the two tools: records each call, and npm ci makes the binaries it would install."""

    def __init__(self, fail: set[str] = frozenset()):
        self.calls, self.fail = [], fail

    def __call__(self, argv: list[str], cwd: Path) -> int:
        tool = Path(argv[0]).name
        self.calls.append((tool, argv[1:], Path(cwd)))
        if tool == "npm" and "npm" not in self.fail:
            (Path(cwd) / "node_modules/.bin").mkdir(parents=True)
        return 1 if tool in self.fail else 0


def lint(tmp_path: Path, npm: Npm, argv: list[str] | None = None, which=lambda name: f"/usr/bin/{name}") -> int:
    return frontend_lint.main(["app/frontend"] if argv is None else argv,
                              {"CRISSP_CACHE": str(tmp_path / "cache")}, run=npm, which=which, cwd=tmp_path)


@pytest.fixture
def frontend(tmp_path):
    app = tmp_path / "app/frontend"
    app.mkdir(parents=True)
    (app / "package.json").write_text('{"name": "shop"}\n')
    return app


def test_the_tools_are_installed_once_then_both_run_on_the_frontend_with_crissps_configs(tmp_path, frontend, capsys):
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    place = frontend_lint.place({"CRISSP_CACHE": str(tmp_path / "cache")})
    assert place.parent == tmp_path / "cache/frontend-lint"
    assert npm.calls == [
        ("npm", ["ci", "--no-audit", "--no-fund", "--loglevel=error"], place),
        ("eslint", ["--config", str(place / "eslint.config.mjs"), "--max-warnings", "0", "."], frontend),
        ("stylelint", ["--config", str(place / "stylelint.config.mjs"), "--config-basedir", str(place),
                       "--allow-empty-input", "**/*.css"], frontend)]
    for name in ("package.json", "package-lock.json", "eslint.config.mjs", "stylelint.config.mjs"):
        assert (place / name).read_text() == (KIT / name).read_text()
    assert "crissp's lint tools installed" in capsys.readouterr().out
    npm.calls.clear()
    assert lint(tmp_path, npm) == 0
    assert [tool for tool, _, _ in npm.calls] == ["eslint", "stylelint"]  # installed once
    assert (frontend / "package.json").read_text() == '{"name": "shop"}\n'  # the project's own files: untouched
    assert sorted(p.name for p in frontend.iterdir()) == ["package.json"]


def test_a_red_eslint_still_runs_stylelint_and_the_step_is_red(tmp_path, frontend):
    npm = Npm(fail={"eslint"})
    assert lint(tmp_path, npm) == 1
    assert [tool for tool, _, _ in npm.calls] == ["npm", "eslint", "stylelint"]
    assert lint(tmp_path, Npm(fail={"stylelint"})) == 1


def test_a_failed_install_is_tried_again_next_time(tmp_path, frontend, capsys):
    assert lint(tmp_path, Npm(fail={"npm"})) == 1
    assert "npm ci failed" in capsys.readouterr().out
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    assert npm.calls[0][0] == "npm"


def test_another_toolkit_is_another_place_in_the_cache(tmp_path, monkeypatch):
    env = {"CRISSP_CACHE": str(tmp_path)}
    before = frontend_lint.place(env)
    other = tmp_path / "kit"
    other.mkdir()
    for name in frontend_lint.FILES:
        (other / name).write_text((KIT / name).read_text())
    (other / "package.json").write_text("{}")
    monkeypatch.setattr(frontend_lint, "KIT", other)
    assert frontend_lint.place(env) != before  # a crissp update with other pins installs them, never mixes them


def test_the_cache_is_crissp_cache_else_xdg_cache_home_else_home():
    assert frontend_lint.cache({"CRISSP_CACHE": "/c", "XDG_CACHE_HOME": "/x", "HOME": "/h"}) == Path("/c")
    assert frontend_lint.cache({"XDG_CACHE_HOME": "/x", "HOME": "/h"}) == Path("/x/crissp")
    assert frontend_lint.cache({"HOME": "/h"}) == Path("/h/.cache/crissp")


def test_without_npm_or_a_frontend_it_says_so(tmp_path, frontend, capsys):
    assert lint(tmp_path, Npm(), which=lambda name: None) == 1
    assert "npm is missing" in capsys.readouterr().out
    assert lint(tmp_path, Npm(), ["app/gone"]) == 1
    assert "app/gone is not a folder" in capsys.readouterr().out
    assert lint(tmp_path, Npm(), ["a", "b"]) == 2
    assert "usage" in capsys.readouterr().out


def test_with_no_folder_it_lints_the_current_one(tmp_path, frontend):
    npm = Npm()
    assert frontend_lint.main([], {"CRISSP_CACHE": str(tmp_path / "cache")}, run=npm, which=lambda n: n,
                              cwd=frontend) == 0
    assert npm.calls[-1][2] == frontend


def test_the_real_runner_runs_a_command_in_its_folder(tmp_path):
    assert frontend_lint.call([sys.executable, "-c", "import os; open('here', 'w')"], tmp_path) == 0
    assert (tmp_path / "here").exists()


def test_the_step_helper_runs_it_with_the_pinned_python(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "py").write_text('#!/usr/bin/env bash\necho "py $*"\n')
    (bin_ / "py").chmod(0o755)
    done = subprocess.run(["bash", "-c", "frontend_lint"], capture_output=True, text=True, check=False,
                          env={"PATH": "/usr/bin:/bin", "BASH_ENV": str(LIB / "steps.sh"), "PY": str(bin_ / "py")})
    assert done.stdout == f"py {LIB / 'frontend_lint.py'}\n"
