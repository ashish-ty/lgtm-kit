# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Preview or render a captured PR video with Remotion.

    uv run render.py render <video folder>                 # out/<pr-or-branch>.mp4
    uv run render.py studio <video folder>                 # scrub it in Remotion Studio
    uv run render.py still  <video folder> --frame 150

Reads ``captures/timeline.json`` as the composition's props and serves ``captures/`` as its
public folder, so nothing is copied into the Remotion project. The MP4 is 1920×1080, 30 fps,
H.264 with AAC narration. Remotion installs itself into ``remotion/node_modules`` on first use.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REMOTION = Path(__file__).resolve().parents[1] / "remotion"
ENTRY = "src/index.ts"
COMPOSITION = "PrVideo"


def ensure_installed() -> None:
    if not (REMOTION / "node_modules").exists():
        command = "ci" if (REMOTION / "package-lock.json").exists() else "install"
        subprocess.run(["npm", command, "--no-audit", "--no-fund"], cwd=REMOTION, check=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "pr-video"


def remotion(args: list[str]) -> None:
    ensure_installed()
    subprocess.run(["npx", "remotion", *args], cwd=REMOTION, check=True)


def flags(captures: Path) -> list[str]:
    schedule = captures / "timeline.json"
    if not schedule.exists():
        raise SystemExit(f"no {schedule} — run capture.py first")
    return [f"--public-dir={captures}", f"--props={schedule}"]


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
    print(f"rendered {video}")


if __name__ == "__main__":
    main()
