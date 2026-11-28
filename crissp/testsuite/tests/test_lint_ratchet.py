"""F-152: a project that already has code can switch the frontend lint on. `frontend_lint --baseline` writes what is
found now into crissp/testsuite/lint-baseline.json (per file its sha256 and its findings per rule); from then on an
unchanged file may keep up to its counts, a new or changed file is clean, and a green run with fewer findings shrinks
the baseline. It never grows. npm and the tools are stand-ins (test_frontend_lint.Npm): no test reaches the network."""

import json
import sys
from pathlib import Path

import pytest
from gitrepo import git
from test_frontend_lint import Npm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import frontend_lint
import lint_ratchet

OLD = {"src/old.js": ["no-undef", "no-undef", "no-empty"], "src/a.css": ["block-no-empty"]}


@pytest.fixture
def shop(tmp_path):
    front = tmp_path / "app/frontend"
    (front / "src").mkdir(parents=True)
    (front / "package.json").write_text("{}\n")
    for name in ("old.js", "clean.js", "a.css"):
        (front / "src" / name).write_text(f"/* {name} */\n")
    return tmp_path


def lint(root: Path, found: dict, *flags: str) -> int:
    return frontend_lint.main(
        [*flags, "app/frontend"],
        {"CRISSP_CACHE": str(root / "cache"), "CRISSP_ROOT": str(root)},
        run=Npm(found=found),
        which=lambda name: name,
        cwd=root,
    )


def baseline(root: Path) -> dict:
    return json.loads((root / lint_ratchet.BASELINE).read_text())["folders"]["app/frontend"]["files"]


def test_without_a_baseline_every_finding_blocks_and_the_baseline_switches_the_lint_on(shop, capsys):
    assert lint(shop, OLD) == 1
    assert "Found 4 errors." in capsys.readouterr().out
    assert lint(shop, OLD, "--baseline") == 0
    assert "baseline written for app/frontend: 4 findings in 2 files" in capsys.readouterr().out
    written = baseline(shop)
    assert written["src/old.js"]["rules"] == {"no-empty": 1, "no-undef": 2}
    assert written["src/old.js"]["sha256"] == lint_ratchet.digest(shop / "app/frontend/src/old.js")
    assert "src/clean.js" not in written
    assert lint(shop, OLD) == 0
    assert "nothing blocks; 4 more known in the baseline" in capsys.readouterr().out
    assert lint(shop, OLD, "--baseline") == 1  # it only shrinks
    assert "has a baseline already, and it only shrinks" in capsys.readouterr().out


def test_one_more_finding_of_a_rule_in_an_unchanged_file_blocks(shop, capsys):
    assert lint(shop, OLD, "--baseline") == 0
    more = {**OLD, "src/old.js": [*OLD["src/old.js"], "no-undef"]}  # say, a crissp update whose rule finds more
    assert lint(shop, more) == 1
    out = capsys.readouterr().out
    assert "(3 of no-undef, the baseline allows 2)" in out and "no-empty" not in out.split("Found")[0]
    assert "Found 3 errors; 2 more known in the baseline" in out


def test_a_new_or_changed_file_is_clean(shop, capsys):
    assert lint(shop, OLD, "--baseline") == 0
    (shop / "app/frontend/src/old.js").write_text("/* touched */\n")
    assert lint(shop, OLD) == 1
    assert "[no-undef] (a changed file is clean)" in capsys.readouterr().out
    (shop / "app/frontend/src/old.js").write_text("/* old.js */\n")
    (shop / "app/frontend/src/new.js").write_text("x\n")
    assert lint(shop, {**OLD, "src/new.js": ["no-undef"]}) == 1
    assert "src/new.js:1:2: error: m [no-undef] (a new file is clean)" in capsys.readouterr().out


def test_fewer_findings_shrink_the_baseline_and_it_never_grows_back(shop, capsys):
    assert lint(shop, OLD, "--baseline") == 0
    assert lint(shop, {"src/old.js": ["no-undef"]}) == 0  # one no-undef and the no-empty fixed, a.css clean
    assert "it shrank, commit crissp/testsuite/lint-baseline.json" in capsys.readouterr().out
    assert baseline(shop) == {
        "src/old.js": {"sha256": lint_ratchet.digest(shop / "app/frontend/src/old.js"), "rules": {"no-undef": 1}}
    }
    assert lint(shop, {"src/old.js": ["no-undef", "no-undef"]}) == 1  # the fixed one cannot come back
    before = (shop / lint_ratchet.BASELINE).read_text()
    assert lint(shop, {"src/old.js": ["no-undef"]}) == 0
    assert (shop / lint_ratchet.BASELINE).read_text() == before  # nothing moved: the file stays as it is
    assert lint(shop, {}) == 0
    assert baseline(shop) == {}


def test_no_baseline_is_written_from_a_lint_that_could_not_run(shop, capsys):
    assert (
        frontend_lint.main(
            ["--baseline", "app/frontend"],
            {"CRISSP_CACHE": str(shop / "cache"), "CRISSP_ROOT": str(shop)},
            run=Npm(fail={"eslint"}),
            which=lambda name: name,
            cwd=shop,
        )
        == 1
    )
    assert "no baseline written: the lint must run first" in capsys.readouterr().out
    assert not (shop / lint_ratchet.BASELINE).exists()


def test_a_partial_run_judges_its_files_and_leaves_the_baseline_alone(shop):
    front = shop / "app/frontend"
    known = lint_ratchet.baseline_of(front, [{"file": "src/old.js", "rule": "no-undef"}] * 2)
    one = [{"file": "src/old.js", "rule": "no-undef"}]
    assert lint_ratchet.judge(front, one, known, complete=False) == ([], 1, None)
    assert lint_ratchet.judge(front, one, known, complete=True)[2]["files"]["src/old.js"]["rules"] == {"no-undef": 1}


def test_the_project_is_crissp_root_else_the_git_repository_else_the_folder(tmp_path):
    folder = tmp_path / "app/frontend"
    folder.mkdir(parents=True)
    assert lint_ratchet.root_of(folder, {"CRISSP_ROOT": str(tmp_path)}) == tmp_path.resolve()
    assert lint_ratchet.root_of(folder, {}) == folder.resolve()
    git(tmp_path, "init", "-q")
    assert lint_ratchet.root_of(folder, {}) == tmp_path.resolve()
    assert lint_ratchet.key_of(folder, tmp_path.resolve()) == "app/frontend"
    assert lint_ratchet.key_of(tmp_path, tmp_path.resolve()) == "."
    assert lint_ratchet.key_of(tmp_path, folder.resolve()) == tmp_path.resolve().as_posix()


def test_a_baseline_that_is_not_an_object_names_nothing(tmp_path):
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    (tmp_path / lint_ratchet.BASELINE).write_text("[]\n")
    assert lint_ratchet.load(tmp_path) == {}
    assert lint_ratchet.digest(tmp_path / "gone.js") == ""
