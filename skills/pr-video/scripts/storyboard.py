"""Read and check a PR video storyboard: the one ```yaml block inside ``storyboard.md``.

The storyboard is the contract for the video. A beat is either a **card** drawn from the diff
(``code``, ``overview``) or a **live** beat carried out on the running app. Everything is
refused here — before a browser opens or a voice speaks — when a beat names a file the diff
lacks, a range that shows nothing, a target the capture can't reach, or a figure it can't fill.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import diff_map
import yaml

LIVE_ACTIONS = {
    "click": "click the target",
    "hover": "move the cursor onto the target without clicking (tooltips)",
    "select": "open a single-choice dropdown and pick `value`",
    "multiselect": "open a multi-choice dropdown and tick every entry in `values`",
    "type": "click a text field and type `text`",
    "press": "press `key` (e.g. Escape) with no cursor move",
    "scroll": "bring the target into view",
    "go": "hard cut to `route`",
    "show": "no action — hold on the screen as it is",
}
CARD_ACTIONS = {
    "code": "a card of one hunk of `file`, optionally cut to `lines: [first, last]`",
    "overview": "the changed files, with lines added and removed, grouped by `layers` when given",
    "tests": "the test files the PR touches and the names of the tests they add",
}
ACTIONS = {**CARD_ACTIONS, **LIVE_ACTIONS}
TARGET_KINDS = ("role", "text", "label", "placeholder", "option", "cell", "stat", "demo", "css")
NEEDS_TARGET = {"click", "hover", "select", "multiselect", "type", "scroll"}
REQUIRED_FIELD = {"select": "value", "multiselect": "values", "type": "text", "press": "key", "go": "route",
                  "code": "file"}
DEFAULT_HOLD = 2.5
SCREEN = (1920, 1080)  # the capture viewport, in CSS pixels; a crop must fit inside it
MAX_CAPTION = 90
MAX_SAY = 400          # about 25 s of speech: one beat says one thing
MAX_CODE_ROWS = 24     # what fits on a 1080p card at a readable size
MAX_REVIEW_POINTS = 4
MAX_LAYERS = 6
SPEECH_CHARS_PER_S = 15.0  # rough speaking rate, for the estimate printed before a capture
DEFAULT_BUSY = '[aria-busy="true"], .animate-spin, .spinner'


class StoryboardError(ValueError):
    """The storyboard cannot be carried out as written."""


@dataclass(frozen=True)
class Beat:
    id: str
    scene: str
    do: str
    target: dict | None = None
    value: str | None = None
    values: tuple[str, ...] = ()
    text: str | None = None
    key: str | None = None
    route: str | None = None
    caption: str | None = None
    say: str | None = None
    figures: dict = field(default_factory=dict)
    hold: float = DEFAULT_HOLD
    wait_for: dict | None = None
    replace: bool = False
    crop: tuple[float, float, float, float] | None = None
    typing: bool = False
    film_every: float | None = None
    file: str | None = None
    hunk: int = 0
    lines: tuple[int, int] | None = None

    @property
    def is_card(self) -> bool:
        return self.do in CARD_ACTIONS


@dataclass(frozen=True)
class Storyboard:
    title: str
    beats: tuple[Beat, ...]
    pr: int | None = None
    repo: str | None = None
    base: str | None = None
    head: str | None = None
    app: str | None = None
    start: str | None = None
    review_points: tuple[str, ...] = ()
    layers: tuple[dict, ...] = ()
    busy: str = DEFAULT_BUSY
    settle_ms: int = 1200
    base_dir: Path = Path(".")

    @property
    def has_live(self) -> bool:
        return any(not b.is_card for b in self.beats)


PRIVATE_REF = re.compile(r"\$\{private\.([\w-]+)\}")
DATE_REF = re.compile(r"\$\{date:([+-]\d+)d\}")


def fill_private(text: str, private: dict) -> str:
    """Swap ``${private.key}`` for its value from the gitignored ``private.yaml`` beside the storyboard."""
    missing = sorted({k for k in PRIVATE_REF.findall(text) if k not in private})
    if missing:
        raise StoryboardError(f"storyboard uses ${{private.…}} keys {missing} that private.yaml does not define")
    return PRIVATE_REF.sub(lambda m: str(private[m.group(1)]), text)


def fill_dates(text: str, today: date) -> str:
    """Swap ``${date:+14d}`` for that day counted from the capture, as YYYY-MM-DD."""
    return DATE_REF.sub(lambda m: (today + timedelta(days=int(m.group(1)))).isoformat(), text)


def extract_yaml(markdown: str) -> str:
    blocks = re.findall(r"```ya?ml\n(.*?)```", markdown, flags=re.DOTALL)
    if len(blocks) != 1:
        raise StoryboardError(f"storyboard.md must hold exactly one ```yaml block, found {len(blocks)}")
    return blocks[0]


def template_fields(text: str | None) -> list[str]:
    """The ``{figure}`` names a caption or narration uses; none when its braces don't parse."""
    try:
        return [name for _, name, _, _ in string.Formatter().parse(text or "") if name]
    except ValueError:
        return []


