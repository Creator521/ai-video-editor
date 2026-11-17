from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image, ImageDraw, ImageFont

from editor.assemble import _ffprobe_duration, make_music
from editor.cinematic import (
    concatenate_audio,
    mux_documentary_audio,
    plan_scene_motion,
    render_storyboard,
    video_dimensions,
    write_srt,
)
from editor.images import generate_scene_image
from editor.jobs import create_job_dir
from editor.pipeline import run_pipeline
from editor.research import download_commons_image, image_credit, research_scene
from editor.style import VOICES
from editor.tts import synthesize_scene
from editor.transcribe import file_signature, transcribe_audio
from editor.voice_beats import make_voice_scene_plan, validate_voice_scene_ranges

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def generate(topic, minutes, language, voice, music, progress_tracker=gr.Progress()):
    topic = (topic or "").strip()
    if not topic:
        raise gr.Error("Pehle topic likho — jaise Maya civilization ya Ashoka.")

    logs: list[str] = []

    def progress(msg: str) -> None:
        logs.append(msg)
        progress_tracker(None, desc=msg)

    music_path = music.name if music else None
    result = run_pipeline(
        topic=topic,
        minutes=float(minutes),
        language=language,
        voice_label=voice,
        music_path=music_path,
        progress=progress,
    )
    script_path = Path(result["job_dir"]) / "script.json"
    script_text = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
    status = "\n".join(logs)
    return result["final"], status, script_text


def split_manual_script(script_text: str) -> list[dict[str, Any]]:
    text = (script_text or "").strip()
    if not text:
        raise gr.Error("Script khali hai. Pehle narration likho.")

    chunks = re.split(r"\n\s*\n|\n(?=\s*\d+\.?\s)", text)
    scenes: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        clean = " ".join(str(chunk).strip().split())
        if not clean:
            continue
        scenes.append(
            {
                "id": idx,
                "narration": clean,
                "research_query": clean[:120],
                "image_url": "",
            }
        )

    if not scenes:
        raise gr.Error("Script ko scenes me convert karne ke liye kam se kam ek valid narration line chahiye.")
    return scenes


def resolve_manual_image_mode(reviewed: dict[str, Any], selected_mode: str) -> str:
    """Use the current global selection unless a scene has an explicit override."""
    override = reviewed.get("image_mode_override")
    allowed = {"AI illustration", "Wikimedia photo"}
    return override if isinstance(override, str) and override in allowed else selected_mode


def manual_voice_entries(voice_files, recorded_voice, scene_count: int) -> list[str]:
    if isinstance(voice_files, (str, Path)):
        voice_files = [voice_files]
    additional = [str(path) for path in (voice_files or []) if str(path).strip()]
    if additional and not recorded_voice:
        raise ValueError(
            "Additional clips start at scene 2. Record or upload scene 1 first, then add these clips."
        )
    entries = [str(recorded_voice)] if recorded_voice else []
    entries.extend(additional)
    if len(entries) > scene_count:
        raise ValueError("Voice clips ki ginti scenes se zyada hai. Extra clips hata kar phir render karein.")
    return entries


