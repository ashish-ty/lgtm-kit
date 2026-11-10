"""End to end on a real browser: a tiny repo with a PR branch, served locally, made into a video.

Needs Playwright and Chrome or Playwright's Chromium; skipped without them. Voicing runs when the
Kokoro model is set up; rendering the MP4 runs only with PR_VIDEO_E2E_RENDER=1 (it takes ~30 s).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture
import crawl_app
import prepare
import render
import session
import timeline
import voice

pytestmark = pytest.mark.e2e

BASE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Uploads</title></head>
<body style="font-family:system-ui;margin:60px"><h1>Upload queue</h1><button id="go">Upload</button>
<div id="out"></div><script>go.onclick=()=>{out.textContent='Uploaded 3 files';};</script></body></html>"""
PR_PAGE = BASE_PAGE.replace("'Uploaded 3 files'", "'Uploaded 3 files · 1 retry'")
WORKER = "def upload(client, path):\n    client.put(path)\n    return client\n"
PR_WORKER = ("RETRIES = 3\n\n\ndef upload(client, path):\n    for _ in range(RETRIES):\n"
             "        if client.put(path):\n            return client\n    raise RuntimeError(path)\n")
RICH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Settings</title></head>
<body style="font-family:system-ui;margin:60px"><h1>Upload settings</h1>
<label>Retries</label><div><button aria-haspopup="listbox" id="rt">3</button>
<ul role="listbox" id="rl" hidden><li role="option">1</li><li role="option">3</li><li role="option">5</li></ul></div>
<label>Region</label><div><button aria-haspopup="listbox" id="rg">eu</button></div>
<label>Bucket</label><input id="bucket" placeholder="bucket name">
<div><div id="failed">42</div><div>FAILED UPLOADS</div></div>
<button aria-label="Help" title="Retries back off exponentially">?</button>
<table><thead><tr><th>Worker</th><th>Errors</th></tr></thead><tbody><tr><td>api</td><td>7</td></tr></tbody></table>
<div style="height:1600px"></div><h2>Audit log</h2>
<script>
rt.onclick=()=>{rl.hidden=!rl.hidden;};
rg.onclick=()=>{  // a portaled list, as Radix, MUI and Headless UI render: into <body>, far from its label
  const ul=document.createElement('ul'); ul.setAttribute('role','listbox');
  for (const v of ['eu','us']) { const li=document.createElement('li'); li.setAttribute('role','option');
    li.textContent=v; li.onclick=()=>{rg.textContent=v; ul.remove();}; ul.append(li); }
  document.body.append(ul);
};
for (const li of rl.children) li.onclick=()=>{rt.textContent=li.textContent;rl.hidden=true;failed.textContent=String(40+Number(li.textContent));};
</script></body></html>"""
OTHER_PAGE = "<!doctype html><html><body><h1>Other page</h1></body></html>"
EVERY_ACTION = """# Every live action

```yaml
title: Settings tour
app: {app}
start: /rich.html
scenes:
  - id: tour
    beats:
      - id: retries
        do: select
        target: {{label: Retries}}
        value: "5"
        figures: {{failed: {{stat: Failed uploads}}}}
        caption: "{{failed}} failed"
        hold: 0.5
      - id: bucket
        do: type
        target: {{label: Bucket}}
        text: logs-archive
        typing: true
        hold: 0.5
      - id: help
        do: hover
        target: {{role: button, name: Help}}
        hold: 0.5
      - id: errors
        do: show
        figures: {{errors: {{cell: {{row: api, column: Errors}}}}}}
        caption: "api errors: {{errors}}"
        crop: [0, 0, 960]
        hold: 0.5
      - id: close
        do: press
        key: Escape
        hold: 0.5
      - id: audit
        do: scroll
        target: {{text: Audit log}}
        hold: 0.5
      - id: away
        do: go
        route: /other.html
        hold: 0.5
```
"""
STORYBOARD = """# Walkthrough

