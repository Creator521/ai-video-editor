from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

Progress = Callable[[str], None]


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Voice-led visuals need faster-whisper. Install the project requirements first."
        ) from exc
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def file_signature(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transcribe_audio(
    audio_path: Path,
    language: str = "English",
    progress: Progress | None = None,
) -> dict[str, Any]:
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(f"Voice recording not found: {audio_path}")

    model_name = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    if progress:
        progress(f"Loading local Whisper model ({model_name})…")
    model = _load_model(model_name)
    language_code = "hi" if language.lower().startswith("hindi") else "en"
    segments, info = model.transcribe(
        str(audio_path),
        language=language_code,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    words: list[dict[str, Any]] = []
    segment_count = 0
    for segment in segments:
        segment_count += 1
        for word in segment.words or []:
            text = str(word.word or "").strip()
            if not text or word.start is None or word.end is None:
                continue
            start, end = float(word.start), float(word.end)
            if end <= start:
                continue
            words.append({"word": text, "start": start, "end": end})
        if progress and segment_count % 10 == 0:
            progress(f"Transcribed {segment_count} audio segments…")

    if not words:
        raise RuntimeError("No speech words were detected in the recording.")
    return {
        "language": str(getattr(info, "language", language_code)),
        "text": " ".join(word["word"] for word in words),
        "words": words,
    }
