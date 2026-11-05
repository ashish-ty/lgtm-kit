# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.45", "pyyaml>=6", "pillow>=10", "kokoro-onnx>=0.4", "edge-tts>=6.1",
#                 "tinytag>=2.1"]
# ///
"""Carry out a storyboard: film its live beats, cut its cards from the diff, speak its narration.

    uv run capture.py <video folder>/storyboard.md [--silent] [--voice auto|kokoro|edge] [--allow-edge]

Writes, beside the storyboard, ``captures/``: a 2x still per live shot, ``audio/`` (one clip per
narrated beat), ``manifest.json`` (what each beat shows), ``timeline.json`` (the frame schedule
Remotion draws) and ``contact-sheet.png``. A browser opens only when the storyboard has live
beats; a code-only video needs no running app.

It stops — and says which beat and why — rather than film something other than what the
storyboard says. A live target that isn't on screen is either a naming mistake (check
``catalogue.json``) or a **finding**: the PR doesn't do what the storyboard expected it to.
It also refuses a video longer than three minutes.

Clicks land on the exact point the synthetic cursor is drawn at, so the video shows the click
that really happened.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import cards
import contact_sheet
import locators
import storyboard as sb
import timeline
import voice
from playwright.sync_api import Locator, Page
from session import SessionError, open_page, require_app, wait_idle

OPTION_MS = 350
TYPING_CHARS = 4         # a still every few characters, so the text is seen being typed
TYPING_FRAME_S = 0.12
FILM_FRAME_S = 0.45      # each still taken during a wait shows this long: the wait, sped up
FILM_MAX = 40
WAIT_FOR_TIMEOUT_MS = 180_000


class Recorder:
    """Saves numbered stills for one beat and the cursor point each one aims at."""

    def __init__(self, page: Page, shots_dir: Path, beat_id: str):
        self.page, self.dir, self.beat, self.shots = page, shots_dir, beat_id, []

    def shot(self, cursor: list[int] | None = None, click: bool = True, seconds: float | None = None) -> None:
        name = f"{self.beat}-{len(self.shots)}.png"
        self.page.screenshot(path=str(self.dir / name), type="png", animations="disabled", caret="hide")
        entry = {"image": f"shots/{name}", "cursor": cursor, "click": click}
        self.shots.append(entry if seconds is None else {**entry, "seconds": seconds})


def center(loc: Locator, at: list[float] | None = None) -> list[int]:
    """Where the cursor lands: the middle, or ``at`` — a fractional point inside the box."""
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    fx, fy = at or (0.5, 0.5)
    return [round(box["x"] + box["width"] * fx), round(box["y"] + box["height"] * fy)]


def chevron_end(loc: Locator) -> list[int]:
    """Where to open a multi-select: its chips carry remove buttons, so never the middle."""
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    return [round(box["x"] + box["width"] - 12), round(box["y"] + box["height"] / 2)]


def pick(page: Page, rec: Recorder, value: str, label: str | None, board: sb.Storyboard, settle: bool) -> None:
    point = center(locators.option(page, value, label))
    rec.shot(cursor=point)
    page.mouse.click(*point)
    if settle:
        wait_idle(page, board.busy, board.settle_ms)
    else:
        page.wait_for_timeout(OPTION_MS)


def close_dropdown(page: Page, label: str | None) -> None:
    page.keyboard.press("Escape")
    if label:  # a click outside closes the ones Escape does not; it is not filmed
        page.locator("label").filter(has_text=locators.exact(label)).first.click()


def type_text(page: Page, target: Locator, beat: sb.Beat, rec: Recorder) -> None:
    if target.evaluate("e => e.type === 'date'"):
        target.fill(beat.text.strip())  # a date field takes YYYY-MM-DD and shows it in its own format
        return
    if beat.replace:
        target.fill("")
    if not beat.typing:
        page.keyboard.type(beat.text)
        return
    for i in range(0, len(beat.text), TYPING_CHARS):
        page.keyboard.type(beat.text[i:i + TYPING_CHARS])
        rec.shot(seconds=TYPING_FRAME_S)


def act_on_target(page: Page, board: sb.Storyboard, beat: sb.Beat, rec: Recorder) -> None:
    target = locators.resolve(page, beat.target)
    label = beat.target.get("label")
    point = chevron_end(target) if beat.do == "multiselect" else center(target, beat.target.get("at"))
    rec.shot(cursor=point, click=beat.do != "hover")
    if beat.do == "hover":
        page.mouse.move(*point)
        page.wait_for_timeout(OPTION_MS)
        return
    page.mouse.click(*point)
    if beat.do == "type":
        type_text(page, target, beat, rec)
    elif beat.do == "select":
        page.wait_for_timeout(OPTION_MS)
        pick(page, rec, beat.value, label, board, settle=True)
        return
    elif beat.do == "multiselect":
        page.wait_for_timeout(OPTION_MS)
        for value in beat.values:
            pick(page, rec, value, label, board, settle=False)
        close_dropdown(page, label)
    wait_idle(page, board.busy, board.settle_ms)


def act(page: Page, board: sb.Storyboard, beat: sb.Beat, rec: Recorder) -> None:
    if beat.do == "go":
        page.goto(f"{board.app}{beat.route}")
        wait_idle(page, board.busy, board.settle_ms)
    elif beat.do == "press":
        page.keyboard.press(beat.key)
        if not beat.film_every:  # a filmed wait starts at once; idling first would skip what it films
            wait_idle(page, board.busy, board.settle_ms)
    elif beat.do == "scroll":
        locators.resolve(page, beat.target).scroll_into_view_if_needed()
        page.wait_for_timeout(OPTION_MS)
    elif beat.do != "show":
        act_on_target(page, board, beat, rec)


def film_until(page: Page, beat: sb.Beat, rec: Recorder) -> None:
    """Film a wait as a person sees it: a still every ``film_every`` seconds until ``wait_for`` shows."""
    done = locators.resolve_now(page, beat.wait_for)
    for _ in range(FILM_MAX):
        if done.count() and done.first.is_visible():
            return
        rec.shot(seconds=FILM_FRAME_S)
        page.wait_for_timeout(round(beat.film_every * 1000))


def read_figures(page: Page, beat: sb.Beat) -> dict[str, str]:
    return {name: " ".join(locators.resolve(page, target).inner_text().split())
            for name, target in beat.figures.items()}


def live_beat(page: Page, board: sb.Storyboard, beat: sb.Beat, shots_dir: Path) -> dict:
    rec = Recorder(page, shots_dir, beat.id)
    act(page, board, beat, rec)
    if beat.wait_for and beat.film_every:
        film_until(page, beat, rec)
    if beat.wait_for:  # work the busy check cannot see, such as an answer streaming in
        locators.resolve(page, beat.wait_for, timeout_ms=WAIT_FOR_TIMEOUT_MS)
        wait_idle(page, board.busy, board.settle_ms)
    figures = read_figures(page, beat)
    rec.shot()
    return {"id": beat.id, "scene": beat.scene, "do": beat.do, "hold": beat.hold, "figures": figures,
            "caption": sb.fill(beat.caption, figures), "say": sb.fill(beat.say, figures),
            "crop": list(beat.crop) if beat.crop else None, "shots": rec.shots}


def card_beat(beat: sb.Beat, diff: dict, layers: tuple[dict, ...] = ()) -> dict:
    return {"id": beat.id, "scene": beat.scene, "do": beat.do, "hold": beat.hold, "caption": beat.caption,
            "say": beat.say, "card": cards.card_for(beat, diff, layers)}


def stopped(page: Page, captures: Path, beat: sb.Beat, err: Exception) -> SystemExit:
    seen = captures / f"STOPPED-{beat.id}.png"
    page.screenshot(path=str(seen))
    return SystemExit(f"STOPPED at beat {beat.id} (scene {beat.scene}): {err}\nscreen: {seen}\n"
                      "Either the storyboard names it wrongly (check catalogue.json), or this is a finding: "
                      "the PR doesn't show what the storyboard expected. Don't paper over a finding.")


def film(board: sb.Storyboard, diff: dict, captures: Path) -> list[dict]:
    shots_dir = captures / "shots"
    if not board.has_live:
        return [card_beat(b, diff, board.layers) for b in board.beats]
    try:
        require_app(board.app)
    except SessionError as err:
        raise SystemExit(f"NOT READY: {err}") from err
    beats = []
    with open_page(board.app) as page:
        page.goto(f"{board.app}{board.start}")
        wait_idle(page, board.busy, board.settle_ms)
        for beat in board.beats:
            if beat.is_card:
                beats.append(card_beat(beat, diff, board.layers))
                continue
            try:
                beats.append(live_beat(page, board, beat, shots_dir))
            except locators.TargetNotFound as err:
                raise stopped(page, captures, beat, err) from err
            print(f"beat {beat.id}: {len(beats[-1]['shots'])} shots")
    return beats


def manifest_for(board: sb.Storyboard, diff: dict, beats: list[dict]) -> dict:
    return {"title": board.title, "pr": board.pr, "repo": board.repo, "base": board.base, "head": board.head,
            "url": (diff.get("pr") or {}).get("url"), "app": board.app, "totals": diff.get("totals"),
            "review_points": list(board.review_points),
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"), "beats": beats}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def run(storyboard_path: Path, silent: bool, engine_name: str, allow_edge: bool) -> Path:
    board = sb.load(storyboard_path)
    folder = storyboard_path.resolve().parent
    diff = sb.read_json(folder / "diff.json") or {"files": [], "totals": {}}
    engine = None if silent else voice.choose_engine(engine_name, voice.model_ready(), voice.edge_allowed(allow_edge))
    print(f"about {sb.estimate_seconds(board) + timeline.TITLE_S + timeline.END_S:.0f} s planned; "
          f"voice: {engine or 'none (silent)'}")
    captures = folder / "captures"
    shutil.rmtree(captures, ignore_errors=True)
    (captures / "shots").mkdir(parents=True)
    beats = film(board, diff, captures)
    if engine:
        beats = voice.voice_beats(beats, captures, voice.speaker(engine, voice.VOICES[engine]), engine,
                                  voice.VOICES[engine])
    manifest = manifest_for(board, diff, beats)
    write_json(captures / "manifest.json", manifest)
    schedule = timeline.build(manifest)
    write_json(captures / "timeline.json", schedule)
    sheet = contact_sheet.build(captures, manifest)
    print(f"captured {len(beats)} beats; {timeline.seconds(schedule):.1f} s; contact sheet {sheet}")
    timeline.check_length(schedule)
    return captures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard", type=Path)
    ap.add_argument("--silent", action="store_true", help="no narration")
    ap.add_argument("--voice", default="auto", choices=voice.ENGINES)
    ap.add_argument("--allow-edge", action="store_true", help="allow the online edge-tts fallback")
    args = ap.parse_args()
    try:
        run(args.storyboard, args.silent, args.voice, args.allow_edge)
    except sb.StoryboardError as err:
        sys.exit(f"STORYBOARD REFUSED:\n{err}")
    except voice.VoiceError as err:
        sys.exit(f"NO VOICE: {err}")
    except timeline.LengthError as err:
        sys.exit(f"TOO LONG: {err}")


if __name__ == "__main__":
    main()