```yaml
app: {app}
start: /index.html
review_points: [Check callers handle RuntimeError]
scenes:
  - id: all
    beats:
      - id: files
        do: overview
        say: Two files change.
      - id: loop
        do: code
        file: worker.py
        say: Upload retries three times, then raises.
      - id: click
        do: click
        target: {{role: button, name: {button}}}
        figures: {{result: {{text: "Uploaded 3 files · 1 retry"}}}}
        caption: "{{result}}"
        say: The page reports {{result}}.
```
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("e2e") / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "index.html").write_text(BASE_PAGE)
    (root / "worker.py").write_text(WORKER)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", "feat/retry")
    (root / "index.html").write_text(PR_PAGE)
    (root / "worker.py").write_text(PR_WORKER)
    (root / "rich.html").write_text(RICH_PAGE)
    (root / "other.html").write_text(OTHER_PAGE)
    git(root, "add", ".")
    git(root, "commit", "-qm", "feat: retry uploads")
    return root


@pytest.fixture(scope="module")
def app(repo: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(repo)))
    server.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def folder(repo: Path, app: str) -> Path:
    try:
        with session.open_page(app) as page:
            page.goto(app)
    except Exception as err:  # noqa: BLE001 — no browser on this machine
        pytest.skip(f"no browser for Playwright: {err}")
    return prepare.run(repo, pr=None, base="main", head="feat/retry")


def write_board(folder: Path, app: str, button: str = "Upload") -> Path:
    path = folder / "storyboard.md"
    path.write_text(STORYBOARD.format(app=app, button=button))
    return path


def test_the_app_is_crawled_into_a_catalogue(folder: Path, app: str, monkeypatch):
    out = folder / "catalogue.json"
    monkeypatch.setattr(sys, "argv", ["crawl_app.py", "--app", app, "--route", "/index.html", "--out", str(out)])
    crawl_app.main()
    screen = json.loads(out.read_text())["routes"]["/index.html"]
    assert "Upload" in screen["buttons"] and "Upload queue" in screen["headings"]


def test_a_silent_capture_films_live_beats_and_cuts_cards(folder: Path, app: str):
    captures = capture.run(write_board(folder, app), silent=True, engine_name="auto", allow_edge=False)
    manifest = json.loads((captures / "manifest.json").read_text())
    by_id = {b["id"]: b for b in manifest["beats"]}
    assert by_id["click"]["caption"] == "Uploaded 3 files · 1 retry"
    assert by_id["click"]["say"] == "The page reports Uploaded 3 files · 1 retry."
    assert [s["cursor"] is not None for s in by_id["click"]["shots"]] == [True, False]
    assert by_id["loop"]["card"]["file"] == "worker.py"
    assert by_id["files"]["card"]["totals"]["files"] == 4
    assert all((captures / s["image"]).exists() for s in by_id["click"]["shots"])
    assert (captures / "contact-sheet.png").exists()
    assert json.loads((captures / "timeline.json").read_text())["audio"] == []
    assert manifest["subtitles"] is True and json.loads((captures / "timeline.json").read_text())["subtitles"] == []


def test_subtitles_can_be_turned_off(folder: Path, app: str):
    captures = capture.run(write_board(folder, app), silent=True, engine_name="auto", allow_edge=False,
                           subtitles=False)
    assert json.loads((captures / "manifest.json").read_text())["subtitles"] is False


def test_every_live_action_is_filmed(folder: Path, app: str):
    path = folder / "storyboard.md"
    path.write_text(EVERY_ACTION.format(app=app))
    captures = capture.run(path, silent=True, engine_name="auto", allow_edge=False)
    beats = {b["id"]: b for b in json.loads((captures / "manifest.json").read_text())["beats"]}
    assert beats["retries"]["caption"] == "45 failed"
    assert len(beats["retries"]["shots"]) == 3  # closed, open, result
    assert len(beats["bucket"]["shots"]) > 3  # typed in steps
    assert beats["help"]["shots"][0]["click"] is False
    assert beats["errors"]["caption"] == "api errors: 7"
    assert [len(beats[b]["shots"]) for b in ("close", "audit", "away")] == [1, 1, 1]