def brace_problem(text: str) -> str | None:
    """A ``{`` or ``}`` that isn't a named figure would crash the fill after filming, so refuse it now."""
    try:
        names = [name for _, name, _, _ in string.Formatter().parse(text) if name is not None]
    except ValueError:
        return "has an unmatched brace"
    if any(name == "" or name.isdigit() for name in names):
        return "has an empty or numbered {…}"
    return None


def fill(template: str | None, figures: dict[str, str]) -> str | None:
    """A caption or narration with each ``{figure}`` replaced by the text read off the screen."""
    return None if template is None else template.format_map(figures)


def check_target(where: str, target) -> list[str]:
    if not isinstance(target, dict) or not target:
        return [f"{where}: target must be a mapping such as {{role: button, name: Save}}"]
    kinds = [k for k in target if k in TARGET_KINDS]
    if len(kinds) != 1:
        return [f"{where}: target needs exactly one of {', '.join(TARGET_KINDS)}, got {sorted(target)}"]
    at, nth = target.get("at"), target.get("nth")
    if at is not None and not (isinstance(at, list) and len(at) == 2
                               and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in at)):
        return [f"{where}: `at` is a point inside the target as fractions, e.g. at: [0.42, 0.8]"]
    if nth is not None and nth not in ("first", "last") and not isinstance(nth, int):
        return [f"{where}: `nth` is first, last or an index"]
    if kinds[0] == "role" and not target.get("name"):
        return [f"{where}: a role target needs a name, e.g. {{role: button, name: Save}}"]
    if kinds[0] == "cell" and not (isinstance(target["cell"], dict) and {"row", "column"} <= set(target["cell"])):
        return [f"{where}: a cell target needs {{cell: {{row: ..., column: ...}}}}"]
    return []


def crop_box(crop: list) -> tuple[float, float, float, float]:
    """``[x, y, width]`` on the screen; the height follows from the video's 16:9."""
    x, y, width = (float(v) for v in crop)
    return (x, y, width, width * SCREEN[1] / SCREEN[0])


def check_crop(where: str, crop) -> list[str]:
    if not (isinstance(crop, list) and len(crop) == 3 and all(isinstance(v, (int, float)) for v in crop)):
        return [f"{where}: `crop` is [x, y, width] in screen pixels; the height follows at 16:9"]
    x, y, width, height = crop_box(crop)
    if x < 0 or y < 0 or width <= 0 or x + width > SCREEN[0] or y + height > SCREEN[1]:
        return [(f"{where}: crop [{x:g}, {y:g}, {width:g}] (height {height:.0f}) falls outside the "
                f"{SCREEN[0]}×{SCREEN[1]} screen")]
    return []


def check_words(where: str, raw: dict) -> list[str]:
    """Caption and narration: their length, and every ``{figure}`` they use is defined."""
    figures, problems = raw.get("figures") or {}, []
    caption, say = raw.get("caption") or "", raw.get("say") or ""
    for name, text in (("caption", caption), ("narration", say)):
        broken = brace_problem(text)
        if broken:
            problems.append(f"{where}: {name} {broken} — write {{{{ and }}}} for a literal brace, "
                            "or {figure_name} for a figure")
            continue
        missing = [f for f in template_fields(text) if f not in figures]
        if missing:
            problems.append(f"{where}: {name} uses {missing} but `figures` does not define them")
    if len(caption) > MAX_CAPTION:
        problems.append(f"{where}: caption is {len(caption)} characters; keep it under {MAX_CAPTION}")
    if len(say) > MAX_SAY:
        problems.append(f"{where}: {len(say)} characters of narration; keep a beat under {MAX_SAY} "
                        "(about 25 s) — split it into two beats")
    if figures and raw.get("do") in CARD_ACTIONS:
        problems.append(f"{where}: figures are read off the live screen; a card beat has none")
    return problems


