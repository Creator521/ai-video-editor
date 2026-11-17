from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from editor.assemble import _ffprobe_duration, make_music
from editor.cinematic import (
    concatenate_audio,
    mux_documentary_audio,
    plan_scene_motion,
    render_storyboard,
    write_srt,
)
from editor.images import generate_all_images
from editor.jobs import create_job_dir
from editor.research import research_scene
from editor.script import build_script
from editor.style import VOICES
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

    job_dir = create_job_dir(OUTPUTS)

    voice = VOICES.get(voice_label, "en-US-AndrewNeural")
    topic = topic.strip()
    log("Researching the topic and image references…")
    try:
        research = research_scene(topic, language)
    except Exception as exc:  # noqa: BLE001
        research = {
            "query": topic,
            "sources": [],
            "image_candidates": [],
            "errors": [f"Research unavailable ({type(exc).__name__})."],
        }
    (job_dir / "research.json").write_text(
        json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for error in research.get("errors", []):
        log(f"Research warning: {error}")
    if not research.get("sources"):
        log("No research excerpts found; the script will avoid specific unsupported claims.")
    script = build_script(
        topic,
        minutes,
        language,
        job_dir,
        log,
        max_scenes=max_scenes,
        research_sources=research.get("sources", []),
    )

    images = generate_all_images(script, job_dir, log)
    word_timings: list[dict] = []
    audios = synthesize_all(script, voice, job_dir, log, word_timings=word_timings)

    voice_track = job_dir / "audio" / "narration.wav"
    total = concatenate_audio(audios, voice_track)
    target_duration = max(0.0, float(minutes) * 60.0)
    duration_warning = None
    if abs(total - target_duration) > max(5.0, target_duration * 0.15):
        duration_warning = (
            f"Rendered runtime is {total:.1f}s; selected target was {target_duration:.1f}s."
        )
        log(f"Length warning: {duration_warning}")
    timeline: list[dict] = []
    captions: list[dict] = []
    words_by_scene: dict[int, list[dict]] = {}
    for word in word_timings:
        words_by_scene.setdefault(int(word["scene_id"]), []).append(word)
    elapsed = 0.0
    for i, (scene, image, audio) in enumerate(zip(script["scenes"], images, audios)):
        end = elapsed + _ffprobe_duration(audio)
        captions.extend(
            {
                "word": word["word"],
                "start": elapsed + float(word["start"]),
                "end": elapsed + float(word["end"]),
            }
            for word in words_by_scene.get(int(scene["id"]), [])
        )
        timeline.append(
            {
                "start": elapsed,
                "end": end,
                "image": str(image),
                "narration": scene["narration"],
                "chapter": (
                    script["title"] if i == 0 else str(scene.get("card") or "")
                ),
                "year": str(scene.get("year") or ""),
                "language": script.get("language", language),
                "has_word_captions": bool(words_by_scene.get(int(scene["id"]))),
                "graphic_start": 0.0,
                "graphic_end": total,
                **plan_scene_motion(scene, i),
            }
        )
        elapsed = end

    timeline[-1]["end"] = total
    timeline_events = [
        {"label": scene["year"], "time": scene["start"]}
        for scene in timeline
        if scene["year"]
    ]
    for scene in timeline:
        scene["timeline_events"] = timeline_events
    log("Animating the full documentary timeline…")
    caption_path = None
    if captions:
        caption_path = write_srt(captions, job_dir / "captions.srt")
    picture = render_storyboard(
        timeline,
        total,
        job_dir / "picture.mp4",
        captions=captions,
        progress=log,
    )
    user_music = Path(music_path) if music_path else None
    music = make_music(total, job_dir / "music.m4a", user_music)
    final = mux_documentary_audio(picture, voice_track, job_dir / "final.mp4", music=music)

    meta = {
        "job_dir": str(job_dir),
        "final": str(final),
        "title": script["title"],
        "scenes": len(script["scenes"]),
        "duration_sec": total,
        "target_duration_sec": target_duration,
        "duration_warning": duration_warning,
        "captions": str(caption_path) if caption_path else None,
        "research": str(job_dir / "research.json"),
    }
    (job_dir / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log("Done.")
    return meta
