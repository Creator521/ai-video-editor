from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from editor.assemble import _run, concat_and_mix, make_music, render_shot, _ffprobe_duration
from editor.images import generate_all_images
from editor.script import build_script
from editor.style import VOICES
from editor.title import make_title_card
from editor.tts import synthesize_all

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
Progress = Callable[[str], None]


def run_pipeline(
    topic: str,
    minutes: float = 1.0,
    language: str = "English",
    voice_label: str = "English (US, documentary)",
    music_path: str | None = None,
    max_scenes: int | None = None,
    progress: Progress | None = None,
) -> dict:
    def log(msg: str) -> None:
        if progress:
            progress(msg)

    OUTPUTS.mkdir(exist_ok=True)
    job_dir = OUTPUTS / datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "shots").mkdir(exist_ok=True)
    (job_dir / "audio").mkdir(exist_ok=True)
    (job_dir / "images").mkdir(exist_ok=True)

    voice = VOICES.get(voice_label, "en-US-AndrewNeural")
    script = build_script(topic.strip(), minutes, language, job_dir, log, max_scenes=max_scenes)

    log("Creating opening title…")
    title_png = make_title_card(script["title"], script.get("subtitle", ""), job_dir / "images" / "title.png")
    title_audio = job_dir / "audio" / "title_silence.mp3"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            "3",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(title_audio),
        ]
    )

    images = generate_all_images(script, job_dir, log)
    audios = synthesize_all(script, voice, job_dir, log)

    shots: list[Path] = []
    title_shot = job_dir / "shots" / "shot_000.mp4"
    log("Editing opening title…")
    render_shot(title_png, title_audio, title_shot, "in")
    shots.append(title_shot)

    motions = ["in", "out"]
    for i, (scene, image, audio) in enumerate(zip(script["scenes"], images, audios)):
        log(f"Editing shot {scene['id']}/{len(script['scenes'])}…")
        dest = job_dir / "shots" / f"shot_{scene['id']:03d}.mp4"
        render_shot(image, audio, dest, motions[i % 2])
        shots.append(dest)

    total = sum(_ffprobe_duration(p) for p in shots)
    user_music = Path(music_path) if music_path else None
    music = make_music(total, job_dir / "music.m4a", user_music)
    final = concat_and_mix(shots, music, job_dir / "final.mp4", log)

    meta = {
        "job_dir": str(job_dir),
        "final": str(final),
        "title": script["title"],
        "scenes": len(script["scenes"]),
        "duration_sec": total,
    }
    (job_dir / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log("Done.")
    return meta