def _ensure_placeholder_image(
    dest: Path,
    text: str,
    aspect_ratio: str = "16:9",
    visual_style: str = "Cinematic Documentary",
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = video_dimensions(aspect_ratio)
    paper_editorial = visual_style == "Paper Editorial"
    image = Image.new(
        "RGB",
        (width, height),
        color=(235, 224, 195) if paper_editorial else (28, 32, 26),
    )
    draw = ImageDraw.Draw(image)
    margin = round(min(width, height) * 0.08)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=max(16, round(margin * 0.35)),
        outline=(145, 109, 66) if paper_editorial else (220, 200, 150),
        width=max(3, round(margin * 0.05)),
    )
    font_size = max(32, round(min(width, height) * 0.045))
    font_path = next(
        (
            path
            for path in (
                Path("C:/Windows/Fonts/Nirmala.ttc"),
                Path("C:/Windows/Fonts/georgia.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
            )
            if path.exists()
        ),
        None,
    )
    font = ImageFont.truetype(str(font_path), font_size) if font_path else ImageFont.load_default()
    max_text_width = width - margin * 3
    lines: list[str] = []
    current = ""
    for word in str(text).split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_text_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 8:
        lines = lines[:7] + [lines[7][:30] + "…"]
    draw.text(
        (width // 2, height // 2),
        "\n".join(lines),
        fill=(45, 36, 27) if paper_editorial else (240, 228, 200),
        font=font,
        anchor="mm",
        align="center",
        spacing=max(6, font_size // 4),
    )
    if paper_editorial:
        label_font = ImageFont.truetype(str(font_path), max(20, font_size // 2)) if font_path else ImageFont.load_default()
        draw.text((margin + 14, margin + 12), "VISUAL BEAT", fill=(156, 93, 38), font=label_font)
    image.save(dest, "PNG")


def prepare_manual_scenes(
    script_text: str,
    language: str = "English",
    image_mode: str = "AI illustration",
) -> tuple[str, str]:
    scenes = split_manual_script(script_text)
    researched = []
    for scene in scenes:
        result = research_scene(scene["research_query"], language)
        researched.append({**scene, "research": result, "prepared_image_mode": image_mode})

    found = sum(bool(item["research"]["image_candidates"]) for item in researched)
    status = (
        f"Research ready for {len(researched)} scenes; Commons images found for {found}. "
        "Review article sources, selected image, and license before rendering."
    )
    return json.dumps(researched, ensure_ascii=False, indent=2), status


def render_manual_documentary(
    script_text: str,
    voice_files=None,
    recorded_voice=None,
    research_json: str = "",
    language: str = "English",
    voice_label: str = "English (US, documentary)",
    image_mode: str = "AI illustration",
    progress_tracker=gr.Progress(),
):
    scenes = split_manual_script(script_text)
    try:
        voice_entries = manual_voice_entries(voice_files, recorded_voice, len(scenes))
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc
    try:
        researched_scenes = json.loads(research_json) if research_json.strip() else []
        if not isinstance(researched_scenes, list):
            raise ValueError("Research data must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        raise gr.Error(f"Research JSON sahi nahi hai: {exc}") from exc

    logs: list[str] = []

    def progress(msg: str) -> None:
        logs.append(msg)
        progress_tracker(None, desc=msg)

    job_dir = create_job_dir(OUTPUTS)

    voice = VOICES.get(voice_label, "en-US-AndrewNeural")
    scene_payload: list[dict[str, Any]] = []
    voice_paths: list[Path] = []
    word_timings: dict[int, list[dict[str, Any]]] = {}
    timeline: list[dict[str, Any]] = []
    attribution_lines: list[str] = []
    research_output: list[dict[str, Any]] = []

    for idx, scene in enumerate(scenes, start=1):
        progress(f"Preparing scene {idx}/{len(scenes)}…")
        reviewed = researched_scenes[idx - 1] if idx - 1 < len(researched_scenes) else {}
        research_data = reviewed.get("research", {}) if isinstance(reviewed, dict) else {}
        research_query = str(reviewed.get("research_query", "")).strip() if isinstance(reviewed, dict) else ""
        if not isinstance(reviewed, dict) or reviewed.get("narration") != scene["narration"]:
            research_query = scene["narration"]
        elif not research_query:
            research_query = scene["narration"]
        if not isinstance(research_data, dict) or research_data.get("query") != research_query:
            research_data = research_scene(research_query, language)

        image_candidates = research_data.get("image_candidates", [])
        selected_index = reviewed.get("selected_image", research_data.get("selected_image", 0))
        try:
            selected_index = int(selected_index)
        except (TypeError, ValueError):
            selected_index = 0
        selected_image = (
            image_candidates[selected_index]
            if isinstance(image_candidates, list) and 0 <= selected_index < len(image_candidates)
            else None
        )
        image_dest = job_dir / "images" / f"scene_{idx:03d}.png"
        scene_image_mode = resolve_manual_image_mode(reviewed, image_mode)
        if scene_image_mode == "AI illustration":
            source_context = research_data.get("sources", [])
            source = source_context[0] if source_context else {}
            image_prompt = str(reviewed.get("image_prompt", "")).strip()
            if not image_prompt:
                image_prompt = (
                    f"Illustrate this documentary narration: {scene['narration']}. "
                    f"Historical context reference: {source.get('title', research_query)}. "
                    f"{str(source.get('extract', ''))[:350]}"
                )
            seed = int(hashlib.sha256(image_prompt.encode("utf-8")).hexdigest()[:8], 16)
            try:
                generate_scene_image(image_prompt, image_dest, seed)
                selected_image = None
                attribution_lines.append(f"Scene {idx}: AI-generated via Pollinations; prompt: {image_prompt}")
            except Exception as exc:
                _ensure_placeholder_image(image_dest, scene["narration"])
                selected_image = None
                progress(f"AI image generation failed for scene {idx}; using placeholder ({exc}).")
                image_prompt = ""
        else:
            image_prompt = ""
            if selected_image:
                try:
                    download_commons_image(selected_image, image_dest)
                except Exception as exc:
                    _ensure_placeholder_image(image_dest, scene["narration"])
                    selected_image = None
                    progress(f"Commons image download failed for scene {idx}; using placeholder ({exc}).")
            else:
                _ensure_placeholder_image(image_dest, scene["narration"])

        audio_dest = job_dir / "audio" / f"scene_{idx:03d}.mp3"
        if idx - 1 < len(voice_entries):
            source_audio = Path(voice_entries[idx - 1])
            if not source_audio.is_file():
                raise gr.Error(f"Scene {idx} ka voice clip nahi mila: {source_audio}")
            audio_dest = source_audio
        else:
            word_timings[idx] = synthesize_scene(scene["narration"], voice, audio_dest)

        voice_paths.append(audio_dest)
        scene_payload.append(
            {
                "id": idx,
                "narration": scene["narration"],
                "chapter": str(reviewed.get("chapter") or reviewed.get("card") or ""),
                "year": str(reviewed.get("year") or ""),
                "language": language,
                "research_query": research_query,
                "image_mode": scene_image_mode,
                "image_prompt": image_prompt,
                "image_path": str(image_dest),
                "voice_path": str(audio_dest),
                "image_source": selected_image,
                "image_attribution": (
                    image_credit(selected_image)
                    if selected_image
                    else "AI-generated via Pollinations" if scene_image_mode == "AI illustration" and image_prompt
                    else "Placeholder rendered; no image source selected."
                ),
                "research_sources": research_data.get("sources", []),
            }
        )
        if selected_image:
            attribution_lines.append(f"Scene {idx}: {image_credit(selected_image)}")
        research_output.append({**scene_payload[-1], "research_note": research_data.get("research_note", "")})

    voice_track = job_dir / "audio" / "narration.wav"
    total = concatenate_audio(voice_paths, voice_track)
    elapsed = 0.0
    captions: list[dict[str, Any]] = []
    for idx, (scene, audio_path) in enumerate(zip(scene_payload, voice_paths)):
        end = elapsed + _ffprobe_duration(audio_path)
        year = scene["year"]
        captions.extend(
            {
                "word": word["word"],
                "start": elapsed + float(word["start"]),
                "end": elapsed + float(word["end"]),
            }
            for word in word_timings.get(idx + 1, [])
        )
        timeline.append(
            {
                "start": elapsed,
                "end": end,
                "image": scene["image_path"],
                "narration": scene["narration"],
                "chapter": scene["chapter"],
                "year": year,
                "language": language,
                "has_word_captions": bool(word_timings.get(idx + 1)),
                "graphic_start": 0.0,
                "graphic_end": total,
                **plan_scene_motion(scene, idx),
            }
        )
        elapsed = end
    timeline_events = [
        {"label": scene["year"], "time": scene["start"]}
        for scene in timeline
        if scene["year"]
    ]
    for scene in timeline:
        scene["timeline_events"] = timeline_events
    timeline[-1]["end"] = total
    progress("Animating the full documentary timeline…")
    caption_path = None
    if captions:
        caption_path = write_srt(captions, job_dir / "captions.srt")
    picture = render_storyboard(
        timeline,
        total,
        job_dir / "picture.mp4",
        captions=captions,
        progress=progress,
    )
    music = make_music(total, job_dir / "music.m4a", None)
    final = mux_documentary_audio(picture, voice_track, job_dir / "final.mp4", music=music)
    (job_dir / "research.json").write_text(
        json.dumps(research_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (job_dir / "attribution.txt").write_text(
        "\n".join(attribution_lines) if attribution_lines else "No external image assets used.\n",
        encoding="utf-8",
    )

    meta = {
        "job_dir": str(job_dir),
        "final": str(final),
        "title": "Manual Documentary",
        "scenes": len(scene_payload),
        "duration_sec": total,
        "scenes_detail": scene_payload,
        "research": str(job_dir / "research.json"),
        "image_attribution": str(job_dir / "attribution.txt"),
        "captions": str(caption_path) if caption_path else None,
    }
    (job_dir / "job.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done.")
    return final, "\n".join(logs), json.dumps(meta, ensure_ascii=False, indent=2)


def prepare_voice_scene_plan(
    audio_path,
    topic: str = "",
    language: str = "English",
    beat_seconds: float = 5.0,
    progress_tracker=gr.Progress(),
):
    if not audio_path:
        raise gr.Error("Pehle apni full narration record ya upload karein.")
    audio_path = Path(str(audio_path))
    if not audio_path.is_file():
        raise gr.Error("Voice recording file nahi mili. Dobara upload/record karein.")

    def progress(message: str) -> None:
        progress_tracker(None, desc=message)

    progress("Transcribing voice locally with word timestamps…")
    try:
        transcript = transcribe_audio(audio_path, language, progress)
        duration = _ffprobe_duration(audio_path)
    except Exception as exc:  # noqa: BLE001
        raise gr.Error(f"Voice analysis fail hui: {exc}") from exc

    research: dict[str, Any] = {"sources": [], "errors": []}
    context = (topic or "").strip()
    if context:
        progress("Finding a short reference for the visual prompts…")
        try:
            research = research_scene(context, language)
        except Exception as exc:  # noqa: BLE001
            research["errors"].append(f"Research unavailable ({type(exc).__name__}).")
        for error in research.get("errors", []):
            progress(f"Research warning: {error}")

    sources = research.get("sources", [])
    excerpt = str(sources[0].get("extract", "")) if sources and isinstance(sources[0], dict) else ""
    try:
        scenes = make_voice_scene_plan(
            transcript["words"],
            duration,
            topic=context,
            max_seconds=float(beat_seconds),
            source_excerpt=excerpt,
        )
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc

    plan = {
        "audio_signature": file_signature(audio_path),
        "audio_duration_sec": duration,
        "language": language,
        "detected_language": transcript["language"],
        "topic": context,
        "transcript": transcript["text"],
        "words": transcript["words"],
        "research_sources": [
            {"title": source.get("title", ""), "url": source.get("url", "")}
            for source in sources
            if isinstance(source, dict)
        ],
        "visual_beat_seconds": float(beat_seconds),
        "scenes": scenes,
    }
    progress(f"Found {len(transcript['words'])} words and made {len(scenes)} visual beats.")
    return (
        json.dumps(plan, ensure_ascii=False, indent=2),
        f"Transcribed {len(transcript['words'])} words into {len(scenes)} visual beats. "
        "Review the scene prompts, then render.",
    )


def render_voice_documentary(
    audio_path,
    plan_json: str,
    language: str = "English",
    image_mode: str = "AI illustration",
    music=None,
    aspect_ratio: str = "9:16",
    visual_style: str = "Paper Editorial",
    progress_tracker=gr.Progress(),
):
    if not audio_path:
        raise gr.Error("Voice recording file nahi mili. Dobara upload/record karein.")
    audio_path = Path(str(audio_path))
    if not audio_path.is_file():
        raise gr.Error("Voice recording file nahi mili. Dobara upload/record karein.")
    try:
        plan = json.loads(plan_json)
        if not isinstance(plan, dict):
            raise ValueError("Voice scene plan must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise gr.Error(f"Voice scene plan JSON sahi nahi hai: {exc}") from exc
    if plan.get("audio_signature") != file_signature(audio_path):
        raise gr.Error("Voice recording badli hui hai. Pehle ‘Transcribe & plan visuals’ dobara chalayein.")
    words = plan.get("words")
    scenes = plan.get("scenes")
    if not isinstance(words, list) or not words or not isinstance(scenes, list) or not scenes:
        raise gr.Error("Plan mein timestamped words ya visual scenes nahi hain.")
    try:
        validate_voice_scene_ranges(scenes, float(plan.get("audio_duration_sec", 0.0)))
    except (KeyError, TypeError, ValueError) as exc:
        raise gr.Error(f"Voice scene timing sahi nahi hai: {exc}") from exc

    logs: list[str] = []

    def progress(message: str) -> None:
        logs.append(message)
        progress_tracker(None, desc=message)

    job_dir = create_job_dir(OUTPUTS)
    (job_dir / "voice_scene_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    transcript_data = {
        "text": plan.get("transcript", ""),
        "language": plan.get("detected_language", ""),
        "words": words,
    }
    (job_dir / "transcript.json").write_text(
        json.dumps(transcript_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    voice_track = job_dir / "audio" / "narration.wav"
    progress("Preparing the narration track…")
    total = concatenate_audio([audio_path], voice_track)
    source_duration = max(0.001, float(plan.get("audio_duration_sec", total)))
    time_scale = total / source_duration
    timed_words: list[dict[str, Any]] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        try:
            start = float(word["start"]) * time_scale
            end = float(word["end"]) * time_scale
        except (KeyError, TypeError, ValueError):
            continue
        text = str(word.get("word", "")).strip()
        if text and end > start:
            timed_words.append({"word": text, "start": start, "end": end})
    timed_words.sort(key=lambda item: item["start"])
    if not timed_words:
        raise gr.Error("Plan mein valid word timings nahi mile.")

    timeline: list[dict[str, Any]] = []
    scene_details: list[dict[str, Any]] = []
    attribution_lines: list[str] = []
    topic = str(plan.get("topic", "")).strip()
    aspect_ratio = aspect_ratio if aspect_ratio in {"9:16", "16:9"} else "9:16"
    visual_style = visual_style if visual_style in {"Paper Editorial", "Cinematic Documentary"} else "Paper Editorial"
    for index, source_scene in enumerate(scenes):
        if not isinstance(source_scene, dict):
            raise gr.Error(f"Scene {index + 1} plan JSON mein object nahi hai.")
        scene = dict(source_scene)
        try:
            planned_start = float(scene["start"])
            planned_end = float(scene["end"])
            scene["start"] = planned_start * time_scale
            scene["end"] = planned_end * time_scale
        except (KeyError, TypeError, ValueError) as exc:
            raise gr.Error(f"Scene {index + 1} ke start/end timestamps sahi nahi hain.") from exc
        scene["language"] = language
        scene["image_prompt"] = str(scene.get("image_prompt", "")).strip()
        scene_mode = resolve_manual_image_mode(scene, image_mode)
        image_path = job_dir / "images" / f"scene_{index + 1:03d}.png"
        progress(f"Preparing visual beat {index + 1}/{len(scenes)}…")
        selected_image = None
        image_prompt = scene["image_prompt"] or (
            f"Illustrate this spoken documentary phrase: {scene.get('narration', '')}. "
            f"Context: {topic}. Avoid captions and text."
        )

        if scene_mode == "Wikimedia photo":
            query = " ".join(part for part in (topic, str(scene.get("narration", ""))) if part)
            result = research_scene(query, language)
            candidates = result.get("image_candidates", [])
            choice = scene.get("selected_image", 0)
            try:
                choice = int(choice)
            except (TypeError, ValueError):
                choice = 0
            selected_image = candidates[choice] if isinstance(candidates, list) and 0 <= choice < len(candidates) else None
            if selected_image:
                try:
                    download_commons_image(selected_image, image_path)
                    attribution = image_credit(selected_image)
                    attribution_lines.append(f"Beat {index + 1}: {attribution}")
                except Exception as exc:  # noqa: BLE001
                    progress(f"Commons image failed for beat {index + 1}; generating a matching illustration ({exc}).")
                    selected_image = None
            if not selected_image:
                progress(f"No usable Commons image for beat {index + 1}; generating a matching illustration.")
                seed = int(hashlib.sha256(image_prompt.encode("utf-8")).hexdigest()[:8], 16)
                try:
                    generate_scene_image(
                        image_prompt,
                        image_path,
                        seed,
                        aspect_ratio=aspect_ratio,
                        visual_style=visual_style,
                    )
                    attribution = "Automatically generated via Pollinations after no usable Commons photo was found."
                    attribution_lines.append(f"Beat {index + 1}: {attribution}; prompt: {image_prompt}")
                except Exception as exc:  # noqa: BLE001
                    _ensure_placeholder_image(
                        image_path,
                        str(scene.get("narration", "")),
                        aspect_ratio,
                        visual_style,
                    )
                    progress(f"Image generation failed for beat {index + 1}; using a designed placeholder ({exc}).")
                    attribution = "Placeholder rendered after Commons search and image generation failed."
        else:
            seed = int(hashlib.sha256(image_prompt.encode("utf-8")).hexdigest()[:8], 16)
            try:
                generate_scene_image(
                    image_prompt,
                    image_path,
                    seed,
                    aspect_ratio=aspect_ratio,
                    visual_style=visual_style,
                )
                attribution = "AI-generated via Pollinations"
                attribution_lines.append(f"Beat {index + 1}: {attribution}; prompt: {image_prompt}")
            except Exception as exc:  # noqa: BLE001
                _ensure_placeholder_image(
                    image_path,
                    str(scene.get("narration", "")),
                    aspect_ratio,
                    visual_style,
                )
                progress(f"Image generation failed for beat {index + 1}; using placeholder ({exc}).")
                attribution = "Placeholder rendered after image generation failed."

        scene["image"] = str(image_path)
        visual_plan = plan_scene_motion(scene, index)
        timeline.append(
            {
                "start": scene["start"],
                "end": scene["end"],
                "image": str(image_path),
                "narration": str(scene.get("narration", "")),
                "chapter": str(scene.get("chapter", "")),
                "year": str(scene.get("year", "")),
                "aspect_ratio": aspect_ratio,
                "visual_style": visual_style,
                "language": language,
                "has_word_captions": True,
                "graphic_start": 0.0,
                "graphic_end": total,
                **visual_plan,
            }
        )
        scene_details.append(
            {
                **scene,
                "start": planned_start,
                "end": planned_end,
                "rendered_start": scene["start"],
                "rendered_end": scene["end"],
                "image_mode": scene_mode,
                "image_attribution": attribution,
                "image_source": selected_image,
                **visual_plan,
            }
        )

    timeline.sort(key=lambda item: float(item["start"]))
    timeline[0]["start"] = 0.0
    timeline[-1]["end"] = total
    for item in timeline:
        item["timeline_events"] = [
            {"label": scene["year"], "time": scene["start"]}
            for scene in timeline
            if scene["year"]
        ]
    captions_path = write_srt(timed_words, job_dir / "captions.srt")
    picture = render_storyboard(
        timeline,
        total,
        job_dir / "picture.mp4",
        captions=timed_words,
        progress=progress,
        aspect_ratio=aspect_ratio,
        visual_style=visual_style,
    )
    user_music = Path(music.name if hasattr(music, "name") else music) if music else None
    music_path = make_music(total, job_dir / "music.m4a", user_music)
    final = mux_documentary_audio(picture, voice_track, job_dir / "final.mp4", music=music_path)
    (job_dir / "attribution.txt").write_text(
        "\n".join(attribution_lines) if attribution_lines else "No external image assets used.\n",
        encoding="utf-8",
    )
    plan["scenes"] = scene_details
    plan["captions"] = str(captions_path)
    plan["aspect_ratio"] = aspect_ratio
    plan["visual_style"] = visual_style
    plan["final"] = str(final)
    plan["job_dir"] = str(job_dir)
    (job_dir / "voice_scene_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta = {
        "job_dir": str(job_dir),
        "final": str(final),
        "duration_sec": total,
        "aspect_ratio": aspect_ratio,
        "visual_style": visual_style,
        "words": len(timed_words),
        "visual_beats": len(scene_details),
        "captions": str(captions_path),
        "transcript": str(job_dir / "transcript.json"),
        "scene_plan": str(job_dir / "voice_scene_plan.json"),
        "image_attribution": str(job_dir / "attribution.txt"),
    }
    (job_dir / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    progress("Voice-led documentary complete.")
    return final, "\n".join(logs), json.dumps(plan, ensure_ascii=False, indent=2)


with gr.Blocks(title="Beyond-style Documentary Editor") as demo:
    gr.Markdown(
        """
# Illustrated Documentary AI
**Narration-led cinematic documentary:** moving camera, animated chapter graphics, visual timelines, captions, and documentary voiceover.

Topic do ya Manual Studio mein apna scene-wise voice upload karo. Editor animated visuals aur `final.mp4` render karega.
        """
    )

    with gr.Tab("AI Documentary"):
        with gr.Row():
            with gr.Column(scale=2):
                topic = gr.Textbox(
                    label="Topic",
                    placeholder="The entire history of the Indus Valley in 8 minutes",
                    lines=2,
                )
                minutes = gr.Slider(0.5, 8.0, value=1.0, step=0.5, label="Approx. target length (minutes)")
                language = gr.Radio(["English", "Hindi"], value="English", label="Narration language")
                voice = gr.Dropdown(list(VOICES.keys()), value="English (US, documentary)", label="Voice")
                music = gr.File(label="Optional background music (mp3/wav)", file_types=[".mp3", ".wav", ".m4a"])
                btn = gr.Button("Edit documentary", variant="primary")
            with gr.Column(scale=3):
                video = gr.Video(label="Final cut")
                status = gr.Textbox(label="Editor log", lines=10)
                script = gr.Code(label="script.json", language="json")

        btn.click(generate, [topic, minutes, language, voice, music], [video, status, script])

    with gr.Tab("Manual Studio"):
        gr.Markdown(
            """
### Script + Voice + Research-based image workflow
- Script likho, scene-wise voice record/upload karo, phir sourced images review karke render karo.
- **AI illustration** Pollinations se scene prompt ke basis par still image banata hai; **Wikimedia photo** Commons search se image leta hai.
- Commons ke liye JSON mein `selected_image` candidate number set karein (pehla candidate `0` hai); AI art ke liye `image_prompt` edit karein.
- Extra voice clips scene 2 se lagte hain, isliye unhe add karne se pehle scene 1 ki recording/upload zaroor dein.
- Wikipedia results research references hain, independent fact-check nahi.
            """
        )
        with gr.Row():
            with gr.Column(scale=2):
                manual_script = gr.Textbox(
                    label="Narration script",
                    placeholder="Write one scene per line or paragraph.\nExample:\nThe city rose along the river.\nPeople built canals and temples.\nTrade connected distant kingdoms.",
                    lines=12,
                )
                manual_language = gr.Radio(["English", "Hindi"], value="English", label="Research language")
                manual_image_mode = gr.Radio(
                    ["AI illustration", "Wikimedia photo"],
                    value="AI illustration",
                    label="Scene visuals",
                )
                recorded_voice = gr.Audio(
                    sources=["microphone", "upload"],
                    type="filepath",
                    label="Record or upload voice clip for scene 1",
                )
                manual_voice_files = gr.Files(
                    label="Additional voice clips (scene 2 onward, in order)",
                    file_count="multiple",
                    file_types=["audio"],
                )
                prepare_btn = gr.Button("Prepare scenes & research images")
                manual_voice = gr.Dropdown(
                    list(VOICES.keys()), value="English (US, documentary)", label="Fallback TTS voice"
                )
                render_btn = gr.Button("Render final documentary", variant="primary")
            with gr.Column(scale=3):
                scene_output = gr.Code(
                    label="Reviewed research and image choices (editable JSON)",
                    language="json",
                    interactive=True,
                    lines=20,
                )
                manual_status = gr.Textbox(label="Research and render log", lines=3)
                final_video = gr.Video(label="Manual final cut")

        prepare_btn.click(
            prepare_manual_scenes,
            [manual_script, manual_language, manual_image_mode],
            [scene_output, manual_status],
        )
        render_btn.click(
            render_manual_documentary,
            [
                manual_script,
                manual_voice_files,
                recorded_voice,
                scene_output,
                manual_language,
                manual_voice,
                manual_image_mode,
            ],
            [final_video, manual_status, scene_output],
        )

    with gr.Tab("Voice-led visuals"):
        gr.Markdown(
            """
### Voice recording se scene-wise visuals
Full narration record/upload karein. Local Whisper har word ka timestamp nikaalega; captions bolte hue word ko highlight karenge aur visuals har 2.5–8 second ke narration beat par badlenge. **Paper Editorial** adds a parchment collage, a recurring illustrated storyteller, layered image cards and a camera move that flows across beat changes. Shorts ke liye 9:16 ya regular YouTube ke liye 16:9 chunein.
Wikimedia photo mode mein suitable image na mile to app matching illustration generate karne ki koshish karega. Attribution file ko publish karne se pehle review karein.
            """
        )
        with gr.Row():
            with gr.Column(scale=2):
                voice_recording = gr.Audio(
                    sources=["microphone", "upload"],
                    type="filepath",
                    label="Full narration recording",
                )
                voice_topic = gr.Textbox(
                    label="Optional topic/context",
                    placeholder="e.g. Ashoka and the Mauryan Empire",
                )
                voice_language = gr.Radio(
                    ["English", "Hindi"], value="English", label="Recording language"
                )
                voice_aspect_ratio = gr.Radio(
                    ["9:16", "16:9"],
                    value="9:16",
                    label="YouTube format",
                    info="9:16 vertical Shorts · 16:9 landscape video",
                )
                voice_visual_style = gr.Radio(
                    ["Paper Editorial", "Cinematic Documentary"],
                    value="Paper Editorial",
                    label="Visual style",
                )
                voice_beat_seconds = gr.Slider(
                    2.5,
                    8.0,
                    value=3.5,
                    step=0.5,
                    label="Approx. seconds per visual beat",
                )
                voice_image_mode = gr.Radio(
                    ["AI illustration", "Wikimedia photo"],
                    value="AI illustration",
                    label="Visual source",
                )
                voice_music = gr.File(
                    label="Optional background music (mp3/wav)",
                    file_types=[".mp3", ".wav", ".m4a"],
                )
                plan_voice_btn = gr.Button("Transcribe & plan visuals")
                render_voice_btn = gr.Button("Render voice-led video", variant="primary")
            with gr.Column(scale=3):
                voice_plan = gr.Code(
                    label="Word timings and visual beats (editable JSON)",
                    language="json",
                    interactive=True,
                    lines=20,
                )
                voice_status = gr.Textbox(label="Voice-led render status", lines=5)
                voice_video = gr.Video(label="Voice-led final cut")

        plan_voice_btn.click(
            prepare_voice_scene_plan,
            [voice_recording, voice_topic, voice_language, voice_beat_seconds],
            [voice_plan, voice_status],
        )
        render_voice_btn.click(
            render_voice_documentary,
            [
                voice_recording,
                voice_plan,
                voice_language,
                voice_image_mode,
                voice_music,
                voice_aspect_ratio,
                voice_visual_style,
            ],
            [voice_video, voice_status, voice_plan],
        )

if __name__ == "__main__":
    demo.launch(inbrowser=True, server_name="127.0.0.1", theme="soft")
