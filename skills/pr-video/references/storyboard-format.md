# Storyboard format

`storyboard.md` is prose for the reader plus **exactly one** ```yaml block, the contract the
capture carries out. `storyboard.py` refuses the file — before a browser opens or a voice speaks —
if a beat can't be carried out. It reads `diff.json` beside it to check every code beat.

```yaml
title: Uploads survive a flaky store   # optional; defaults to the PR title
app: http://localhost:5173             # only when there are live beats
start: /files                          # where the browser opens (live beats only)
busy: '[aria-busy="true"], .spinner'   # optional: what counts as "still loading"
settle_ms: 1200                        # optional: wait after loading, for charts to draw
layers:                                # optional, ≤ 6: group the overview by these instead of code/tests/generated
  - {name: API, paths: ["backend/*"]}  # globs; `*` also crosses `/`; first match wins; the rest is "other"
  - {name: UI, paths: ["frontend/*"]}
review_points:                         # optional, ≤ 4: the end card, "Check before you approve"
  - The final failure raises; check callers handle RuntimeError

scenes:
  - id: shape                          # scenes group beats for the reader; never on screen
    beats:
      - id: files
        do: overview
        say: Three files change. The worker gets retry logic, and there is one new test.
  - id: worker
    beats:
      - id: retry-loop
        do: code
        file: src/worker.py            # a path exactly as in diff.json
        hunk: 0                        # 0-based; default 0
        lines: [7, 18]                 # optional: new-file line numbers (old, for a deleted file)
        say: Upload now tries three times, doubling the wait, then raises.
  - id: live
    beats:
      - id: click-upload
        do: click
        target: {role: button, name: Upload}
        figures:
          result: {text: "Uploaded 3 files"}
        caption: "{result}"            # ≤ 90 characters, on the beat's result; {{ and }} for a literal brace
        say: Clicking Upload now reports {result}.
```

`pr`, `repo`, `base` and `head` come from `diff.json`; set them only to override.

## Beats

Every beat may carry `say:` (narration, ≤ 400 characters) and `hold:` (seconds on the result,
default 2.5). A beat lasts its hold or its narration plus a breath, whichever is longer.

### Cards (from the diff)

| `do` | Needs | Shows |
|---|---|---|
| `overview` | — | every changed file in groups — the storyboard's `layers`, else code / tests / generated — biggest first, with +/− bars (14 rows shown, the rest counted) |
| `tests` | — | the test files the PR touches and the names of the tests each adds (pytest, Jest/Vitest/Playwright `it`/`test`, Go). Listed, not run. Refused when the diff has no test files — put that in `review_points` instead |
| `code` | `file` | one hunk: both line numbers, + rows green, − rows red. Over 24 rows is refused: pick `lines: [first, last]` or split across beats |

`lines` slices by new-file numbers; a deleted line stays with the line after it. A card beat has
no `figures` and no cursor.

### Live (on the running app)

| `do` | Needs | Shots | Motion |
|---|---|---|---|
| `click` | `target` | before, after | cursor glides to the target and clicks |
| `hover` | `target` | before, after | cursor glides there, no click (tooltips) |
| `select` | `target`, `value` | closed, open, result | open the dropdown, click the option |
| `multiselect` | `target`, `values` | closed, one per value, result | open, tick each value; it closes off camera |
| `type` | `target`, `text` | before, after | click the field and type (`replace: true` clears it first) |
| `press` | `key` | after | none (e.g. `Escape`) |
| `scroll` | `target` | after | hard cut to the target in view |
| `go` | `route` | after | hard cut to another page |
| `show` | — | one | none; holds on the screen as it is |

The caption appears only on a beat's last shot, the result.

## Targets

Exactly one kind per target. Use the first that works, in this order:

| Kind | Reaches | Example |
|---|---|---|
| `role` + `name` | buttons, tabs, links by accessible name | `{role: button, name: Save}` |
| `label` | the control right after a `<label>` (custom dropdowns included) | `{label: Retries}` |
| `text` | any element by its whole visible text (ignores case) | `{text: Upload queue}` |
| `placeholder` | a text field known only by its hint | `{placeholder: Search files...}` |
| `option` | an entry in an open dropdown | `{option: Weekly}` |
| `stat` | the number printed beside a label on a stat tile | `{stat: Failed uploads}` |
| `cell` | a table cell by first-column row and header | `{cell: {row: api, column: Errors}}` |
| `demo` | `[data-demo=name]` — only if the PR adds it; never edit the app under review | `{demo: upload-table}` |
| `css` | last resort | `{css: ".queue-card"}` |

Names come from `catalogue.json`. Modifiers on any target: `at: [fx, fy]` (where inside the box
the cursor lands, as fractions — for a canvas chart) and `nth: first | last | N` (which match,
when a modal repeats a label from the page behind it; the modal's is usually `last`).

A beat can carry `wait_for: <target>`: after its action, the capture waits up to 3 minutes for it.
With `film_every: <seconds>` it takes a still at that interval until the target shows (each still
plays 0.45 s, so a wait plays sped up). `typing: true` on a `type` beat films the text being typed.

`${date:+14d}` in any text becomes that date from the capture day, as YYYY-MM-DD.

## Framing

`crop: [x, y, width]` makes that part of the 1920×1080 screen fill the video for the beat's result
(height follows at 16:9). The shots leading up to it keep the previous beat's framing while the
cursor's target is inside it. A card resets the framing.

## Figures

`figures` maps a name to a live target; its visible text fills `{name}` in the caption and in
`say`. So a number you say aloud is the number on screen.

## Private values

A value that must not sit in `storyboard.md` goes in `private.yaml` beside it and is referred to as
`${private.key}`. A key the file doesn't define refuses the storyboard. (`.pr-videos/` is not
committed anyway; this keeps such values out of anything you paste elsewhere.)
