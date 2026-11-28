"""F-26: Vibe's trusted_folders.toml is read with tomllib and written in Vibe's own shape, in one place for init and
repair: never a duplicate, never invalid TOML, never a folder the user marked untrusted, never a file it does not know."""

import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import vibe

WIN = Path("C:\\Users\\x\\proj")


def db(home: Path) -> Path:
    return home / "trusted_folders.toml"


def lists(home: Path) -> dict:
    return tomllib.loads(db(home).read_text())


def test_home_is_vibe_home_else_dot_vibe():
    assert vibe.home({"VIBE_HOME": "/v"}) == Path("/v")
    assert vibe.home({}) == Path.home() / ".vibe"


def test_a_windows_path_is_added_once_however_often_it_runs(tmp_path):
    for _ in range(3):
        vibe.trust(tmp_path, WIN)
    assert lists(tmp_path) == {"trusted": [str(WIN)], "untrusted": []}
    assert "already trusts" in vibe.trust(tmp_path, WIN)
    assert vibe.state(tmp_path, WIN) == "trusted"


def test_vibes_own_forward_slash_entry_counts(tmp_path):
    db(tmp_path).write_text('trusted = [\n    "C:/Users/x/proj/",\n]\nuntrusted = []\n')
    assert vibe.state(tmp_path, WIN) == "trusted"


def test_a_one_line_list_stays_valid_toml_and_keeps_its_entries(tmp_path):
    db(tmp_path).write_text('trusted = ["/a"]\nuntrusted = ["/bad"]\n')
    assert vibe.trust(tmp_path, Path("/b")).startswith("trusted /b")
    assert lists(tmp_path) == {"trusted": ["/a", "/b"], "untrusted": ["/bad"]}
    assert db(tmp_path).read_text() == 'trusted = [\n    "/a",\n    "/b",\n]\nuntrusted = [\n    "/bad",\n]\n'


def test_an_untrusted_folder_stays_untrusted(tmp_path):
    before = 'trusted = []\nuntrusted = [\n    "/c",\n]\n'
    db(tmp_path).write_text(before)
    assert vibe.state(tmp_path, Path("/c")) == "untrusted"
    assert "marked untrusted" in vibe.trust(tmp_path, Path("/c"))
    assert db(tmp_path).read_text() == before


def test_a_file_it_does_not_know_is_left_alone(tmp_path):
    for text in ("trusted = [\n", 'trusted = "/a"\n', 'trusted = []\nother = 1\n', "trusted = [1]\n"):
        db(tmp_path).write_text(text)
        assert vibe.state(tmp_path, Path("/a")) == "unreadable"
        assert "left alone" in vibe.trust(tmp_path, Path("/a"))
        assert db(tmp_path).read_text() == text


def test_no_file_yet_and_missing_lists(tmp_path):
    assert vibe.state(tmp_path, Path("/a")) == "absent"
    vibe.trust(tmp_path, Path("/a"))
    assert lists(tmp_path) == {"trusted": ["/a"], "untrusted": []}
    db(tmp_path).write_text("untrusted = []\n")
    vibe.trust(tmp_path, Path("/b"))
    assert lists(tmp_path) == {"trusted": ["/b"], "untrusted": []}
    assert not (tmp_path / "trusted_folders.toml.tmp").exists()
