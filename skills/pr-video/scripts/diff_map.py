"""Read a unified diff into the files, hunks and numbered rows a code card shows.

Pure functions only: ``prepare.py`` fetches the diff, this turns it into ``diff.json``, and the
storyboard and capture read that file. A row is ``{kind, old, new, text}`` where ``kind`` is
``+``, ``-`` or a space, and ``old`` / ``new`` are the line numbers on each side (``None`` on
the side the line does not exist).
"""

from __future__ import annotations

import difflib
import re
from fnmatch import fnmatch
from pathlib import PurePosixPath

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$")
GENERATED = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock", "poetry.lock", "Pipfile.lock",
             "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum", "*.min.js", "*.min.css", "*.snap")
TEST_PARTS = ("tests", "test", "__tests__", "spec")
TEST_NAMES = ("test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*", "*Test.java", "*_test.cpp")
KINDS = ("code", "test", "generated")


def kind_of(path: str) -> str:
    """``generated`` (lockfiles, minified, snapshots), ``test``, or ``code``."""
    p = PurePosixPath(path)
    if any(fnmatch(p.name, g) for g in GENERATED):
        return "generated"
    if any(part in TEST_PARTS for part in p.parts[:-1]) or any(fnmatch(p.name, t) for t in TEST_NAMES):
        return "test"
    return "code"


C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def unquote(path: str) -> str:
    """Undo git's C-quoting of a path (``core.quotePath``): ``"caf\\303\\251.txt"`` is ``café.txt``."""
    if len(path) < 2 or not (path[0] == path[-1] == '"'):
        return path
    body, out, i = path[1:-1], bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            octal = body[i + 1:i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8))
                i += 4
                continue
            out.append(C_ESCAPES.get(body[i + 1], ord(body[i + 1])))
            i += 2
            continue
        out += ch.encode()
        i += 1
    return out.decode("utf-8", errors="replace")


def _side_path(text: str) -> str:
    """A ``---``/``+++`` path: git ends one holding a space with a tab, and quotes unusual ones."""
    return _strip_prefix(unquote(text.rstrip("\t")))


def _strip_prefix(path: str) -> str:
    return path[2:] if path[:2] in ("a/", "b/") else path


def _git_header_path(line: str) -> str:
    """``diff --git a/x b/x`` — ambiguous with spaces, so only a fallback for files with no ---/+++."""
    rest = line[len("diff --git "):]
    if rest.endswith('"') and rest.rfind(' "b/') >= 0:
        return _strip_prefix(unquote(rest[rest.rfind(' "b/') + 1:]))
    half = rest.rfind(" b/")
    return rest[half + 3:] if half >= 0 else rest


def _new_file(header: str) -> dict:
    path = _git_header_path(header)
    return {"path": path, "old_path": path, "status": "modified", "added": 0, "removed": 0, "hunks": []}


def _read_meta(file: dict, line: str) -> dict:
    """The header lines between ``diff --git`` and the first hunk; returns the updated file."""
    if line.startswith("new file mode"):
        return {**file, "status": "added"}
    if line.startswith("deleted file mode"):
        return {**file, "status": "deleted"}
    if line.startswith("rename from "):
        return {**file, "old_path": unquote(line[len("rename from "):]), "status": "renamed"}
    if line.startswith("rename to "):
        return {**file, "path": unquote(line[len("rename to "):]), "status": "renamed"}
    if line.startswith("Binary files "):
        return {**file, "status": "binary"}
    if line.startswith("--- ") and line[4:] != "/dev/null":
        return {**file, "old_path": _side_path(line[4:])}
    if line.startswith("+++ ") and line[4:] != "/dev/null":
        return {**file, "path": _side_path(line[4:])}
    if line.startswith("+++ /dev/null"):
        return {**file, "path": file["old_path"]}
    return file


def _read_hunk(lines: list[str], i: int) -> tuple[dict, int]:
    """The hunk whose ``@@`` header is ``lines[i]``; returns it and the index after it."""
    old, new, context = HUNK.match(lines[i]).groups()
    old_no, new_no, rows = int(old), int(new), []
    i += 1
    while i < len(lines) and lines[i][:1] in (" ", "+", "-", "\\", "") and not lines[i].startswith("diff --git "):
        line = lines[i]
        if line.startswith("\\"):  # "\ No newline at end of file"
            i += 1
            continue
        if line == "" and i == len(lines) - 1:
            break
        sign, text = (line[:1] or " "), line[1:]
        rows.append({"kind": sign, "old": None if sign == "+" else old_no,
                     "new": None if sign == "-" else new_no, "text": text})
        old_no += sign != "+"
        new_no += sign != "-"
        i += 1
    return {"old_start": int(old), "new_start": int(new), "context": context.strip(), "rows": rows}, i


def _finish(file: dict) -> dict:
    rows = [r for h in file["hunks"] for r in h["rows"]]
    return {**file, "kind": kind_of(file["path"]),
            "added": sum(r["kind"] == "+" for r in rows), "removed": sum(r["kind"] == "-" for r in rows)}


def parse(text: str) -> list[dict]:
    """Every file in a ``git diff`` / ``gh pr diff``, in diff order."""
    lines, files, current, i = text.split("\n"), [], None, 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            if current:
                files.append(_finish(current))
            current = _new_file(line)
            i += 1
        elif current is not None and HUNK.match(line):
            hunk, i = _read_hunk(lines, i)
            current = {**current, "hunks": [*current["hunks"], hunk]}
        else:
            if current is not None:
                current = _read_meta(current, line)
            i += 1
    if current:
        files.append(_finish(current))
    return files


def totals(files: list[dict]) -> dict:
    """File count, and lines added/removed split by code, tests and generated files."""
    out = {"files": len(files)}
    for kind in KINDS:
        picked = [f for f in files if f["kind"] == kind]
        out[kind] = {"added": sum(f["added"] for f in picked), "removed": sum(f["removed"] for f in picked)}
    return out


def _row_keys(rows: list[dict], deleted: bool) -> list[int]:
    """The line number each row is sliced by. New-side numbers; a deleted line sits just before
    the next surviving line, so it stays with that line. A deleted file has only old numbers."""
    if deleted:
        return [r["old"] for r in rows]
    keys, upcoming = [None] * len(rows), None
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]["new"] is not None:
            upcoming = rows[i]["new"]
            keys[i] = upcoming
        else:
            keys[i] = upcoming if upcoming is not None else _last_new(rows) + 1
    return keys


def _last_new(rows: list[dict]) -> int:
    numbers = [r["new"] for r in rows if r["new"] is not None]
    return numbers[-1] if numbers else 0


def card_rows(hunk: dict, lines: list[int] | None = None, deleted: bool = False) -> list[dict]:
    """The rows a card shows: the whole hunk, or those within ``lines: [first, last]``."""
    if not lines:
        return list(hunk["rows"])
    first, last = lines
    keys = _row_keys(hunk["rows"], deleted)
    return [row for row, key in zip(hunk["rows"], keys) if first <= key <= last]


def find_file(files: list[dict], path: str) -> dict:
    for f in files:
        if f["path"] == path:
            return f
    close = difflib.get_close_matches(path, [f["path"] for f in files], n=3, cutoff=0.5)
    raise KeyError(f"{path!r} is not in the diff" + (f" — did you mean {close}?" if close else ""))
