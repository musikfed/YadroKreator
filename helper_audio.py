"""Safe and deterministic sound renderer for the wifcam_helper camera firmware.

The sound composition (data only) lives in wifcam_helper/firmware/audio.
Do not execute Python or shell code supplied by the source repository.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import random
import struct
import wave

EXPECTED_KEYS = {"schema", "name", "sample_rate", "device_sample_rate",
                 "duration_seconds", "noise_seed", "notes", "events", "noise"}
SAMPLE_RATE = 11025
DEVICE_RATE = 16000
DURATION = 7
PCM_BYTES = DEVICE_RATE * DURATION * 2


def read_score(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12_000:
        raise ValueError("Camera sound manifest must be a regular small file")
    score = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(score, dict) or set(score) != EXPECTED_KEYS:
        raise ValueError("Unexpected sound manifest fields")
    if score["schema"] != "peginelab.boot-jingle.v1" or not isinstance(score["name"], str):
        raise ValueError("Unexpected sound score schema")
    if (type(score["sample_rate"]) is not int or score["sample_rate"] != SAMPLE_RATE or
        type(score["device_sample_rate"]) is not int or score["device_sample_rate"] != DEVICE_RATE or
        type(score["duration_seconds"]) is not int or score["duration_seconds"] != DURATION or
        type(score["noise_seed"]) is not int or not (0 <= score["noise_seed"] <= 100000)):
        raise ValueError("Unsupported camera audio format")
    notes = score["notes"]
    events = score["events"]
    noise = score["noise"]
    if (not isinstance(notes, dict) or not (1 <= len(notes) <= 24) or
        not isinstance(events, list) or not (1 <= len(events) <= 64) or
        not isinstance(noise, list) or len(noise) > 8):
        raise ValueError("Unbounded sound score")
    for key, hz in notes.items():
        if not isinstance(key, str) or not key.isalnum() or len(key) > 5 or type(hz) not in (int, float) or not (70 <= hz <= 4000):
            raise ValueError("Invalid note frequency")
    for e in events:
        if (not isinstance(e, list) or len(e) != 4 or
            type(e[0]) not in (int, float) or type(e[1]) not in (int, float) or
            not isinstance(e[2], str) or e[2] not in notes or
            type(e[3]) not in (int, float) or not
            (0 <= e[0] < DURATION and 0.01 <= e[1] <= 1 and e[0] + e[1] <= DURATION and 0 < e[3] <= 0.7)):
            raise ValueError("Invalid note event")
    for e in noise:
        if (not isinstance(e, list) or len(e) != 3 or
            any(type(v) not in (int, float) for v in e) or
            not (0 <= e[0] < DURATION and 0 < e[1] <= 0.1 and e[0] + e[1] <= DURATION and 0 <= e[2] <= 0.2)):
            raise ValueError("Invalid bounded noise event")
    return score


def render_score(score: dict, target: Path) -> tuple[Path, Path]:
    """Write 11025 Hz 8-bit WAV + 16000 Hz signed 16-bit mono raw PCM."""
    n = SAMPLE_RATE * DURATION
    samples = [0.0] * n
    for start, dur, note, amp in score["events"]:
        freq = score["notes"][note]
        first, last = int(start * SAMPLE_RATE), min(n, int((start + dur) * SAMPLE_RATE))
        for i in range(first, last):
            t = (i - first) / SAMPLE_RATE
            rel = (i - first) / max(1, last - first)
            env = min(1., t / .008) * min(1., (1 - rel) / .12)
            sq = 1. if math.sin(2 * math.pi * freq * t) >= 0 else -1.
            sq2 = 1. if math.sin(4 * math.pi * freq * t) >= 0 else -1.
            samples[i] += amp * env * (.82 * sq + .18 * sq2)
    rng = random.Random(score["noise_seed"])
    for start, dur, amp in score["noise"]:
        for i in range(int(start * SAMPLE_RATE), min(n, int((start + dur) * SAMPLE_RATE))):
            samples[i] += amp * (1 if rng.random() > .5 else -1)
    target.mkdir(parents=True, exist_ok=True)
    wav = target / "boot-jingle.wav"
    pcm = target / "boot-jingle.s16le"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(bytes(int(128 + max(-.95, min(.95, x)) * 120) & 255 for x in samples))
    with pcm.open("wb") as writer:
        for i in range(DEVICE_RATE * DURATION):
            source = i * SAMPLE_RATE / DEVICE_RATE
            idx = min(int(source), n - 1)
            nxt = min(idx + 1, n - 1)
            sample = samples[idx] + (samples[nxt] - samples[idx]) * (source - idx)
            signed = int(max(-.75, min(.75, sample)) * 16384)
            writer.write(struct.pack("<h", signed))
    if pcm.stat().st_size != PCM_BYTES:
        raise RuntimeError("Generated camera audio has unexpected size")
    return wav, pcm