def test_a_target_the_pr_does_not_have_stops_the_capture(folder: Path, app: str):
    with pytest.raises(SystemExit, match="finding"):
        capture.run(write_board(folder, app, button="Retry now"), silent=True, engine_name="auto", allow_edge=False)
    assert (folder / "captures" / "STOPPED-click.png").exists()


def test_an_app_that_is_not_running_is_reported(folder: Path):
    with pytest.raises(SystemExit, match="NOT READY"):
        capture.run(write_board(folder, "http://127.0.0.1:9"), silent=True, engine_name="auto", allow_edge=False)


@pytest.mark.skipif(not voice.model_ready(), reason="Kokoro model not set up (voice.py setup)")
def test_a_voiced_capture_and_render(folder: Path, app: str):
    pytest.importorskip("kokoro_onnx")
    captures = capture.run(write_board(folder, app), silent=False, engine_name="kokoro", allow_edge=False)
    audio = json.loads((captures / "timeline.json").read_text())["audio"]
    assert [a["src"] for a in audio] == ["audio/files.wav", "audio/loop.wav", "audio/click.wav"]
    if os.environ.get("PR_VIDEO_E2E_RENDER") != "1":
        return
    subprocess.run([sys.executable, str(Path(render.__file__)), "render", str(folder)], check=True)
    assert list((folder / "out").glob("*.mp4"))


PORTAL = """# Portaled dropdown

```yaml
title: Region
app: {app}
start: /rich.html
scenes:
  - id: one
    beats:
      - id: region
        do: select
        target: {{label: Region}}
        value: us
        figures: {{region: {{label: Region}}}}
        caption: "{{region}}"
        hold: 0.5
```
"""
STUCK = STORYBOARD.replace("start: /index.html", "start: /index.html\nbusy: '#go'")  # never stops being busy
TOO_LONG = """# Too long

```yaml
title: Long
scenes:
  - id: one
    beats:
      - id: files
        do: overview
        hold: 200
```
"""


def test_a_dropdown_rendered_into_the_body_is_picked(folder: Path, app: str):
    path = folder / "storyboard.md"
    path.write_text(PORTAL.format(app=app))
    captures = capture.run(path, silent=True, engine_name="auto", allow_edge=False)
    assert json.loads((captures / "manifest.json").read_text())["beats"][0]["caption"] == "us"


def test_a_page_that_never_settles_stops_with_a_report_and_keeps_the_last_capture(folder: Path, app: str,
                                                                                  monkeypatch):
    capture.run(write_board(folder, app), silent=True, engine_name="auto", allow_edge=False)
    monkeypatch.setattr(session, "BUSY_TIMEOUT_MS", 1500)
    (folder / "storyboard.md").write_text(STUCK.format(app=app, button="Upload"))
    with pytest.raises(SystemExit, match="STOPPED at the start page"):
        capture.run(folder / "storyboard.md", silent=True, engine_name="auto", allow_edge=False)
    assert (folder / "captures" / "manifest.json").exists()


def test_a_storyboard_over_three_minutes_is_refused_before_anything_runs(folder: Path, app: str):
    capture.run(write_board(folder, app), silent=True, engine_name="auto", allow_edge=False)
    before = (folder / "captures" / "timeline.json").read_text()
    (folder / "storyboard.md").write_text(TOO_LONG)
    with pytest.raises(timeline.LengthError, match="planned"):
        capture.run(folder / "storyboard.md", silent=True, engine_name="auto", allow_edge=False)
    assert (folder / "captures" / "timeline.json").read_text() == before
