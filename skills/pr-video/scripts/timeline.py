"""Turn a capture manifest into the frame-exact schedule the Remotion composition draws.

Timing lives here rather than in the composition so it can be tested, and so the composition
is a pure function of this file: same manifest, same video.

A **card** beat (code, overview) is one shot drawn from data. A **live** beat's shots play in
order: every shot but the last carries the point the cursor moves to, and clicks unless it says
``click: false`` (a hover); the last shot is the result, held for the beat's ``hold`` with its
caption on. A beat's narration starts with the beat; when it runs longer than the beat, the
beat's last shot is held until it finishes.

A beat's ``crop`` frames its result. The shots before a result keep the framing the previous
beat left while the cursor's target is inside it, and show the whole screen otherwise. Cursor
points are written in video pixels, already mapped through each shot's framing.

**Subtitles** follow the narration: each voiced beat's ``say`` is cut into short cues at sentence,
then clause, then word breaks, and the clip's length is shared among them by their characters —
the voice reads at an even pace, so that lands close enough. A manifest with
``subtitles: false`` (``capture.py --no-subtitles``) has none; a silent video has nothing to subtitle.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FPS = 30
SIZE = (1920, 1080)
TITLE_S = 3.0
END_S = 4.0
GLIDE_S = 0.8
CLICK_S = 0.3
SETTLE_S = 0.25
PASSING_S = 0.6
VOICE_TAIL_S = 0.4  # breath after the last word, before the cut
MAX_LENGTH_S = 180
CURSOR_HOME = (960, 640)
MAX_CUE_CHARS = 84  # two lines of a subtitle, the usual broadcast limit
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
CLAUSE_BREAK = re.compile(r"(?<=[,;:\u2014])\s+")


class LengthError(ValueError):
    """The video runs past the agreed three minutes."""


def frames(seconds: float) -> int:
    return max(1, round(seconds * FPS))


def inside(point, crop) -> bool:
    x, y, w, h = crop
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def to_video(point, crop) -> list[int]:
    if not crop:
        return [point[0], point[1]]
    x, y, w, _ = crop
    scale = SIZE[0] / w
    return [round((point[0] - x) * scale), round((point[1] - y) * scale)]


def shot_crop(shot: dict, is_result: bool, beat_crop, carried):
    if is_result:
        return beat_crop
    point = shot.get("cursor")
    return carried if carried and (point is None or inside(point, carried)) else None


def voice_frames(beat: dict) -> int:
    voice = beat.get("voice")
    return frames(voice["seconds"] + VOICE_TAIL_S) if voice else 0


def stretch_last(shots: list[dict], needed: int) -> list[dict]:
    """Hold the last shot longer so the beat lasts at least ``needed`` frames."""
    short = needed - sum(s["duration"] for s in shots)
    if short <= 0:
        return shots
    return [*shots[:-1], {**shots[-1], "duration": shots[-1]["duration"] + short}]


def card_segment(beat: dict, start: int) -> list[dict]:
    duration = max(frames(beat["hold"]), voice_frames(beat))
    return [{"kind": beat["do"], "image": None, "card": beat["card"], "from": start, "duration": duration,
             "caption": beat.get("caption"), "beat": beat["id"], "crop": None}]


def live_segments(beat: dict, start: int, cursor, carried):
    """The beat's shots and cursor moves, and where the cursor ends up."""
    shots, moves, f = [], [], start
    last = len(beat["shots"]) - 1
    for i, shot in enumerate(beat["shots"]):
        crop = shot_crop(shot, i == last, beat.get("crop"), carried)
        point = to_video(shot["cursor"], crop) if shot.get("cursor") else None
        caption = None
        if i == last:
            duration, caption = frames(beat["hold"]), beat.get("caption")
        elif point:
            glide = frames(GLIDE_S)
            duration = glide + frames(CLICK_S) + frames(SETTLE_S)
            moves.append({"start": f, "end": f + glide, "from": list(cursor), "to": list(point),
                          "click": f + glide if shot.get("click", True) else None})
            cursor = (point[0], point[1])
        else:  # an in-between frame: typing, a filmed wait, or a screen passed through
            duration = frames(shot.get("seconds", PASSING_S))
        shots.append({"kind": "image", "image": shot["image"], "card": None, "from": f, "duration": duration,
                      "caption": caption, "beat": beat["id"], "crop": list(crop) if crop else None})
        f += duration
    return stretch_last(shots, voice_frames(beat)), moves, cursor


def _pack(pieces: list[str]) -> list[str]:
    """Join pieces, in order, into lines of at most ``MAX_CUE_CHARS``."""
    out, line = [], ""
    for piece in pieces:
        joined = f"{line} {piece}" if line else piece
        if len(joined) <= MAX_CUE_CHARS or not line:
            line = joined
        else:
            out.append(line)
            line = piece
    return [*out, line] if line else out


