"""Cards carry exactly what the composition draws: no more rows or columns than fit."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cards
import storyboard as sb


def file(path, kind="code", added=1, removed=0, rows=None, status="modified"):
    rows = rows or [{"kind": "+", "old": None, "new": 1, "text": "x"}]
    return {"path": path, "old_path": path, "status": status, "kind": kind, "added": added, "removed": removed,
            "hunks": [{"old_start": 1, "new_start": 1, "context": "def f():", "rows": rows}]}


def diff(*files):
    return {"files": list(files), "totals": {"files": len(files)}}


def test_code_card_carries_the_rows_and_where_they_come_from():
    rows = [{"kind": " ", "old": 1, "new": 1, "text": "\tindented"},
            {"kind": "+", "old": None, "new": 2, "text": "y" * 200}]
    d = diff(file("src/a.py", rows=rows))
    card = cards.card_for(sb.Beat(id="c", scene="s", do="code", file="src/a.py"), d)
    assert (card["file"], card["context"], card["hunk"], card["hunks"]) == ("src/a.py", "def f():", 0, 1)
    assert card["rows"][0]["text"] == "    indented"
    assert len(card["rows"][1]["text"]) == cards.MAX_COLS and card["rows"][1]["text"].endswith("…")
    assert rows[0]["text"] == "\tindented"  # the diff is not changed


def overview(d, layers=()):
    return cards.card_for(sb.Beat(id="o", scene="s", do="overview"), d, layers)


def test_overview_groups_by_kind_biggest_first():
    d = diff(file("uv.lock", kind="generated", added=500), file("tests/t.py", kind="test", added=9),
             file("small.py", added=1), file("big.py", added=40, removed=3))
    card = overview(d)
    assert [(g["name"], [f["path"] for f in g["files"]]) for g in card["groups"]] == [
        ("code", ["big.py", "small.py"]), ("tests", ["tests/t.py"]), ("generated", ["uv.lock"])]
    assert card["groups"][0]["added"] == 41 and card["groups"][0]["removed"] == 3
    assert "hunks" not in card["groups"][0]["files"][0]


def test_overview_groups_by_the_layers_the_storyboard_names():
    d = diff(file("backend/api/x.py", added=5), file("frontend/src/App.tsx", added=7), file("README.md", added=1))
    card = overview(d, ({"name": "API", "paths": ["backend/*"]}, {"name": "UI", "paths": ["frontend/*"]}))
    assert [(g["name"], g["added"]) for g in card["groups"]] == [("API", 5), ("UI", 7), ("other", 1)]
    assert [g["colour"] for g in card["groups"]] == [0, 1, "other"]


def test_overview_keeps_what_fits_and_counts_the_rest():
    d = diff(*[file(f"f{i}.py") for i in range(cards.MAX_OVERVIEW_FILES + 5)])
    group = overview(d)["groups"][0]
    assert (len(group["files"]), group["more"]) == (cards.MAX_OVERVIEW_FILES, 5)


def test_tests_card_names_the_tests_each_file_adds():
    py = file("tests/test_w.py", kind="test", added=3, rows=[
        {"kind": "+", "old": None, "new": 1, "text": "def test_retries_three_times():"},
        {"kind": "+", "old": None, "new": 2, "text": "async def test_gives_up():"},
        {"kind": "-", "old": 3, "new": None, "text": "def test_removed_one():"}])
    js = file("web/upload.test.ts", kind="test", added=2, rows=[
        {"kind": "+", "old": None, "new": 1, "text": "  it('shows the retry count', () => {"},
        {"kind": "+", "old": None, "new": 2, "text": '  test.only("keeps the file", async () => {'}])
    go = file("w_test.go", kind="test", added=1, rows=[{"kind": "+", "old": None, "new": 1,
                                                        "text": "func TestBackoff(t *testing.T) {"}])
    card = cards.card_for(sb.Beat(id="t", scene="s", do="tests"), diff(py, js, go, file("w.py")))
    assert [f["path"] for f in card["files"]] == ["tests/test_w.py", "web/upload.test.ts", "w_test.go"]
    assert card["files"][0]["names"] == ["test_retries_three_times", "test_gives_up"]
    assert card["files"][1]["names"] == ["shows the retry count", "keeps the file"]
    assert card["files"][2]["names"] == ["TestBackoff"]
    assert card["total_names"] == 5


def test_live_beats_have_no_card():
    assert cards.card_for(sb.Beat(id="l", scene="s", do="show"), diff()) is None
