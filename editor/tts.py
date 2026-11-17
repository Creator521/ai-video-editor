from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import edge_tts

Progress = Callable[[str], None]


async def _synthesize_scene(
    text: str,
    voice: str,
    dest: Path,
) -> list[dict[str, Any]]:
    communicate = edge_tts.Communicate(text, voice=voice, rate="-8%")
    audio = bytearray()
    words: list[dict[str, Any]] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk.get("data", b""))
        elif chunk["type"] == "WordBoundary":
            word = str(chunk.get("text", "")).strip()
            if word:
                start = float(chunk["offset"]) / 10_000_000
                end = (float(chunk["offset"]) + float(chunk["duration"])) / 10_000_000
                words.append({"word": word, "start": start, "end": end})

    if not audio:
        raise RuntimeError("Edge TTS returned no audio.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(audio)
    return words


def synthesize_scene(text: str, voice: str, dest: Path) -> list[dict[str, Any]]:
    return asyncio.run(_synthesize_scene(text, voice, dest))


def synthesize_all(
    script: dict,
    voice: str,
    job_dir: Path,
    progress: Progress | None = None,
    word_timings: list[dict[str, Any]] | None = None,
) -> list[Path]:
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    paths: list[Path] = []

    async def run() -> None:
        for scene in script["scenes"]:
            dest = audio_dir / f"scene_{scene['id']:03d}.mp3"
            if progress:
                progress(f"Recording narration {scene['id']}/{len(script['scenes'])}…")
            scene_words = await _synthesize_scene(scene["narration"], voice, dest)
            if word_timings is not None:
                word_timings.extend(
                    {"scene_id": scene["id"], **word}
                    for word in scene_words
                )
            paths.append(dest)

    asyncio.run(run())
    return paths
