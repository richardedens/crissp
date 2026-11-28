"""F-34: a project's frontend is linted with crissp's own tools (lib/frontend_lint.py, frontend-lint/): ESLint and
stylelint pinned at exact versions with their lockfile, installed once per toolkit into crissp's cache with npm ci, and
run with crissp's configs on the frontend's folder. The project's package.json and its files stay untouched. npm and the
tools are stand-ins here: no test reaches the network."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from gitrepo import git

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import frontend_lint

KIT = LIB.parent / "frontend-lint"
PINS = {
    "eslint": "9.39.5",
    "@eslint/js": "9.39.5",
    "typescript-eslint": "8.72.2",
    "typescript": "6.0.3",
    "globals": "17.14.0",
    "eslint-plugin-react-hooks": "7.1.1",
    "eslint-plugin-jsx-a11y": "6.10.2",
    "eslint-plugin-react": "7.37.5",
    "stylelint": "17.16.0",
    "stylelint-config-recommended": "18.0.0",
}


def test_the_toolkit_pins_every_tool_at_one_exact_version_and_its_lockfile_agrees():
    package = json.loads((KIT / "package.json").read_text())
    assert package["private"] is True and package["devDependencies"] == PINS
    lock = json.loads((KIT / "package-lock.json").read_text())
    assert lock["packages"][""]["devDependencies"] == PINS
    for name, version in PINS.items():
        assert lock["packages"][f"node_modules/{name}"]["version"] == version, name
    eslint = (KIT / "eslint.config.mjs").read_text()
    for name in set(PINS) - {"eslint", "typescript", "stylelint", "stylelint-config-recommended"}:
        assert f'from "{name}"' in eslint, name  # every ESLint package pinned is used by the config
    assert '"react/no-danger": "error"' in eslint and "react.configs" not in eslint  # React's plugin: no-danger only


def test_the_project_kit_lints_css_as_crissp_lints_its_own_mistakes_not_layout():
    """F-151: the kit extended stylelint's standard set: about 7,800 findings in one project's hand-written CSS, nearly
    all layout (one declaration per line, empty lines before rules) or descending specificity. Now it holds the rules
    crissp holds its own CSS to (F-96)."""
    kit = (KIT / "stylelint.config.mjs").read_text()
    own = (LIB.parent / "lint" / "stylelint.config.mjs").read_text()
    for config in (kit, own):
        assert 'extends: ["stylelint-config-recommended"]' in config and '"no-descending-specificity": null' in config
    assert "standard" not in kit


def test_react_hooks_are_held_to_their_two_rules_and_the_compiler_rules_are_opt_in():
    """F-151: the hooks plugin's recommended set (v7) brings the React Compiler's rules (set-state-in-effect, refs,
    immutability, purity, …): hundreds of findings in code that does not use the compiler. Without --react-compiler only
    rules-of-hooks and exhaustive-deps apply."""
    eslint = (KIT / "eslint.config.mjs").read_text()
    assert '"react-hooks/rules-of-hooks": "error", "react-hooks/exhaustive-deps": "error"' in eslint
    assert 'process.env.CRISSP_REACT_COMPILER === "1"\n    ? reactHooks.configs.flat.recommended' in eslint
    assert "jsxA11y.flatConfigs.recommended" in eslint and "tseslint.configs.recommended" in eslint


def test_a_project_that_uses_the_react_compiler_says_so_and_gets_its_rules(tmp_path, frontend):
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    assert npm.envs[1]["CRISSP_REACT_COMPILER"] == "0"
    npm = Npm()
    assert lint(tmp_path, npm, ["--react-compiler", "app/frontend"]) == 0
    assert [e["CRISSP_REACT_COMPILER"] for e in npm.envs] == ["1", "1"]  # installed already: eslint, stylelint


class Npm:
    """Stand-in for npm and the two tools: records each call (without its report file), npm ci makes the binaries it
    would install, and ESLint and stylelint write a JSON report as the real ones do, with the findings `found` names
    per file ({file: [rule, …]}). A tool in `fail` crashes: an exit code that means it did not run, and no report."""

    def __init__(self, fail: set[str] = frozenset(), found: dict[str, list[str]] | None = None):
        self.calls, self.envs, self.fail, self.found = [], [], fail, found or {}

    def __call__(self, argv: list[str], cwd: Path, env: dict | None = None) -> int:
        tool = Path(argv[0]).name
        rest = list(argv[1:])
        out = None
        if "--output-file" in rest:
            i = rest.index("--output-file")
            out = Path(rest[i + 1])
            del rest[i : i + 2]
        self.calls.append((tool, rest, Path(cwd)))
        self.envs.append(env)
        if tool == "npm":
            if "npm" in self.fail:
                return 1
            (Path(cwd) / "node_modules/.bin").mkdir(parents=True)
            return 0
        if tool in self.fail:
            return 2 if tool == "eslint" else 78
        files = [a for a in rest if not a.startswith("-") and (Path(cwd) / a).is_file()]
        mine = {f: self.found.get(f, []) for f in files}
        if tool == "eslint":
            report = [
                {
                    "filePath": str(Path(cwd) / f),
                    "messages": [{"ruleId": r, "line": 1, "column": 2, "message": "m"} for r in rules],
                }
                for f, rules in mine.items()
            ]
        else:
            report = [
                {
                    "source": str(Path(cwd) / f),
                    "warnings": [{"rule": r, "line": 3, "column": 4, "text": f"bad ({r})"} for r in rules],
                    "invalidOptionWarnings": [],
                }
                for f, rules in mine.items()
            ]
        out.write_text(json.dumps(report))
        return (1 if tool == "eslint" else 2) if any(mine.values()) else 0


def lint(tmp_path: Path, npm: Npm, argv: list[str] | None = None, which=lambda name: f"/usr/bin/{name}") -> int:
    return frontend_lint.main(
        ["app/frontend"] if argv is None else argv,
        {"CRISSP_CACHE": str(tmp_path / "cache")},
        run=npm,
        which=which,
        cwd=tmp_path,
    )


@pytest.fixture
def frontend(tmp_path):
    app = tmp_path / "app/frontend"
    (app / "src").mkdir(parents=True)
    (app / "package.json").write_text('{"name": "shop"}\n')
    (app / "src/main.tsx").write_text("export const a = 1;\n")
    (app / "src/app.css").write_text("a { color: red; }\n")
    return app


SOURCE = ["src/main.tsx"]
STYLE = ["src/app.css"]


def eslint_argv(place: Path, *files: str) -> list[str]:
    return ["--config", str(place / "eslint.config.mjs"), "--no-warn-ignored", "--format", "json", *files]


def stylelint_argv(place: Path, *files: str) -> list[str]:
    return [
        "--config",
        str(place / "stylelint.config.mjs"),
        "--config-basedir",
        str(place),
        "--allow-empty-input",
        "--formatter",
        "json",
        *files,
    ]


def test_the_tools_are_installed_once_then_both_run_on_the_frontend_with_crissps_configs(tmp_path, frontend, capsys):
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    place = frontend_lint.place({"CRISSP_CACHE": str(tmp_path / "cache")})
    assert place.parent == tmp_path / "cache/frontend-lint"
    assert npm.calls == [
        ("npm", ["ci", "--no-audit", "--no-fund", "--loglevel=error"], place),
        ("eslint", eslint_argv(place, *SOURCE), frontend),
        ("stylelint", stylelint_argv(place, *STYLE), frontend),
    ]
    for name in ("package.json", "package-lock.json", "eslint.config.mjs", "stylelint.config.mjs"):
        assert (place / name).read_text() == (KIT / name).read_text()
    assert "crissp's lint tools installed" in capsys.readouterr().out
    npm.calls.clear()
    assert lint(tmp_path, npm) == 0
    assert [tool for tool, _, _ in npm.calls] == ["eslint", "stylelint"]  # installed once
    assert (frontend / "package.json").read_text() == '{"name": "shop"}\n'  # the project's own files: untouched
    assert sorted(p.name for p in frontend.iterdir()) == ["package.json", "src"]


def test_git_ignored_build_output_and_build_folders_are_never_linted(tmp_path, frontend):
    """F-150: crissp's configs live in its cache, so their ignore patterns never matched a project's dist/ (stylelint
    reads them from the config's folder): thousands of findings in minified bundles. Now the tools get the project's
    own files only, as git lists them, without the build folders."""
    git(tmp_path, "init", "-q")
    for path in ("dist/assets/index.js", "dist/assets/index.css", "out/main.js", "node_modules/x/x.css", "build/b.js"):
        (frontend / path).parent.mkdir(parents=True, exist_ok=True)
        (frontend / path).write_text("var x\n")
    (frontend / ".gitignore").write_text("dist/\nout/\n")
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    place = frontend_lint.place({"CRISSP_CACHE": str(tmp_path / "cache")})
    assert npm.calls[1:] == [
        ("eslint", eslint_argv(place, *SOURCE), frontend),
        ("stylelint", stylelint_argv(place, *STYLE), frontend),
    ]
    for config in ("eslint.config.mjs", "stylelint.config.mjs"):
        assert "dist" not in (KIT / config).read_text()  # no pattern that only seems to ignore it


def test_a_frontend_without_code_or_styles_skips_that_tool_and_says_so(tmp_path, frontend, capsys):
    (frontend / "src/main.tsx").unlink()
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    assert [tool for tool, _, _ in npm.calls] == ["npm", "stylelint"]
    assert "no JavaScript or TypeScript to lint" in capsys.readouterr().out
    (frontend / "src/app.css").unlink()
    npm.calls.clear()
    assert lint(tmp_path, npm) == 0 and npm.calls == []
    assert "no CSS to lint" in capsys.readouterr().out


def test_many_files_are_linted_in_batches_and_one_red_batch_makes_the_step_red(tmp_path, frontend, monkeypatch):
    for n in range(30):
        (frontend / f"src/file-{n:02}.js").write_text("export {};\n")
    monkeypatch.setattr(frontend_lint, "LIMIT", 200)
    npm = Npm()
    assert lint(tmp_path, npm) == 0
    eslint = [argv for tool, argv, _ in npm.calls if tool == "eslint"]
    assert len(eslint) > 1
    assert sorted(f for argv in eslint for f in argv[len(eslint_argv(Path("/p"))) :]) == sorted(
        [*(f"src/file-{n:02}.js" for n in range(30)), *SOURCE]
    )

    npm = Npm(found={"src/file-29.js": ["no-undef"]})  # in the last batch: every batch's findings count
    assert lint(tmp_path, npm) == 1


def test_a_red_eslint_still_runs_stylelint_and_the_step_is_red(tmp_path, frontend, capsys):
    npm = Npm(found={"src/main.tsx": ["no-undef"]})
    assert lint(tmp_path, npm) == 1
    assert [tool for tool, _, _ in npm.calls] == ["npm", "eslint", "stylelint"]
    out = capsys.readouterr().out
    assert "src/main.tsx:1:2: error: m [no-undef]\n" in out and "Found 1 error." in out
    assert "crissp lint --baseline" in out  # how a project with code switches the lint on
    assert lint(tmp_path, Npm(found={"src/app.css": ["block-no-empty", "block-no-empty"]})) == 1
    assert "src/app.css:3:4: error: bad [block-no-empty]\n" in capsys.readouterr().out  # the rule said once


def test_a_tool_that_cannot_run_is_red_never_a_pass(tmp_path, frontend, capsys):
    """A crash (a broken config, a missing plugin) writes no report: red, with the tool named, never green."""
    for tool in ("eslint", "stylelint"):
        npm = Npm(fail={tool})
        assert lint(tmp_path, npm) == 1
        assert [t for t, _, _ in npm.calls][-2:] == ["eslint", "stylelint"]  # the other still runs
        assert f"{tool} could not run (exit {2 if tool == 'eslint' else 78})" in capsys.readouterr().out


def test_stylelint_s_invalid_options_are_a_problem(tmp_path, frontend, capsys):
    class Broken(Npm):
        def __call__(self, argv, cwd, env=None):
            code = super().__call__(argv, cwd, env)
            if Path(argv[0]).name == "stylelint":
                out = Path(argv[argv.index("--output-file") + 1])
                out.write_text(
                    json.dumps([{"source": "x.css", "warnings": [], "invalidOptionWarnings": [{"text": "bad"}]}])
                )
            return code

    assert lint(tmp_path, Broken()) == 1
    assert "frontend-lint: stylelint: bad" in capsys.readouterr().out


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
    assert lint(tmp_path, Npm(), ["--strict"]) == 2


def test_with_no_folder_it_lints_the_current_one(tmp_path, frontend):
    npm = Npm()
    assert (
        frontend_lint.main([], {"CRISSP_CACHE": str(tmp_path / "cache")}, run=npm, which=lambda n: n, cwd=frontend) == 0
    )
    assert npm.calls[-1][2] == frontend


def test_the_real_runner_runs_a_command_in_its_folder(tmp_path, capfd):
    assert frontend_lint.call([sys.executable, "-c", "import os; open('here', 'w')"], tmp_path) == 0
    assert (tmp_path / "here").exists()
    report = [sys.executable, "-c", "print('report'); import sys; print('why', file=sys.stderr)", "--output-file", "x"]
    assert frontend_lint.call(report, tmp_path) == 0
    out, err = capfd.readouterr()
    assert "report" not in out and "why" in err  # the report is in its file; why a tool failed stays in sight
    copy = [sys.executable, "-c", "import sys; print('[{}]', file=sys.stderr)", "--output-file", "x"]
    assert frontend_lint.call(copy, tmp_path) == 0
    assert capfd.readouterr().err == ""  # stylelint's copy of its report, on stderr: left out


def test_the_step_helper_runs_it_with_the_pinned_python(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "py").write_text('#!/usr/bin/env bash\necho "py $*"\n')
    (bin_ / "py").chmod(0o755)
    done = subprocess.run(
        ["bash", "-c", "frontend_lint"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "BASH_ENV": str(LIB / "steps.sh"), "PY": str(bin_ / "py")},
    )
    assert done.stdout == f"py {LIB / 'frontend_lint.py'}\n"


def test_a_reported_path_outside_the_folder_is_kept_as_it_is(tmp_path):
    found, _ = frontend_lint.from_eslint([{"filePath": "/elsewhere/a.js", "messages": [{"ruleId": None}]}], tmp_path)
    assert found == [{"file": "/elsewhere/a.js", "line": 0, "column": 0, "rule": "parse-error", "message": ""}]
