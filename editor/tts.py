from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import edge_tts

Progress = Callable[[str], None]


async def _speak(text: str, voice: str, dest: Path) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate="-8%")
    await communicate.save(str(dest))


def synthesize_all(script: dict, voice: str, job_dir: Path, progress: Progress | None = None) -> list[Path]:
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    paths: list[Path] = []

    async def run() -> None:
        for scene in script["scenes"]:
            dest = audio_dir / f"scene_{scene['id']:03d}.mp3"
            if progress:
                progress(f"Recording narration {scene['id']}/{len(script['scenes'])}…")
            await _speak(scene["narration"], voice, dest)
            paths.append(dest)

    asyncio.run(run())
    return paths
