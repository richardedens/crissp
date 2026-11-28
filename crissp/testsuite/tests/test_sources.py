"""F-150: a lint or a scan looks at a project's own files, never at its build output. lib/sources.py lists them: what
git tracks or would track (its .gitignore counts, wherever it is), without the common build folders (dist, build,
node_modules, .next, coverage, …) even where nothing ignores them. Without git, the folder is walked, the same build
folders left out. A sample project with a git-ignored dist/ shows it."""

import sys
from pathlib import Path

import pytest
from gitrepo import git

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sources


def write(root: Path, *paths: str) -> None:
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("x\n")


OWN = ("src/main.js", "src/app.css", "src/view.tsx", "src/deep/dist.js")
BUILT = (
    "dist/assets/index.js",
    "dist/assets/index.css",
    "out/index.js",
    "node_modules/react/index.js",
    "build/main.js",
    ".next/server/page.js",
    "coverage/lcov-report/prettify.js",
    "packages/ui/dist/index.css",
)


@pytest.fixture
def shop(tmp_path):
    """A frontend in a git repository: its own code, and build output that .gitignore names (dist/, out/) or that is
    in a build folder nothing ignores (node_modules/, build/, .next/, coverage/, a package's dist/)."""
    git(tmp_path, "init", "-q")
    front = tmp_path / "app/frontend"
    write(front, *OWN, *BUILT)
    (front / ".gitignore").write_text("dist/\nout/\n")
    git(tmp_path, "add", "app/frontend/src", "app/frontend/.gitignore")
    git(tmp_path, "commit", "-q", "-m", "shop")
    return front


def test_only_the_projects_own_files_are_listed_never_its_build_output(shop):
    assert sources.files(shop, (".js", ".tsx", ".css")) == sorted(OWN)
    assert sources.files(shop, (".css",)) == ["src/app.css"]


def test_a_new_file_git_does_not_ignore_is_listed_and_a_deleted_one_is_not(shop):
    write(shop, "src/new.js")
    (shop / "src/main.js").unlink()
    assert sources.files(shop, (".js",)) == ["src/deep/dist.js", "src/new.js"]


def test_without_git_the_folder_is_walked_without_the_build_folders(tmp_path):
    write(tmp_path, *OWN, *BUILT, ".git/hooks/x.js")
    assert sources.files(tmp_path, (".js", ".tsx", ".css")) == sorted([*OWN, "out/index.js"])


def test_a_build_folder_is_one_by_its_name_anywhere_in_the_path():
    assert sources.built("packages/ui/dist/a.js") and sources.built("node_modules/x.js")
    assert not sources.built("src/dist.js") and not sources.built("src/distance/a.js")


def test_a_long_list_is_split_into_command_lines_that_stay_short():
    names = [f"src/file-{n:04}.js" for n in range(3000)]
    batches = sources.batches(names, limit=10_000)
    assert [n for batch in batches for n in batch] == names and len(batches) > 1
    assert all(sum(len(n) + 1 for n in batch) <= 10_000 for batch in batches)
    assert sources.batches([], limit=10) == []


def test_the_staged_files_of_a_folder_come_from_the_hook(tmp_path, monkeypatch, capsys):
    """F-154: the hook writes the staged paths (relative to the project) into the file CRISSP_STAGED names."""
    listed = tmp_path / "staged"
    listed.write_text("app/frontend/src/a.js\napp/backend/x.py\napp/frontend/b.css\n\n")
    env = {"CRISSP_STAGED": str(listed), "CRISSP_ROOT": str(tmp_path)}
    front = tmp_path / "app/frontend"
    assert sources.staged(front, env) == {"src/a.js", "b.css"}
    assert sources.staged(tmp_path, env) == {"app/frontend/src/a.js", "app/backend/x.py", "app/frontend/b.css"}
    assert sources.staged(front, {}) is None  # not the hook: everything
    front.mkdir(parents=True)
    monkeypatch.chdir(front)
    assert sources.main(["staged", ".js", ".css"], env) == 0
    assert capsys.readouterr().out == "b.css\nsrc/a.js\n"
    assert sources.main(["staged", ".js"], {}) == 1  # outside the hook there is no staged list
    assert sources.main([], env) == 2