def check_live(where: str, raw: dict) -> list[str]:
    problems = []
    if raw["do"] in NEEDS_TARGET:
        problems += check_target(where, raw.get("target"))
    if raw.get("crop") is not None:
        problems += check_crop(where, raw["crop"])
    if raw.get("wait_for") is not None:
        problems += check_target(f"{where} wait_for", raw["wait_for"])
    film = raw.get("film_every")
    if film is not None and (raw.get("wait_for") is None or not isinstance(film, (int, float)) or not 0.2 <= film <= 5):
        problems.append(f"{where}: `film_every` is seconds between stills (0.2–5) and needs a `wait_for`")
    for name, target in (raw.get("figures") or {}).items():
        problems += check_target(f"{where} figure {name}", target)
    return problems


def check_code(where: str, raw: dict, diff: dict | None) -> list[str]:
    if diff is None:
        return [f"{where}: a code beat needs diff.json beside the storyboard — run prepare.py first"]
    try:
        file = diff_map.find_file(diff["files"], str(raw["file"]))
    except KeyError as err:
        return [f"{where}: {err.args[0]}"]
    hunk = raw.get("hunk", 0)
    if not isinstance(hunk, int) or not 0 <= hunk < len(file["hunks"]):
        return [f"{where}: hunk {hunk} — {raw['file']} has {len(file['hunks'])} hunks (0-based)"]
    lines = raw.get("lines")
    if lines is not None and not (isinstance(lines, list) and len(lines) == 2
                                  and all(isinstance(n, int) for n in lines) and lines[0] <= lines[1]):
        return [f"{where}: `lines` is [first, last], line numbers in the new file (old, for a deleted file)"]
    rows = diff_map.card_rows(file["hunks"][hunk], lines, deleted=file["status"] == "deleted")
    if not rows:
        return [f"{where}: lines {lines} hold no rows of hunk {hunk} in {raw['file']}"]
    if len(rows) > MAX_CODE_ROWS:
        return [(f"{where}: {raw['file']} hunk {hunk} has {len(rows)} rows; a card holds {MAX_CODE_ROWS} — "
                "pick `lines: [first, last]` or split it across beats")]
    return []


def check_beat(raw: dict, where: str, diff: dict | None) -> list[str]:
    do = raw.get("do")
    if do not in ACTIONS:
        return [f"{where}: `do` must be one of {', '.join(ACTIONS)}, got {do!r}"]
    needed = REQUIRED_FIELD.get(do)
    if needed and not raw.get(needed):
        return [f"{where}: `{do}` needs `{needed}`"]
    problems = check_words(where, raw)
    if do == "code":
        problems += check_code(where, raw, diff)
    elif do == "tests" and not any(f["kind"] == "test" for f in (diff or {}).get("files", [])):
        problems.append(f"{where}: the diff has no test files — say so in `review_points` instead of a tests card")
    elif do in LIVE_ACTIONS:
        problems += check_live(where, raw)
    return problems


def build_beat(raw: dict, scene: str) -> Beat:
    lines = raw.get("lines")
    return Beat(
        id=str(raw["id"]), scene=scene, do=raw["do"], target=raw.get("target"),
        value=raw.get("value"), values=tuple(raw.get("values") or ()), text=raw.get("text"),
        key=raw.get("key"), route=raw.get("route"), caption=raw.get("caption"), say=raw.get("say"),
        figures=dict(raw.get("figures") or {}), hold=float(raw.get("hold", DEFAULT_HOLD)),
        wait_for=raw.get("wait_for"), replace=bool(raw.get("replace", False)),
        crop=crop_box(raw["crop"]) if raw.get("crop") is not None else None,
        typing=bool(raw.get("typing", False)),
        film_every=float(raw["film_every"]) if raw.get("film_every") is not None else None,
        file=raw.get("file"), hunk=int(raw.get("hunk", 0)), lines=tuple(lines) if lines else None,
    )


