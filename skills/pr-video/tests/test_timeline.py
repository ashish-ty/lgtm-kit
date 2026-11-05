"""The schedule is frame-exact: clicks land when the cursor arrives, narration sets each beat's length."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import timeline as tl


def live(bid="level", hold=2.0, caption="12 rows", voice=None, crop=None):
    return {"id": bid, "do": "select", "hold": hold, "caption": caption, "voice": voice, "crop": crop, "shots": [
        {"image": f"{bid}-0.png", "cursor": [400, 200]},
        {"image": f"{bid}-1.png", "cursor": [400, 300]},
        {"image": f"{bid}-2.png", "cursor": None},
    ]}


def card(bid="c", do="code", hold=2.5, voice=None):
    return {"id": bid, "do": do, "hold": hold, "caption": None, "voice": voice, "card": {"file": "x.py", "rows": []}}


def manifest(*beats, **extra):
    return {"title": "Retry uploads", "pr": 42, "repo": "acme/infra", "base": "main", "head": "feat/retry",
            "totals": {"files": 3, "code": {"added": 10, "removed": 2}, "test": {"added": 5, "removed": 0},
                       "generated": {"added": 0, "removed": 0}},
            "review_points": ["Check the cap"], "beats": list(beats), **extra}


def test_title_comes_first_and_end_card_last():
    t = tl.build(manifest(live()))
    assert t["shots"][0]["from"] == t["title"]["duration"] == tl.frames(tl.TITLE_S)
    assert t["end"]["from"] == t["shots"][-1]["from"] + t["shots"][-1]["duration"]
    assert t["end"]["from"] + t["end"]["duration"] == t["total_frames"]


def test_title_card_names_the_pr_and_its_size():
    title = tl.build(manifest(card()))["title"]
    assert title["eyebrow"] == "PR #42 · acme/infra"
    assert title["subtitle"] == "feat/retry → main · 3 files · +15 −2"


def test_a_branch_without_a_pr_says_so():
    title = tl.build(manifest(card(), pr=None, repo=None))["title"]
    assert title["eyebrow"] == "Branch feat/retry"


def test_end_card_carries_the_review_points():
    assert tl.build(manifest(card()))["end"]["points"] == ["Check the cap"]


def test_shots_are_contiguous_across_cards_and_live_beats():
    t = tl.build(manifest(card("a"), live("b"), card("c", do="overview")))
    for prev, nxt in zip(t["shots"], t["shots"][1:]):
        assert nxt["from"] == prev["from"] + prev["duration"]
    assert [s["kind"] for s in t["shots"]] == ["code", "image", "image", "image", "overview"]


def test_a_card_is_one_shot_held_for_its_hold():
    shot = tl.build(manifest(card(hold=3)))["shots"][0]
    assert (shot["duration"], shot["card"], shot["image"]) == (tl.frames(3), {"file": "x.py", "rows": []}, None)


def test_narration_longer_than_the_hold_stretches_a_card():
    shot = tl.build(manifest(card(hold=2, voice={"src": "audio/c.wav", "seconds": 6.0})))["shots"][0]
    assert shot["duration"] == tl.frames(6.0 + tl.VOICE_TAIL_S)


def test_narration_stretches_only_the_result_of_a_live_beat():
    plain = tl.build(manifest(live(hold=1)))["shots"]
    voiced = tl.build(manifest(live(hold=1, voice={"src": "audio/l.wav", "seconds": 8.0})))["shots"]
    assert [s["duration"] for s in voiced[:-1]] == [s["duration"] for s in plain[:-1]]
    assert sum(s["duration"] for s in voiced) == tl.frames(8.0 + tl.VOICE_TAIL_S)


def test_short_narration_leaves_the_hold_alone():
    shot = tl.build(manifest(card(hold=4, voice={"src": "a.wav", "seconds": 1.0})))["shots"][0]
    assert shot["duration"] == tl.frames(4)


def test_each_voice_starts_with_its_beat():
    t = tl.build(manifest(card("a", voice={"src": "audio/a.wav", "seconds": 3.0}), live("b"),
                          card("c", voice={"src": "audio/c.wav", "seconds": 2.0})))
    starts = {s["beat"]: s["from"] for s in reversed(t["shots"])}
    assert t["audio"] == [{"src": "audio/a.wav", "from": starts["a"], "duration": tl.frames(3.0)},
                          {"src": "audio/c.wav", "from": starts["c"], "duration": tl.frames(2.0)}]


def test_click_lands_when_the_glide_ends_and_before_the_cut():
    t = tl.build(manifest(live()))
    first, move = t["shots"][0], t["moves"][0]
    assert move["click"] == move["end"] == first["from"] + tl.frames(tl.GLIDE_S)
    assert move["click"] < first["from"] + first["duration"]


def test_cursor_chains_from_one_target_to_the_next_across_a_card():
    t = tl.build(manifest(live("a"), card(), live("b")))
    assert t["moves"][0]["from"] == list(tl.CURSOR_HOME)
    for prev, nxt in zip(t["moves"], t["moves"][1:]):
        assert nxt["from"] == prev["to"]


def test_caption_shows_only_on_the_result():
    assert [s["caption"] for s in tl.build(manifest(live()))["shots"]] == [None, None, "12 rows"]


def test_a_hover_moves_without_a_click():
    beat = {"id": "h", "do": "hover", "hold": 1, "caption": None, "shots": [
        {"image": "h-0.png", "cursor": [10, 10], "click": False}, {"image": "h-1.png", "cursor": None}]}
    assert tl.build(manifest(beat))["moves"][0]["click"] is None


def test_in_between_frames_keep_their_own_length():
    beat = {"id": "t", "do": "type", "hold": 1, "caption": None, "shots": [
        {"image": "t-0.png", "cursor": [10, 10]}, {"image": "t-1.png", "cursor": None, "seconds": 0.12},
        {"image": "t-2.png", "cursor": None}]}
    assert tl.build(manifest(beat))["shots"][1]["duration"] == tl.frames(0.12)


def test_a_crop_frames_the_result_and_maps_the_cursor():
    crop = [960, 0, 960, 540]
    t = tl.build(manifest(live("a", crop=crop), live("b")))
    a = [s for s in t["shots"] if s["beat"] == "a"]
    assert [s["crop"] for s in a] == [None, None, crop]
    b_first = next(s for s in t["shots"] if s["beat"] == "b")
    assert b_first["crop"] is None  # cursor at x=400 is outside the carried crop
    inside = live("c")
    inside["shots"][0]["cursor"] = [1200, 100]
    t2 = tl.build(manifest(live("a", crop=crop), inside))
    c_first = next(s for s in t2["shots"] if s["beat"] == "c")
    assert c_first["crop"] == crop
    assert t2["moves"][2]["to"] == [480, 200]


def test_a_card_resets_the_carried_crop():
    t = tl.build(manifest(live("a", crop=[960, 0, 960, 540]), card(), live("b")))
    assert next(s for s in t["shots"] if s["beat"] == "b")["crop"] is None


def test_longer_than_three_minutes_is_refused_naming_the_longest_beats():
    beats = [card(f"c{i}", hold=20) for i in range(10)]
    beats[3] = card("long", hold=40)
    with pytest.raises(tl.LengthError, match=r"long \(40 s\)"):
        tl.check_length(tl.build(manifest(*beats)))
    tl.check_length(tl.build(manifest(card())))  # short is fine


def test_main_writes_the_timeline(tmp_path):
    import json
    (tmp_path / "manifest.json").write_text(json.dumps(manifest(card())))
    sys.argv = ["timeline.py", str(tmp_path)]
    tl.main()
    assert json.loads((tmp_path / "timeline.json").read_text())["fps"] == tl.FPS
