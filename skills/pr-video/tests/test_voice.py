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


MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413  # MPEG-1 Layer III, 128 kbps, 44.1 kHz: 417 bytes, 1152 samples
MP3_FRAME_SECONDS = 1152 / 44100


def test_duration_of_an_mp3(tmp_path):
    (tmp_path / "a.mp3").write_bytes(MP3_FRAME * 40)
    assert voice.duration(tmp_path / "a.mp3") == pytest.approx(40 * MP3_FRAME_SECONDS, abs=0.05)


def test_an_unreadable_mp3_names_the_file(tmp_path):
    (tmp_path / "bad.mp3").write_bytes(b"not audio")
    with pytest.raises(ValueError, match="bad.mp3"):
        voice.duration(tmp_path / "bad.mp3")


def fake_download(content: bytes):
    def retrieve(url: str, path: Path) -> None:
        Path(path).write_bytes(content)
    return retrieve


def test_setup_keeps_a_download_that_matches_its_pinned_hash(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(voice.urllib.request, "urlretrieve", fake_download(b"model"))
    monkeypatch.setattr(voice, "MODEL_SHA256", {name: hashlib.sha256(b"model").hexdigest() for name in voice.MODEL_FILES})
    voice.setup(tmp_path)
    assert voice.model_ready(tmp_path)


def test_setup_refuses_a_download_that_doesnt_match(tmp_path, monkeypatch):
    monkeypatch.setattr(voice.urllib.request, "urlretrieve", fake_download(b"tampered"))
    with pytest.raises(voice.VoiceError, match="checksum"):
        voice.setup(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_every_model_file_has_a_pinned_hash():
    assert set(voice.MODEL_SHA256) == set(voice.MODEL_FILES)


def test_no_copyleft_dependencies():
    """The skill is MIT; company legal scans flag GPL libraries even when they're only fetched at run time."""
    scripts = Path(voice.__file__).parent
    headers = "".join(p.read_text().split("# ///", 2)[1] for p in scripts.glob("*.py") if "# /// script" in p.read_text())
    assert "mutagen" not in headers


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


def test_setup_turns_a_network_failure_into_a_voice_error(tmp_path, monkeypatch):
    def broken(url: str, path: Path) -> None:
        Path(path).write_bytes(b"half")
        raise OSError("connection reset")
    monkeypatch.setattr(voice.urllib.request, "urlretrieve", broken)
    with pytest.raises(voice.VoiceError, match="connection reset"):
        voice.setup(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_say_accepts_allow_edge(monkeypatch, tmp_path):
    spoken = []
    monkeypatch.setattr(voice, "model_ready", lambda: False)
    monkeypatch.setattr(voice, "speaker", lambda engine, name: lambda text, out: spoken.append((engine, text, out)))
    monkeypatch.setattr(voice, "duration", lambda path: 1.0)
    monkeypatch.setattr(sys, "argv", ["voice.py", "say", "hi", str(tmp_path / "o.mp3"), "--allow-edge"])
    voice.main()
    assert spoken == [("edge", "hi", tmp_path / "o.mp3")]


def test_main_reports_a_failed_setup_without_a_traceback(monkeypatch):
    def fail(*_a, **_k) -> None:
        raise voice.VoiceError("checksum")
    monkeypatch.setattr(voice, "setup", fail)
    monkeypatch.setattr(sys, "argv", ["voice.py", "setup"])
    with pytest.raises(SystemExit, match="NO VOICE: checksum"):
        voice.main()
