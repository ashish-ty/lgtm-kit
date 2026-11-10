# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Preview or render a captured PR video with Remotion.

    uv run render.py render <video folder>                 # out/<pr-or-branch>.mp4 (+ .srt subtitles)
    uv run render.py studio <video folder>                 # scrub it in Remotion Studio
    uv run render.py still  <video folder> --frame 150

Reads ``captures/timeline.json`` as the composition's props and serves ``captures/`` as its
public folder, so nothing is copied into the Remotion project. The MP4 is 1920×1080, 30 fps,
H.264 with AAC narration, its subtitles burned in and also written beside it as ``.srt``. Remotion installs itself into ``remotion/node_modules`` on first use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import timeline

REMOTION = Path(__file__).resolve().parents[1] / "remotion"
ENTRY = "src/index.ts"
COMPOSITION = "PrVideo"
INSTALLED = "node_modules/.pr-video-installed"  # written only after npm finishes; holds the lockfile's hash


def lock_hash() -> str:
    lock = REMOTION / "package-lock.json"
    return hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else "no-lockfile"


def ensure_installed() -> None:
    """Install Remotion on first use, and again when an earlier install was cut off or the plugin
    update changed the lockfile: a bare ``node_modules/`` proves nothing."""
    marker = REMOTION / INSTALLED
    if marker.exists() and marker.read_text().strip() == lock_hash():
        return
    missing = [tool for tool in ("node", "npm", "npx") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"NOT RENDERED: {', '.join(missing)} not found — install Node.js 18 or newer "
                         "(https://nodejs.org), then rerun")
    command = "ci" if (REMOTION / "package-lock.json").exists() else "install"
    print(f"installing Remotion into {REMOTION / 'node_modules'} (once) …")
    run(["npm", command, "--no-audit", "--no-fund"], f"`npm {command}` in {REMOTION} failed")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(lock_hash())


def run(args: list[str], failure: str) -> None:
    try:
        subprocess.run(args, cwd=REMOTION, check=True)
    except FileNotFoundError as err:
        raise SystemExit(f"NOT RENDERED: {args[0]} not found — install Node.js 18 or newer") from err
    except subprocess.CalledProcessError as err:
        raise SystemExit(f"NOT RENDERED: {failure} (exit {err.returncode}); its output is above") from err


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "pr-video"


def remotion(args: list[str]) -> None:
    ensure_installed()
    run(["npx", "remotion", *args], f"`remotion {args[0]}` failed")


def flags(captures: Path) -> list[str]:
    schedule = captures / "timeline.json"
    if not schedule.exists():
        raise SystemExit(f"no {schedule} — run capture.py first")
    return [f"--public-dir={captures}", f"--props={schedule}"]


def write_srt(captures: Path, video: Path) -> Path | None:
    """The narration subtitles as ``<video>.srt``, for players that show captions as text."""
    text = timeline.srt(json.loads((captures / "timeline.json").read_text()))
    if not text:
        return None
    out = video.with_suffix(".srt")
    out.write_text(text, encoding="utf-8")
    return out


def video_name(folder: Path, manifest: dict) -> str:
    return f"{folder.name}-{slug(manifest['title'])}.mp4"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["studio", "still", "render"])
    ap.add_argument("folder", type=Path, help="the PR's folder under .pr-videos/")
    ap.add_argument("--frame", type=int, default=0)
    args = ap.parse_args()
    folder = args.folder.resolve()
    captures = folder / "captures"
    common = flags(captures)
    if args.command == "studio":
        remotion(["studio", ENTRY, *common])
        return
    out = folder / "out"
    out.mkdir(exist_ok=True)
    if args.command == "still":
        target = out / f"still-{args.frame:05d}.png"
        remotion(["still", ENTRY, COMPOSITION, str(target), f"--frame={args.frame}", *common])
        print(target)
        return
    manifest = json.loads((captures / "manifest.json").read_text())
    video = out / video_name(folder, manifest)
    remotion(["render", ENTRY, COMPOSITION, str(video), "--codec=h264", *common])
    subtitles = write_srt(captures, video)
    print(f"rendered {video}" + (f"\nsubtitles {subtitles}" if subtitles else ""))


if __name__ == "__main__":
    main()
