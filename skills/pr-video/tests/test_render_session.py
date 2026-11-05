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
