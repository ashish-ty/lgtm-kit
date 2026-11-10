---
name: pr-video
description: Make a narrated walkthrough video (≤3 min) of a pull request or branch so its reviewer can understand it fast — diff cards for the code that matters plus live capture of the locally running app, with a local AI voiceover. Use when someone asks for a PR video, a video walkthrough or explainer of a PR/branch/diff, wants to "see" what an AI-generated PR does before reviewing it, or invokes /pr-video. Writes everything to <repo>/.pr-videos/, which ignores itself in git.
---

# PR video

The reviewer (the user) watches; you write the story. You read the PR's diff, its description
and the criteria it was built against, decide what a reviewer must see, and write a storyboard.
The scripts cut code cards from the real diff, film the real app with a synthetic cursor, speak
your narration locally, and render a 1080p MP4. Nobody records a screen.

**Rules — keep to them unless the user asks otherwise.**

- **On demand, local only.** No upload, no hosted service. Nothing merges or posts.
- **No interview and no branding.** You draft the storyboard from the PR yourself; ask only when
  the app can't be started or the PR's purpose can't be told from the diff and its issue.
- **≤ 3 minutes, enforced.** `capture.py` refuses a longer video and names the longest beats.
- **Voice is local: Kokoro.** edge-tts is the free fallback but sends the narration text to
  Microsoft, and narration describes the code, so it runs only with `--allow-edge`
  (or `PR_VIDEO_ALLOW_EDGE=1`). If neither is available, render `--silent`.
- **Diff explainer + live capture.** Cards come from `diff.json`; live beats film the app the
  user started from the PR head. Never mock a screen, never edit the app under review.
- **Output in `<repo>/.pr-videos/`**, whose `.gitignore` is `*`. The user deletes videos by hand.
- **Real things only.** Captions and narration figures are read off the screen; code cards are
  the real diff. A live target that isn't there is a *finding*, not something to work around.

## Where things live

```
<skill>/ (this folder)                <repo>/.pr-videos/pr-42/
  scripts/prepare.py    diff → json      diff.json        the PR, its body, every hunk
  scripts/crawl_app.py  screen map       catalogue.json   what live screens offer (live beats only)
  scripts/storyboard.py contract         storyboard.md    your beats (one yaml block)
  scripts/capture.py    film + voice     captures/        stills, audio/, manifest, timeline, contact sheet
  scripts/render.py     Remotion         out/             the MP4
  scripts/voice.py      Kokoro / edge
  remotion/             composition
  references/storyboard-format.md
```

`<skill>` is the folder this SKILL.md is in. Run scripts with `uv run <skill>/scripts/<name>.py …`
— each declares its own dependencies (PEP 723), so nothing is installed into any repo. The commands
below shorten this to `uv run <name>.py`.

Needs on the machine: `uv`, Node 18+ (Remotion's `node_modules` installs on first render), `gh`
signed in (for `--pr`), and for live beats Chrome or Playwright's Chromium
(`uvx playwright install chromium`). First time on a machine: `uv run <skill>/scripts/voice.py setup`
fetches the Kokoro model (~120 MB) into `~/.cache/pr-video/kokoro/`. If a tool is missing, tell the
user which one and how to install it; don't install system packages yourself.

## The flow

### 1. Prepare

`uv run prepare.py --repo <repo> --pr <N>` (or `--base main [--head <branch>]` for a branch with
no PR). It writes `<repo>/.pr-videos/pr-<N>/diff.json` and prints the size split into code,
tests and generated files. If it says the working tree is not on the PR head, live beats would
film the wrong code: check out the head before the app is started.

### 2. Read the PR the way a reviewer needs it

Read `diff.json` (the `pr.body`, the files, the hunks), and the issue it links to, if any —
its acceptance criteria say what the live part must show. Decide:

- **the 2–5 hunks that carry the change** (the logic, a contract or schema change, anything
  risky: error handling, concurrency, auth, data deletion). Skip renames, formatting, generated files.
- **what to show live**: each acceptance criterion a person can see in the UI. A backend-only
  or library PR has no live part — that's fine; make it cards only.
- **what the reviewer must still check by hand** — up to 4 `review_points` for the end card.
  This is where your honest doubts go: untested paths, behaviour the PR claims but the diff
  doesn't show, a test that asserts nothing.

### 3. Live part only: check the app and crawl it

The user (or the coding agent) starts the app from the PR head; you don't. Then
`uv run session.py check --app <url>`. If the app needs a sign-in, `uv run session.py login --app <url>`
opens a browser for the user to sign in once (kept in `~/.pr-video/`, never in the repo).
`uv run crawl_app.py --app <url> --route <route> … --out <folder>/catalogue.json` records what
each screen offers. Live target names come from this file, not from reading the code.

### 4. Write the storyboard

Write `<folder>/storyboard.md` following [references/storyboard-format.md](references/storyboard-format.md):
the PR's intent (in the first narration), an overview card grouped by the `layers` it touches,
the key code cards, a tests card, then the live beats — each with a `say:` line. Name layers by
what they are in this repo (API, worker, UI, schema), from the paths in `diff.json`.

Narration rules — it is spoken, so:
- Say what the code **does**, in plain words; don't read code aloud. "The upload now retries
  three times, doubling the wait" — not "for attempt in range RETRIES".
- Speak identifiers as words ("the upload worker", not `upload_worker.py`). Spell out symbols.
- Describe what the diff shows, not what the PR description claims. If something is claimed but
  not visible, say so, and add it to `review_points`.
- About 15 characters per second: a 25-second beat is ~400 characters, the cap per beat.
  Aim for 90–150 s in all.

### 5. Capture

`uv run capture.py <folder>/storyboard.md`. It refuses a bad storyboard before anything runs,
films the live beats, speaks every `say:`, and writes `captures/contact-sheet.png`. Look at the
contact sheet yourself before rendering.

When it **stops at a live beat**, read the screenshot it names. If the storyboard used the wrong
name, fix it from `catalogue.json` and rerun. If the thing really isn't there, **that is a
finding**: don't rewrite the beat to show something else. Tell the user, put it in
`review_points`, and drop or change the beat only with that noted.

When it stops because **the page never settled** (a timeout), something matching `busy:` may
stay on screen — a decorative spinner, say. Set `busy:` to the selector that really means
loading. A stopped or refused run leaves the previous `captures/` as it was.

When it says **TOO LONG**, cut beats or narration — it names the longest.

### 6. Render and hand over

`uv run render.py render <folder>` writes `out/<name>.mp4`, with the narration burned in as
subtitles and also saved as `out/<name>.srt` (capture with `--no-subtitles` to leave them out).
Give the user the path, its length, and the review points in one short message. `render.py studio <folder>` opens Remotion Studio
for scrubbing; `render.py still <folder> --frame N` renders one frame.

## Known limits (v1)

- Hard cuts between shots; no zoom or spotlight. A `crop` frames a part of the screen statically.
- Code cards have +/− colouring but no syntax highlighting, and at most 24 rows each.
- The narration starts with its beat; it doesn't sync to individual clicks inside a beat.
- Remotion is free for individuals and companies of up to 3 people; check its license before
  using it at a larger company.
