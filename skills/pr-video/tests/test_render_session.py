"""Small pure pieces of render.py and session.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import render


def test_video_is_named_after_the_folder_and_title(tmp_path):
    assert render.video_name(tmp_path / "pr-42", {"title": "Retry: uploads!"}) == "pr-42-retry-uploads.mp4"


def test_render_needs_a_capture_first(tmp_path):
    with pytest.raises(SystemExit, match="capture.py"):
        render.flags(tmp_path / "captures")


def test_flags_serve_the_captures_folder(tmp_path):
    (tmp_path / "timeline.json").write_text("{}")
    assert render.flags(tmp_path) == [f"--public-dir={tmp_path}", f"--props={tmp_path / 'timeline.json'}"]


def test_one_browser_profile_per_app_origin():
    session = pytest.importorskip("session")
    assert session.profile_for("http://localhost:5173").name == "localhost-5173"
    assert session.profile_for("https://app.example.com").name == "app-example-com-https"
    assert session.reachable("http://127.0.0.1:9") is False


def test_an_auth_gated_or_missing_root_still_counts_as_answering():
    session = pytest.importorskip("session")
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(int(self.path.strip("/")))
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert session.reachable(f"{base}/401") is True
        assert session.reachable(f"{base}/404") is True
        assert session.reachable(f"{base}/503") is False
    finally:
        server.shutdown()


def test_an_interrupted_install_is_redone(tmp_path, monkeypatch):
    calls = []
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "node_modules").mkdir()  # left behind by a cut-off npm ci
    monkeypatch.setattr(render, "REMOTION", tmp_path)
    monkeypatch.setattr(render.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(render.subprocess, "run", lambda args, **kw: calls.append(args))
    render.ensure_installed()
    assert calls and calls[0][:2] == ["npm", "ci"]
    calls.clear()
    render.ensure_installed()  # finished once: not again
    assert calls == []
    (tmp_path / "package-lock.json").write_text('{"v": 2}')  # a plugin update changes the lockfile
    render.ensure_installed()
    assert calls


def test_missing_npm_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "REMOTION", tmp_path)
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="Node.js"):
        render.ensure_installed()


def test_a_failed_render_is_reported_not_traced(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(render, "ensure_installed", lambda: None)

    def fail(args, **kw):
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(render.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="NOT RENDERED"):
        render.remotion(["render"])


def test_subtitles_are_written_beside_the_video(tmp_path):
    import json
    (tmp_path / "timeline.json").write_text(json.dumps(
        {"fps": 30, "subtitles": [{"from": 0, "duration": 30, "text": "Hello."}]}))
    video = tmp_path / "out" / "pr-1-x.mp4"
    video.parent.mkdir()
    assert render.write_srt(tmp_path, video) == video.with_suffix(".srt")
    assert video.with_suffix(".srt").read_text() == "1\n00:00:00,000 --> 00:00:01,000\nHello.\n"


def test_no_srt_when_there_are_no_subtitles(tmp_path):
    (tmp_path / "timeline.json").write_text('{"fps": 30, "subtitles": []}')
    assert render.write_srt(tmp_path, tmp_path / "v.mp4") is None
    assert not (tmp_path / "v.srt").exists()
