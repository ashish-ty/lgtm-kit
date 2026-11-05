# lgtm-kit

**Agent skills that turn AI-written pull requests into something a human can actually review.**

Coding agents can open a 3,000-line PR in ten minutes. Reading it still takes a person an
afternoon. lgtm-kit is a small set of skills you drop into your coding agent to close that gap.

| Skill | What it does | Status |
|---|---|---|
| [`pr-video`](skills/pr-video/SKILL.md) | A narrated walkthrough video (≤ 3 min) of a PR: cards for the code that matters, the running app filmed with a synthetic cursor, and a local AI voiceover. | ✅ v0.1 |
| `pr-ship` | Ship work as small, test-first stacked PRs with local "ready for review" gates. | planned |
| `qa-chaos` | Exploratory QA and fault injection against a locally running app. | planned |

<!-- HERO VIDEO: replace with the Excalidraw demo once rendered -->

## pr-video

Ask your agent *"make a PR video for #42"*. It:

1. **Reads the PR** — diff, description, linked issue — and picks the 2–5 hunks a reviewer must see.
2. **Writes a storyboard** — an overview of the layers touched, code cards, a tests card, live
   beats in the app, and up to 4 honest *"check before you approve"* points.
3. **Films the real app** you started from the PR head (Playwright, synthetic cursor). If a
   screen the PR claims isn't there, that's reported as a finding — never faked.
4. **Speaks the narration locally** with [Kokoro](https://github.com/thewh1teagle/kokoro-onnx).
5. **Renders a 1080p MP4** with [Remotion](https://www.remotion.dev) into `<repo>/.pr-videos/`,
   which ignores itself in git.

Nothing is uploaded, nothing posts, nothing merges. Backend-only PRs get a cards-only video.

### Requirements

- [`uv`](https://docs.astral.sh/uv/) — every script declares its own dependencies (PEP 723); nothing is installed into your repo
- Node 18+ — Remotion installs on first render
- [`gh`](https://cli.github.com/), signed in — to read PRs by number (or use `--base main --head <branch>`)
- For live beats: Chrome, or `uvx playwright install chromium`
- First run: `uv run skills/pr-video/scripts/voice.py setup` downloads the Kokoro voice model (~120 MB) to `~/.cache/pr-video/`

Tested on **macOS**. Linux runs the unit tests in CI and should work. Windows: use WSL.

## Install

**Claude Code** (plugin marketplace):

```
/plugin marketplace add ashish-ty/lgtm-kit
/plugin install lgtm-kit@lgtm-kit
```

**Any agent** via the community [skills CLI](https://github.com/vercel-labs/skills):

```
npx skills add ashish-ty/lgtm-kit          # prompts for which agents to install into
npx skills add ashish-ty/lgtm-kit -a opencode -a gemini-cli -g
```

**By hand** — clone and symlink `skills/pr-video` into your agent's skills folder:

| Agent | Global skills folder | Project skills folder | Tested |
|---|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | ✅ |
| Gemini CLI | `~/.gemini/skills/` | `.gemini/skills/` or `.agents/skills/` | ⏳ before v0.1 |
| OpenCode | `~/.config/opencode/skills/` | `.opencode/skills/` | ⏳ before v0.1 |
| Codex CLI | `~/.codex/skills/` | `.agents/skills/` | should work |
| Cursor | — | `.cursor/skills/` | should work |

```
git clone https://github.com/ashish-ty/lgtm-kit ~/src/lgtm-kit
ln -s ~/src/lgtm-kit/skills/pr-video ~/.claude/skills/pr-video
```

The skills only ask the agent to run shell commands and write files, so any agent that can do
both should be able to drive them.

## Privacy

- Everything runs on your machine. The PR text and code never leave it, except through `gh`.
- The voice is local (Kokoro). [edge-tts](https://github.com/rany2/edge-tts) is an opt-in fallback
  that **sends the narration text to Microsoft**, so it only runs with `--allow-edge` or
  `PR_VIDEO_ALLOW_EDGE=1`. Without either voice, render with `--silent`.
- Sign-in sessions for live capture are kept in `~/.pr-video/`, never in the repo.

## ⚠️ Remotion license

pr-video renders with [Remotion](https://www.remotion.dev/license). Remotion is free for
individuals and for companies of **up to 3 people**; larger companies need a
[Remotion company license](https://www.remotion.dev/license). lgtm-kit's own code is MIT, but that
doesn't cover Remotion. Check before you use pr-video at work.

## Development

```
cd skills/pr-video
uv run --python 3.12 --with pytest --with pyyaml --with pillow --with mutagen pytest -q
cd remotion && npm ci && npm run typecheck
uvx ruff check skills
```

The browser E2E test (`tests/test_e2e.py`) runs when Playwright is installed; set
`PR_VIDEO_E2E_RENDER=1` to also render the MP4.

## License

[MIT](LICENSE) © 2026 Ashish Tyagi
