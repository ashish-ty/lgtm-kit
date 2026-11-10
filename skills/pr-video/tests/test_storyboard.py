"""The storyboard is refused before anything runs when a beat can't be carried out."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import storyboard as sb

DIFF = {"pr": {"number": 42, "title": "Retry uploads", "repo": "acme/infra", "base": "main", "head": "feat/retry"},
        "files": [{"path": "src/worker.py", "status": "modified", "kind": "code", "added": 30, "removed": 1,
                   "hunks": [{"old_start": 1, "new_start": 1, "context": "",
                              "rows": [{"kind": "+", "old": None, "new": n, "text": f"line {n}"}
                                       for n in range(1, 31)]}]},
                  {"path": "gone.py", "status": "deleted", "kind": "code", "added": 0, "removed": 2,
                   "hunks": [{"old_start": 1, "new_start": 0, "context": "",
                              "rows": [{"kind": "-", "old": 1, "new": None, "text": "a"},
                                       {"kind": "-", "old": 2, "new": None, "text": "b"}]}]}],
        "totals": {"files": 2}}


def board(beats: str, head: str = "") -> str:
    return f"""Prose for the reader.

```yaml
{head}
scenes:
  - id: one
    beats:
{beats}
```
"""


def parse(beats: str, head: str = "", **kw):
    return sb.parse(board(beats, head), diff=DIFF, **kw)


CODE = """      - id: c
        do: code
        file: src/worker.py
        lines: [1, 20]
        say: The worker now retries."""


def test_title_and_pr_come_from_the_diff_when_the_storyboard_leaves_them_out():
    b = parse(CODE)
    assert (b.title, b.pr, b.repo, b.base, b.head) == ("Retry uploads", 42, "acme/infra", "main", "feat/retry")


def test_the_storyboard_title_wins_over_the_pr_title():
    assert parse(CODE, head="title: Uploads survive a flaky store").title == "Uploads survive a flaky store"


def test_a_code_beat_carries_its_rows():
    beat = parse(CODE).beats[0]
    assert (beat.do, beat.file, beat.hunk, beat.lines, beat.say) == ("code", "src/worker.py", 0, (1, 20),
                                                                    "The worker now retries.")


def test_a_code_beat_for_a_file_outside_the_diff_is_refused_with_close_names():
    with pytest.raises(sb.StoryboardError, match="did you mean"):
        parse(CODE.replace("src/worker.py", "src/workers.py"))


def test_a_hunk_index_past_the_end_is_refused():
    with pytest.raises(sb.StoryboardError, match="hunk 3"):
        parse(CODE + "\n        hunk: 3")


def test_a_card_too_long_to_read_is_refused():
    with pytest.raises(sb.StoryboardError, match="30 rows"):
        parse(CODE.replace("        lines: [1, 20]\n", ""))


def test_a_range_that_shows_nothing_is_refused():
    with pytest.raises(sb.StoryboardError, match="no rows"):
        parse(CODE.replace("[1, 20]", "[200, 210]"))


def test_a_deleted_file_is_sliced_by_old_numbers():
    beat = parse(CODE.replace("src/worker.py", "gone.py").replace("[1, 20]", "[2, 2]")).beats[0]
    assert beat.lines == (2, 2)


def test_lines_must_be_a_first_last_pair():
    with pytest.raises(sb.StoryboardError, match=r"\[first, last\]"):
        parse(CODE.replace("[1, 20]", "[20, 1]"))


def test_overview_needs_nothing_more():
    assert parse("      - id: o\n        do: overview\n        say: Two files.").beats[0].do == "overview"


def test_code_beats_need_a_diff():
    with pytest.raises(sb.StoryboardError, match="diff.json"):
        sb.parse(board(CODE), diff=None)


LIVE = """      - id: open
        do: click
        target: {role: button, name: Upload}
        say: Uploading a file."""


def test_live_beats_need_an_app_and_a_start():
    with pytest.raises(sb.StoryboardError, match="`app`"):
        parse(LIVE)
    b = parse(LIVE, head="app: http://localhost:5173/\nstart: /files")
    assert (b.app, b.start, b.has_live) == ("http://localhost:5173", "/files", True)


def test_a_code_only_storyboard_has_no_live_beats():
    assert parse(CODE).has_live is False


@pytest.mark.parametrize("beat, problem", [
    ("      - id: x\n        do: fly", "`do` must be one of"),
    ("      - id: x\n        do: click", "target must be a mapping"),
    ("      - id: x\n        do: click\n        target: {role: button}", "needs a name"),
    ("      - id: x\n        do: click\n        target: {text: A, css: b}", "exactly one"),
    ("      - id: x\n        do: select\n        target: {label: L}", "needs `value`"),
    ("      - id: x\n        do: show\n        crop: [0, 0, 5000]", "outside"),
    ("      - id: x\n        do: show\n        caption: '{n} rows'", "does not define"),
    ("      - id: x\n        do: show\n        say: '" + "word " * 100 + "'", "characters of narration"),
])
def test_bad_live_beats_are_refused(beat, problem):
    with pytest.raises(sb.StoryboardError, match=problem):
        parse(beat, head="app: http://x\nstart: /")


def test_figures_fill_both_caption_and_narration():
    beat = parse("      - id: s\n        do: show\n        figures: {n: {text: Rows}}\n"
                 "        caption: '{n} rows'\n        say: 'It shows {n} rows.'", head="app: http://x\nstart: /").beats[0]
    assert sb.fill(beat.caption, {"n": "12"}) == "12 rows"
    assert sb.fill(beat.say, {"n": "12"}) == "It shows 12 rows."
    assert sb.fill(None, {}) is None


def test_narration_using_an_undefined_figure_is_refused():
    with pytest.raises(sb.StoryboardError, match="narration uses"):
        parse("      - id: s\n        do: show\n        say: 'It has {n}.'", head="app: http://x\nstart: /")


def test_duplicate_beat_ids_are_refused():
    with pytest.raises(sb.StoryboardError, match="duplicate"):
        parse(CODE + "\n" + CODE)


def test_exactly_one_yaml_block():
    with pytest.raises(sb.StoryboardError, match="exactly one"):
        sb.parse("no yaml here", diff=DIFF)


def test_review_points_are_kept_and_capped():
    head = "review_points: [a, b, c, d, e]"
    with pytest.raises(sb.StoryboardError, match="at most 4"):
        parse(CODE, head=head)
    assert parse(CODE, head="review_points: [Check the backoff cap]").review_points == ("Check the backoff cap",)


def test_private_values_and_dates_are_filled():
    beats = ("      - id: t\n        do: type\n        target: {placeholder: Search}\n"
             "        text: '${private.user} ${date:+2d}'")
    b = parse(beats, head="app: http://x\nstart: /", private={"user": "kim"}, today=date(2026, 11, 1))
    assert b.beats[0].text == "kim 2026-11-03"
    with pytest.raises(sb.StoryboardError, match="private.yaml"):
        parse(beats, head="app: http://x\nstart: /")


def test_estimate_counts_holds_and_speech():
    b = parse(CODE + "\n        hold: 1")
    assert sb.estimate_seconds(b) == pytest.approx(len("The worker now retries.") / sb.SPEECH_CHARS_PER_S)


def test_load_reads_diff_and_private_beside_the_file(tmp_path):
    import json
    (tmp_path / "diff.json").write_text(json.dumps(DIFF))
    (tmp_path / "storyboard.md").write_text(board(CODE))
    assert sb.load(tmp_path / "storyboard.md").beats[0].file == "src/worker.py"


def test_targets_lists_what_the_capture_will_look_for():
    b = parse("      - id: s\n        do: select\n        target: {label: Level}\n        value: Unit",
              head="app: http://x\nstart: /")
    assert sb.targets(b) == [("s", "label", "Level"), ("s", "option", "Unit")]


def test_a_tests_card_needs_test_files_in_the_diff():
    with pytest.raises(sb.StoryboardError, match="no test files"):
        parse("      - id: t\n        do: tests")


def test_layers_are_checked_and_kept():
    layers = "layers: [{name: API, paths: ['src/*']}]"
    assert parse(CODE, head=layers).layers == ({"name": "API", "paths": ["src/*"]},)
    with pytest.raises(sb.StoryboardError, match="layers"):
        parse(CODE, head="layers: [{name: API}]")


@pytest.mark.parametrize("text", ["returns an empty dict {}", "item {0}", "set } at the end", "open { here"])
def test_stray_braces_are_refused_before_capture(text):
    with pytest.raises(sb.StoryboardError, match=r"\{\{"):
        parse(f"      - id: s\n        do: show\n        caption: '{text}'", head="app: http://x\nstart: /")


def test_doubled_braces_show_as_one_brace():
    beat = parse("      - id: s\n        do: show\n        say: 'returns {{}}'", head="app: http://x\nstart: /").beats[0]
    assert sb.fill(beat.say, {}) == "returns {}"


def test_a_code_beat_on_a_binary_file_says_so():
    diff = {**DIFF, "files": [*DIFF["files"], {"path": "docs/logo.png", "status": "added", "binary": True,
                                                "kind": "code", "added": 0, "removed": 0, "hunks": []}]}
    with pytest.raises(sb.StoryboardError, match="binary file"):
        sb.parse(board("      - id: c\n        do: code\n        file: docs/logo.png"), diff=diff)
