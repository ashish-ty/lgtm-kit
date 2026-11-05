"""The data a card beat draws, cut from ``diff.json``: a hunk of code, the changed files, or the tests."""

from __future__ import annotations

import re
from fnmatch import fnmatch

import diff_map
from storyboard import Beat

MAX_COLS = 110            # characters across a 1080p code card at a readable size
MAX_OVERVIEW_FILES = 14
MAX_TEST_FILES = 8
MAX_TEST_NAMES = 5        # per file
KIND_GROUPS = (("code", "code"), ("test", "tests"), ("generated", "generated"))
TAB = "    "
FILE_FIELDS = ("path", "kind", "status", "added", "removed")
# Names of tests a + row adds: pytest, Jest/Vitest/Mocha/Playwright, Go.
TEST_NAME = (re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)"),
             re.compile(r"\b(?:it|test)(?:\.\w+)?\(\s*(['\"`])(?P<name>.+?)\1"),
             re.compile(r"^\s*func\s+(Test\w+)\s*\("))


def fit(text: str) -> str:
    line = text.replace("\t", TAB)
    return line if len(line) <= MAX_COLS else line[:MAX_COLS - 1] + "…"


def code_card(beat: Beat, diff: dict) -> dict:
    file = diff_map.find_file(diff["files"], beat.file)
    hunk = file["hunks"][beat.hunk]
    rows = diff_map.card_rows(hunk, list(beat.lines) if beat.lines else None, deleted=file["status"] == "deleted")
    return {"file": file["path"], "old_path": file["old_path"], "status": file["status"], "context": hunk["context"],
            "hunk": beat.hunk, "hunks": len(file["hunks"]), "rows": [{**r, "text": fit(r["text"])} for r in rows]}


def by_size(files: list[dict]) -> list[dict]:
    return sorted(files, key=lambda f: (-(f["added"] + f["removed"]), f["path"]))


def layer_of(path: str, layers: tuple[dict, ...]) -> int | None:
    return next((i for i, layer in enumerate(layers) if any(fnmatch(path, g) for g in layer["paths"])), None)


def grouped(files: list[dict], layers: tuple[dict, ...]) -> list[tuple[str, object, list[dict]]]:
    """(name, colour key, files): by the storyboard's layers, else by code / tests / generated."""
    if not layers:
        return [(name, kind, [f for f in files if f["kind"] == kind]) for kind, name in KIND_GROUPS]
    found = [layer_of(f["path"], layers) for f in files]
    groups = [(layer["name"], i, [f for f, at in zip(files, found) if at == i]) for i, layer in enumerate(layers)]
    return [*groups, ("other", "other", [f for f, at in zip(files, found) if at is None])]


def overview_card(diff: dict, layers: tuple[dict, ...] = ()) -> dict:
    """The changed files in groups, biggest first; at most MAX_OVERVIEW_FILES rows across all groups."""
    room, groups = MAX_OVERVIEW_FILES, []
    for name, colour, files in grouped(diff["files"], layers):
        if not files:
            continue
        ordered = by_size(files)
        shown = [{k: f[k] for k in FILE_FIELDS} for f in ordered[:room]]
        room -= len(shown)
        groups.append({"name": name, "colour": colour, "added": sum(f["added"] for f in files),
                       "removed": sum(f["removed"] for f in files), "files": shown, "more": len(files) - len(shown)})
    return {"groups": groups, "totals": diff.get("totals", {})}


def test_names(file: dict) -> list[str]:
    names = []
    for row in (r for h in file["hunks"] for r in h["rows"] if r["kind"] == "+"):
        for pattern in TEST_NAME:
            found = pattern.search(row["text"])
            if found:
                names.append(found.groupdict().get("name") or found.group(1))
                break
    return names


def tests_card(diff: dict) -> dict:
    """The test files the PR touches and the tests each one adds."""
    files = by_size([f for f in diff["files"] if f["kind"] == "test"])
    shown = []
    for f in files[:MAX_TEST_FILES]:
        names = test_names(f)
        shown.append({**{k: f[k] for k in FILE_FIELDS}, "names": [fit(n) for n in names[:MAX_TEST_NAMES]],
                      "more_names": max(0, len(names) - MAX_TEST_NAMES)})
    return {"files": shown, "more": max(0, len(files) - MAX_TEST_FILES),
            "total_names": sum(len(test_names(f)) for f in files)}


def card_for(beat: Beat, diff: dict, layers: tuple[dict, ...] = ()) -> dict | None:
    if beat.do == "code":
        return code_card(beat, diff)
    if beat.do == "overview":
        return overview_card(diff, layers)
    if beat.do == "tests":
        return tests_card(diff)
    return None