def _fit(sentence: str) -> list[str]:
    if len(sentence) <= MAX_CUE_CHARS:
        return [sentence]
    pieces = []
    for clause in CLAUSE_BREAK.split(sentence):
        pieces += [clause] if len(clause) <= MAX_CUE_CHARS else _pack(clause.split(" "))
    return _pack(pieces)


def cue_texts(text: str) -> list[str]:
    """Narration cut into subtitle cues: whole sentences where they fit, clauses or words where not."""
    flat = " ".join(text.split())
    return [cue for sentence in SENTENCE_BREAK.split(flat) if sentence for cue in _fit(sentence)]


def subtitles_for(text: str, start: int, length: int) -> list[dict]:
    """Cues back to back from ``start``, sharing ``length`` frames by how much each one says."""
    cues = cue_texts(text)
    total = sum(len(c) for c in cues) or 1
    out, said = [], 0
    for cue in cues:
        begin = start + round(length * said / total)
        said += len(cue)
        out.append({"from": begin, "duration": start + round(length * said / total) - begin, "text": cue})
    return [c for c in out if c["duration"] > 0]


def _clock(frame: int, fps: int) -> str:
    ms = round(frame * 1000 / fps)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(timeline: dict) -> str:
    """The subtitles as a SubRip file, for players and uploads that show captions as text."""
    fps = timeline["fps"]
    return "\n".join(f"{i}\n{_clock(c['from'], fps)} --> {_clock(c['from'] + c['duration'], fps)}\n{c['text']}\n"
                     for i, c in enumerate(timeline.get("subtitles") or [], start=1))


def title_card(manifest: dict) -> dict:
    pr, repo, head, base = (manifest.get(k) for k in ("pr", "repo", "head", "base"))
    eyebrow = " · ".join(p for p in (f"PR #{pr}" if pr else None, repo) if p) or (f"Branch {head}" if head else "")
    totals = manifest.get("totals") or {}
    parts = [f"{head} → {base}" if head and base else None]
    if totals:
        added = sum(totals.get(k, {}).get("added", 0) for k in ("code", "test", "generated"))
        removed = sum(totals.get(k, {}).get("removed", 0) for k in ("code", "test", "generated"))
        parts.append(f"{totals['files']} files · +{added} −{removed}")
    return {"from": 0, "duration": frames(TITLE_S), "eyebrow": eyebrow, "title": manifest["title"],
            "subtitle": " · ".join(p for p in parts if p) or None}


def build(manifest: dict) -> dict:
    shots, moves, audio, subtitles = [], [], [], []
    with_subtitles = manifest.get("subtitles", True)
    f, cursor, carried = frames(TITLE_S), CURSOR_HOME, None
    for beat in manifest["beats"]:
        if "card" in beat:
            segment, carried = card_segment(beat, f), None
        else:
            segment, beat_moves, cursor = live_segments(beat, f, cursor, carried)
            moves += beat_moves
            carried = beat.get("crop")
        if beat.get("voice"):
            audio.append({"src": beat["voice"]["src"], "from": f, "duration": frames(beat["voice"]["seconds"])})
            if with_subtitles and beat.get("say"):
                subtitles += subtitles_for(beat["say"], f, audio[-1]["duration"])
        shots += segment
        f += sum(s["duration"] for s in segment)
    end = frames(END_S)
    return {"fps": FPS, "width": SIZE[0], "height": SIZE[1], "total_frames": f + end,
            "title": title_card(manifest),
            "end": {"from": f, "duration": end, "points": list(manifest.get("review_points") or [])},
            "shots": shots, "moves": moves, "audio": audio, "subtitles": subtitles}


def seconds(timeline: dict) -> float:
    return timeline["total_frames"] / timeline["fps"]


def check_length(timeline: dict) -> None:
    """Refuse past three minutes, naming the beats that cost the most."""
    total = seconds(timeline)
    if total <= MAX_LENGTH_S:
        return
    per_beat: dict[str, int] = {}
    for shot in timeline["shots"]:
        per_beat[shot["beat"]] = per_beat.get(shot["beat"], 0) + shot["duration"]
    longest = sorted(per_beat.items(), key=lambda kv: -kv[1])[:3]
    named = ", ".join(f"{b} ({d / timeline['fps']:.0f} s)" for b, d in longest)
    raise LengthError(f"the video runs {total:.0f} s, past the {MAX_LENGTH_S} s limit — cut or shorten beats; "
                      f"longest: {named}")


def main() -> None:
    captures = Path(sys.argv[1])
    timeline = build(json.loads((captures / "manifest.json").read_text()))
    (captures / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False))
    print(f"timeline: {seconds(timeline):.1f} s, {len(timeline['shots'])} shots")


if __name__ == "__main__":
    main()
