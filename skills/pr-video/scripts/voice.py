# /// script
# requires-python = ">=3.10"
# dependencies = ["kokoro-onnx>=0.4", "edge-tts>=6.1", "tinytag>=2.1"]
# ///
"""Speak each beat's narration, locally by default.

    uv run voice.py setup                     # one-time: fetch the Kokoro model (~120 MB)
    uv run voice.py say "Some words" out.wav  # try a voice

**Kokoro** (``kokoro-onnx``) runs on this machine; nothing leaves it. **edge-tts** is the free
fallback, but it sends the narration text to Microsoft's online speech service, and narration
describes the code — so it runs only with ``--allow-edge`` or ``PR_VIDEO_ALLOW_EDGE=1``, never
by itself. Clips are cached by engine, voice and text in ``~/.cache/pr-video/tts``, so a
re-capture only speaks the lines that changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path

CACHE = Path.home() / ".cache" / "pr-video"
MODEL_DIR = CACHE / "kokoro"
TTS_CACHE = CACHE / "tts"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
ENGINES = ("auto", "kokoro", "edge")
VOICES = {"kokoro": "af_heart", "edge": "en-US-AriaNeural"}
SUFFIX = {"kokoro": ".wav", "edge": ".mp3"}
KOKORO_SPEED = 1.05
EDGE_WARNING = ("edge-tts sends the narration text to Microsoft's online speech service; allow it with "
                "--allow-edge or PR_VIDEO_ALLOW_EDGE=1 only when the PR's content may leave this machine")


class VoiceError(RuntimeError):
    """No voice engine can run under the current settings."""


def model_ready(folder: Path = MODEL_DIR) -> bool:
    return all((folder / name).exists() for name in MODEL_FILES)


def edge_allowed(flag: bool) -> bool:
    return flag or os.environ.get("PR_VIDEO_ALLOW_EDGE") == "1"


def choose_engine(requested: str, model_ready: bool, allow_edge: bool) -> str:
    if requested not in ENGINES:
        raise VoiceError(f"voice engine {requested!r}: use one of {', '.join(ENGINES)}")
    setup = f"the Kokoro model is not in {MODEL_DIR} — run `uv run voice.py setup` (about 120 MB, once)"
    if requested == "kokoro" and not model_ready:
        raise VoiceError(setup)
    if requested == "edge" and not allow_edge:
        raise VoiceError(EDGE_WARNING)
    if requested != "auto":
        return requested
    if model_ready:
        return "kokoro"
    if allow_edge:
        return "edge"
    raise VoiceError(f"{setup}; or {EDGE_WARNING}; or capture with --silent")


def cache_key(engine: str, voice_name: str, text: str) -> str:
    return hashlib.sha256(f"{engine}\0{voice_name}\0{text}".encode()).hexdigest()[:20]


def duration(path: Path) -> float:
    if path.suffix == ".wav":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    from tinytag import TinyTag  # mp3 from edge-tts (MIT; replaces GPL mutagen)

    seconds = TinyTag.get(str(path)).duration
    if seconds is None:
        raise ValueError(f"can't read the length of {path}")
    return float(seconds)


def voice_beats(beats: list[dict], captures: Path, speak: Callable[[str, Path], None], engine: str,
                voice_name: str, cache: Path = TTS_CACHE, measure: Callable[[Path], float] = duration) -> list[dict]:
    """New beats, each with ``voice: {src, seconds}`` (or ``None`` when it says nothing). The clip
    is copied into ``captures/audio/`` because that is the folder Remotion serves."""
    audio = captures / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for beat in beats:
        text = (beat.get("say") or "").strip()
        if not text:
            out.append({**beat, "voice": None})
            continue
        cached = cache / f"{cache_key(engine, voice_name, text)}{SUFFIX[engine]}"
        if not cached.exists():
            speak(text, cached)
        clip = audio / f"{beat['id']}{SUFFIX[engine]}"
        shutil.copyfile(cached, clip)
        out.append({**beat, "voice": {"src": f"audio/{clip.name}", "seconds": measure(clip)}})
    return out


def kokoro_speaker(voice_name: str) -> Callable[[str, Path], None]:
    import numpy as np
    from kokoro_onnx import Kokoro

    model = Kokoro(str(MODEL_DIR / MODEL_FILES[0]), str(MODEL_DIR / MODEL_FILES[1]))

    def speak(text: str, out: Path) -> None:
        samples, rate = model.create(text, voice=voice_name, speed=KOKORO_SPEED, lang="en-us")
        pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
        part = out.with_suffix(".part")
        with wave.open(str(part), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        part.rename(out)

    return speak


def edge_speaker(voice_name: str) -> Callable[[str, Path], None]:
    import edge_tts

    def speak(text: str, out: Path) -> None:
        part = out.with_suffix(".part")
        asyncio.run(edge_tts.Communicate(text, voice_name).save(str(part)))
        part.rename(out)

    return speak


def speaker(engine: str, voice_name: str) -> Callable[[str, Path], None]:
    return kokoro_speaker(voice_name) if engine == "kokoro" else edge_speaker(voice_name)


def setup() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        target = MODEL_DIR / name
        if target.exists():
            print(f"have {target}")
            continue
        print(f"fetching {name} …")
        part = target.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL + name, part)
        part.rename(target)
    print(f"Kokoro model ready in {MODEL_DIR}")


def main() -> None:
    if sys.argv[1:2] == ["setup"]:
        setup()
    elif sys.argv[1:2] == ["say"] and len(sys.argv) == 4:
        engine = choose_engine("auto", model_ready(), edge_allowed("--allow-edge" in sys.argv))
        speaker(engine, VOICES[engine])(sys.argv[2], Path(sys.argv[3]))
        print(f"{engine}: {sys.argv[3]} ({duration(Path(sys.argv[3])):.1f} s)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