def read_beats(scenes: list, diff: dict | None) -> tuple[list[Beat], list[str]]:
    beats, problems, seen = [], [], set()
    for scene in scenes:
        scene_id = str(scene.get("id", ""))
        for raw in scene.get("beats") or []:
            where = f"beat {raw.get('id', '?')} (scene {scene_id})"
            if not raw.get("id"):
                problems.append(f"{where}: every beat needs an id")
                continue
            if raw["id"] in seen:
                problems.append(f"{where}: duplicate beat id")
            seen.add(raw["id"])
            found = check_beat(raw, where, diff)
            problems += found
            if not found:
                beats.append(build_beat(raw, scene_id))
    return beats, problems


def check_board(data: dict, beats: list[Beat], title: str | None) -> list[str]:
    problems = [] if data.get("scenes") else ["missing `scenes`"]
    if not title:
        problems.append("missing `title`, and diff.json has no PR title to fall back on")
    if any(not b.is_card for b in beats) and not (data.get("app") and data.get("start")):
        problems.append("live beats need `app` (the local URL the person started) and `start` (where to open)")
    if len(data.get("review_points") or ()) > MAX_REVIEW_POINTS:
        problems.append(f"review_points: at most {MAX_REVIEW_POINTS}, so the end card can be read")
    return problems + check_layers(data.get("layers"))


def check_layers(layers) -> list[str]:
    """``layers: [{name: API, paths: ["backend/*"]}, …]`` — globs where ``*`` also crosses ``/``."""
    if layers is None:
        return []
    ok = isinstance(layers, list) and 0 < len(layers) <= MAX_LAYERS and all(
        isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("paths"), list)
        and x["paths"] and all(isinstance(p, str) for p in x["paths"]) for x in layers)
    return [] if ok else [f"layers: a list of 1–{MAX_LAYERS} {{name: ..., paths: [glob, ...]}}"]


def parse(markdown: str, diff: dict | None = None, base_dir: Path = Path("."), private: dict | None = None,
          today: date | None = None) -> Storyboard:
    text = fill_dates(fill_private(extract_yaml(markdown), private or {}), today or date.today())
    data = yaml.safe_load(text) or {}
    pr = (diff or {}).get("pr") or {}
    title = data.get("title") or pr.get("title")
    beats, problems = read_beats(data.get("scenes") or [], diff)
    problems += check_board(data, beats, title)
    if not beats and not problems:
        problems.append("the storyboard has no beats")
    if problems:
        raise StoryboardError("\n".join(problems))
    app = data.get("app")
    return Storyboard(
        title=title, beats=tuple(beats), pr=data.get("pr", pr.get("number")),
        repo=data.get("repo", pr.get("repo")), base=data.get("base", pr.get("base")),
        head=data.get("head", pr.get("head")), app=app.rstrip("/") if app else None, start=data.get("start"),
        review_points=tuple(str(p) for p in data.get("review_points") or ()),
        layers=tuple({"name": x["name"], "paths": list(x["paths"])} for x in data.get("layers") or ()),
        busy=data.get("busy", DEFAULT_BUSY), settle_ms=int(data.get("settle_ms", 1200)), base_dir=base_dir,
    )


def read_json(path: Path) -> dict | None:
    import json
    return json.loads(path.read_text()) if path.exists() else None


def load(path: Path) -> Storyboard:
    folder = path.resolve().parent
    private_file = folder / "private.yaml"
    private = (yaml.safe_load(private_file.read_text()) or {}) if private_file.exists() else {}
    return parse(path.read_text(), diff=read_json(folder / "diff.json"), base_dir=folder, private=private)


def estimate_seconds(board: Storyboard) -> float:
    """A rough length before any capture: each beat lasts its hold or its narration, whichever is longer."""
    return sum(max(b.hold, len(b.say or "") / SPEECH_CHARS_PER_S) for b in board.beats)


def targets(board: Storyboard) -> list[tuple[str, str, str]]:
    """(beat id, target kind, name) for every element the live beats name."""
    out = []
    for beat in board.beats:
        for target in ([beat.target] if beat.target else []) + list(beat.figures.values()):
            kind = next(k for k in target if k in TARGET_KINDS)
            if kind != "cell":
                out.append((beat.id, kind, str(target["name"] if kind == "role" else target[kind])))
        if beat.do == "select" and beat.value:
            out.append((beat.id, "option", beat.value))
        out += [(beat.id, "option", v) for v in beat.values]
    return out
