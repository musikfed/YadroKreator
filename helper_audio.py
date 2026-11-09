"""Stage a pre-rendered and validated spoken boot greeting for the Helper camera.

The Russian TTS voice is generated in the wifcam_helper GitHub workflow.
The builder reads only a fixed WAV asset, NEVER executes source scripts from
the fetched Helper repository, and writes raw PCM for Raptor's `play`.
"""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

SAMPLE_RATE = 16000
MAX_SECONDS = 15
MIN_SECONDS = 1
WAV_PATH = "firmware/audio/boot-voice.wav"
MAX_WAV_BYTES = (SAMPLE_RATE * MAX_SECONDS * 2) + 4096


def inspect_voice(path: Path) -> tuple[int, bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_WAV_BYTES:
        raise ValueError("Missing, unsafe or oversized Helper voice WAV asset; run its GitHub voice workflow")
    try:
        with wave.open(str(path), "rb") as reader:
            if (reader.getnchannels(), reader.getframerate(), reader.getsampwidth(),
                    reader.getcomptype()) != (1, SAMPLE_RATE, 2, "NONE"):
                raise ValueError("Helper voice must be PCM signed 16-bit mono 16000Hz WAV")
            frames = reader.getnframes()
            if not (SAMPLE_RATE * MIN_SECONDS <= frames <= SAMPLE_RATE * MAX_SECONDS):
                raise ValueError("Helper startup phrase must last 1–15 seconds")
            payload = reader.readframes(frames)
            if len(payload) != frames * 2:
                raise ValueError("Truncated Helper voice WAV")
            return frames, payload
    except (wave.Error, EOFError, OSError) as exc:
        raise ValueError("Invalid or truncated Helper voice WAV") from exc


def stage_voice(source: Path, target: Path) -> tuple[Path, Path]:
    frames, pcm = inspect_voice(source)
    target.mkdir(parents=True, exist_ok=True)
    wav = target / "boot-voice.wav"
    raw = target / "boot-voice.s16le"
    shutil.copyfile(source, wav)
    raw.write_bytes(pcm)
    if raw.stat().st_size != frames * 2:
        raise RuntimeError("Incorrect Helper speaker PCM length")
    return wav, raw
