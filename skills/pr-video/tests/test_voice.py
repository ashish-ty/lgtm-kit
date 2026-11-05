"""Narration is local by default; the online fallback is only ever used when allowed."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import voice


def write_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * round(seconds * rate))


def test_auto_prefers_local_kokoro():
    assert voice.choose_engine("auto", model_ready=True, allow_edge=True) == "kokoro"


def test_auto_falls_back_to_edge_only_when_allowed():
    assert voice.choose_engine("auto", model_ready=False, allow_edge=True) == "edge"
    with pytest.raises(voice.VoiceError, match="voice.py setup"):
        voice.choose_engine("auto", model_ready=False, allow_edge=False)


def test_edge_asked_for_by_name_still_needs_the_allowance():
    with pytest.raises(voice.VoiceError, match="Microsoft"):
        voice.choose_engine("edge", model_ready=True, allow_edge=False)
    assert voice.choose_engine("edge", model_ready=True, allow_edge=True) == "edge"


def test_kokoro_asked_for_without_the_model_says_how_to_get_it():
    with pytest.raises(voice.VoiceError, match="voice.py setup"):
        voice.choose_engine("kokoro", model_ready=False, allow_edge=True)


def test_unknown_engine_is_refused():
    with pytest.raises(voice.VoiceError, match="engine"):
        voice.choose_engine("polly", model_ready=True, allow_edge=True)


def test_allow_edge_reads_the_environment(monkeypatch):
    monkeypatch.setenv("PR_VIDEO_ALLOW_EDGE", "1")
    assert voice.edge_allowed(False) is True
    monkeypatch.delenv("PR_VIDEO_ALLOW_EDGE")
    assert voice.edge_allowed(False) is False
    assert voice.edge_allowed(True) is True


def test_cache_key_changes_with_text_voice_and_engine():
    base = voice.cache_key("kokoro", "af_heart", "Hello.")
    assert base == voice.cache_key("kokoro", "af_heart", "Hello.")
    assert len({base, voice.cache_key("kokoro", "af_heart", "Hi."), voice.cache_key("kokoro", "am_adam", "Hello."),
                voice.cache_key("edge", "af_heart", "Hello.")}) == 4


def test_duration_of_a_wav(tmp_path):
    write_wav(tmp_path / "a.wav", 1.5)
    assert voice.duration(tmp_path / "a.wav") == pytest.approx(1.5)


def test_voice_beats_speaks_each_line_once_and_reuses_the_cache(tmp_path):
    spoken = []

    def speak(text: str, out: Path) -> None:
        spoken.append(text)
        write_wav(out, len(text) / 10)

    beats = [{"id": "a", "say": "Twenty chars of talk"}, {"id": "b", "say": None}, {"id": "c", "say": "Ten chars!"}]
    voiced = voice.voice_beats(beats, tmp_path / "captures", speak, "kokoro", "af_heart", cache=tmp_path / "cache")
    assert voiced[0]["voice"] == {"src": "audio/a.wav", "seconds": pytest.approx(2.0)}
    assert voiced[1]["voice"] is None
    assert (tmp_path / "captures" / "audio" / "c.wav").exists()
    assert "voice" not in beats[0]  # the input is left as it was
    voice.voice_beats(beats, tmp_path / "captures", speak, "kokoro", "af_heart", cache=tmp_path / "cache")
    assert spoken == ["Twenty chars of talk", "Ten chars!"]


def test_edge_clips_are_mp3(tmp_path):
    def speak(text: str, out: Path) -> None:
        assert out.suffix == ".mp3"
        out.write_bytes(b"")

    voiced = voice.voice_beats([{"id": "a", "say": "x"}], tmp_path, speak, "edge", "en-US-AriaNeural",
                               cache=tmp_path / "cache", measure=lambda p: 1.0)
    assert voiced[0]["voice"]["src"] == "audio/a.mp3"


def test_model_ready_needs_both_files(tmp_path):
    assert voice.model_ready(tmp_path) is False
    for name in voice.MODEL_FILES:
        (tmp_path / name).write_bytes(b"x")
    assert voice.model_ready(tmp_path) is True
