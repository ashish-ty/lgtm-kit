# Working on lgtm-kit

Notes for coding agents (and people) changing this repo.

## What pr-video is for — keep this intact

A reviewer watches a ≤3-minute video and understands a PR faster than by reading its diff.
Every change must keep that true:

- Code cards are the real diff; live beats film the real app. Nothing is mocked.
- When the storyboard and the app disagree, the run stops and reports a finding. It never fakes the shot.
- Everything runs locally. The narration doesn't leave the machine unless the user passes `--allow-edge`.
- The video stays under 3 minutes, is easy to read, and is easy to follow by ear.

## After any change to `skills/pr-video/`, re-make the reference video

Tests passing is not enough: a change can pass every test and still make the video worse.
After the tests, re-make the README demo video and compare it with the one in the README.

1. **Tests.** From `skills/pr-video/`, run:

   ```sh
   PR_VIDEO_E2E_RENDER=1 uv run --with pytest --with pyyaml --with pillow --with tinytag \
     --with playwright --with kokoro-onnx pytest -q
   ```

   Run it on Python 3.10 too (`--python 3.10`); that's the oldest version the scripts support.

2. **Reference video: [excalidraw#12189](https://github.com/excalidraw/excalidraw/pull/12189).**
   Its storyboard is [skills/pr-video/tests/reference/excalidraw-12189.storyboard.md](skills/pr-video/tests/reference/excalidraw-12189.storyboard.md).
   In an Excalidraw checkout:
   1. Run `gh pr checkout 12189`.
   2. Start the app from `excalidraw-app/` with `npx vite --port 3001 --strictPort`.
   3. Copy the storyboard to `.pr-videos/pr-12189/storyboard.md`.
   4. Run `prepare.py --pr 12189`, then `capture.py`, then `render.py render`, using this
      branch's scripts rather than an installed plugin.

3. **Compare it with the README video.** Look at the contact sheet and a few frames, not only the exit code:
   - All 12 beats are there and it runs about 2:20.
   - The live beats show `9. buy milk` → `10. buy milk`, then two undos: the marker first, then the copy.
   - The code cards are readable, and the subtitles cover neither code nor captions.
   - The end card lists the review points.

   If the video got worse, fix the change, not the storyboard. If it changed on purpose, update the
   README video and `docs/media/` screenshots in the same PR.

If you can't run step 2 (no network, no browser), say so in the PR. Don't skip it silently.
