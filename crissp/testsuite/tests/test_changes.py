"""crissp/testsuite/changes.json: every change says what was wrong, how it is fixed and which tests prove it, and those tests
exist. Known gaps are written down, not hidden."""

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "crissp" / "testsuite" / "changes.json"


def _test_dirs(root: Path) -> tuple[Path, ...]:
    """Where a change's tests may be: every step's test folders (crissp/testsuite/suites.json)."""
    sys.path.insert(0, str(ROOT / "crissp/testsuite/lib"))
    import project
    return tuple(root / t for s in project.load(root)["steps"] for t in s["tests"])


TEST_DIRS = _test_dirs(ROOT)
FRONTEND_TEST = (".test.ts", ".test.tsx")  # vitest's file names (a frontend's test folder)


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test")}


def _vitest_names(path: Path) -> set[str]:
    """The names given to it(…), test(…) and describe(…) in a vitest file (quoted with ', " or `)."""
    return {m.group(2) for m in re.finditer(r"\b(?:it|test|describe)(?:\.\w+)*\(\s*(['\"`])(.+?)\1", path.read_text())}


def find_test(ref: str, dirs=TEST_DIRS) -> bool:
    """`test_file` (a file in one of the test folders) or `test_file::test_name` (a test function in it). A frontend test
    is named by its file, `layout.test.ts`, or `layout.test.ts::the name given to it(…)`."""
    file, _, name = ref.partition("::")
    if file.endswith(FRONTEND_TEST):
        return any((d / file).is_file() and (not name or name in _vitest_names(d / file)) for d in dirs)
    for d in dirs:
        path = d / (file if file.endswith(".py") else f"{file}.py")
        if path.is_file() and (not name or name in _test_functions(path)):
            return True
    return False


def problems(data: dict, dirs=TEST_DIRS) -> list[str]:
    out = []
    if set(data) != {"changes", "gaps"}:
        out.append(f"changes.json has {sorted(data)}, expected ['changes', 'gaps']")
    seen = set()
    for i, c in enumerate(data.get("changes", [])):
        cid = c.get("id") or f"#{i}"
        for field in ("id", "title", "problem", "fix"):
            if not isinstance(c.get(field), str) or not c[field].strip():
                out.append(f"{cid}: '{field}' is missing or empty")
        if cid in seen:
            out.append(f"{cid}: the id is used twice")
        seen.add(cid)
        tests = c.get("tests")
        if not isinstance(tests, list) or not tests:
            out.append(f"{cid}: 'tests' names no test (test_file or test_file::test_name)")
            continue
        out += [f"{cid}: test {t!r} does not exist" for t in tests if not find_test(t, dirs)]
    if not all(isinstance(g, str) and g.strip() for g in data.get("gaps", [])):
        out.append("every gap is a sentence")
    return out


def test_every_change_has_its_proof_and_the_gaps_are_written_down():
    data = json.loads(MANIFEST.read_text())
    assert problems(data) == []
    assert data["gaps"]  # an honest list is never empty


def test_the_check_finds_what_is_missing(tmp_path):
    (tmp_path / "test_x.py").write_text("def test_one():\n    pass\n\nasync def test_two():\n    pass\n")
    good = {"id": "a", "title": "t", "problem": "p", "fix": "f", "tests": ["test_x", "test_x.py::test_two"]}
    assert problems({"changes": [good], "gaps": ["g"]}, [tmp_path]) == []
    bad = [{"id": "a", "title": "", "problem": "p", "fix": "f", "tests": ["test_x::test_three", "test_y"]},
           {"title": "t", "problem": "p", "fix": "f"}, {**good}]
    assert problems({"changes": bad, "gaps": [""], "other": 1}, [tmp_path]) == [
        "changes.json has ['changes', 'gaps', 'other'], expected ['changes', 'gaps']",
        "a: 'title' is missing or empty",
        "a: test 'test_x::test_three' does not exist",
        "a: test 'test_y' does not exist",
        "#1: 'id' is missing or empty",
        "#1: 'tests' names no test (test_file or test_file::test_name)",
        "a: the id is used twice",
        "every gap is a sentence",
    ]


@pytest.mark.parametrize("ref", ["test_impact", "test_gate.py::test_a_file_at_100_stays_at_100"])
def test_the_testsuite_s_own_tests_can_be_named(ref):
    assert find_test(ref)


def test_the_folders_are_the_steps_test_folders():
    assert TEST_DIRS == (ROOT / "crissp/testsuite/tests", ROOT / "crissp/uxsuite/tests", ROOT / "crissp/deploy/tests",
                         ROOT / "crissp/testsuite/package_tests",
                         ROOT / "crissp/testsuite/tests")  # the audit step runs from crissp/testsuite


def test_a_frontend_test_is_named_by_its_file_and_the_name_given_to_it(tmp_path):
    (tmp_path / "layout.test.ts").write_text(
        "describe('the wall', () => {\n  it(\"keeps a gap of 4 cm\", () => {});\n  test.each([1])(`fits ${1}`, () => {});\n"
        "  it.skip('later', () => {});\n});\n")
    for ref in ("layout.test.ts", "layout.test.ts::keeps a gap of 4 cm", "layout.test.ts::the wall",
                "layout.test.ts::later"):
        assert find_test(ref, [tmp_path]), ref
    assert not find_test("layout.test.ts::a gap of 5 cm", [tmp_path])
    assert not find_test("room.test.tsx", [tmp_path])


def test_the_manifest_is_this_repository_s_with_its_gaps():
    """This repository's own fixes, each with its proof, and an honest list of what is not proven yet; nothing of the
    products the framework came from stays in it."""
    data = json.loads(MANIFEST.read_text())
    assert isinstance(data["changes"], list) and len(data["gaps"]) >= 3
    text = json.dumps(data)
    assert not re.search(r"a[e]gis|cvew[a]tch|b[r]idge|sm[a]sh|py[o]dide|w[a]ndvol|\\bF[l]ow\\b", text, re.I)
