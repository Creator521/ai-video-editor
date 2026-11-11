from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import edge_tts
import gradio as gr
from PIL import Image, ImageDraw, ImageFont

from editor.assemble import _ffprobe_duration, _run, concat_and_mix, make_music, render_shot
from editor.images import generate_scene_image
from editor.pipeline import run_pipeline
from editor.research import download_commons_image, image_credit, research_scene
from editor.style import VOICES

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def generate(topic, minutes, language, voice, music):
    topic = (topic or "").strip()
    if not topic:
        raise gr.Error("Pehle topic likho — jaise Maya civilization ya Ashoka.")

    logs: list[str] = []

    def progress(msg: str) -> None:
        logs.append(msg)

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

    chunks = re.split(r"\n\s*\n|\n(?=\s*\d+\.?\s)|(?<=[.!?])\s+", text)
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


def _ensure_placeholder_image(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), color=(28, 32, 26))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 80, width - 80, height - 80), radius=28, outline=(220, 200, 150), width=4)
    font_path = Path("C:/Windows/Fonts/georgia.ttf")
    font = ImageFont.truetype(str(font_path), 54) if font_path.exists() else ImageFont.load_default()
    wrap = text[:90]
    draw.text((width // 2, height // 2), wrap, fill=(240, 228, 200), font=font, anchor="mm")
    image.save(dest, "PNG")


async def _speak_scene(text: str, voice: str, dest: Path) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate="-8%")
    await communicate.save(str(dest))


def prepare_manual_scenes(
    script_text: str,
    language: str = "English",
    image_mode: str = "AI illustration",
) -> tuple[str, str]:
    scenes = split_manual_script(script_text)
    researched = []
    for scene in scenes:
        result = research_scene(scene["research_query"], language)
        researched.append({**scene, "research": result, "image_mode": image_mode})

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
):
    scenes = split_manual_script(script_text)
    voice_entries = []
    if recorded_voice:
        voice_entries.append(str(recorded_voice))
    if voice_files:
        voice_entries = [str(p) for p in list(voice_files) if str(p).strip()]
        if recorded_voice:
            voice_entries.insert(0, str(recorded_voice))
    try:
        researched_scenes = json.loads(research_json) if research_json.strip() else []
        if not isinstance(researched_scenes, list):
            raise ValueError("Research data must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        raise gr.Error(f"Research JSON sahi nahi hai: {exc}") from exc

    logs: list[str] = []

    def progress(msg: str) -> None:
        logs.append(msg)

    OUTPUTS.mkdir(exist_ok=True)
    job_dir = OUTPUTS / datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "shots").mkdir(exist_ok=True)
    (job_dir / "audio").mkdir(exist_ok=True)
    (job_dir / "images").mkdir(exist_ok=True)

    voice = VOICES.get(voice_label, "en-US-AndrewNeural")
    scene_payload: list[dict[str, Any]] = []
    shots: list[Path] = []
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
        scene_image_mode = reviewed.get("image_mode", image_mode)
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
            if source_audio.exists():
                audio_dest = source_audio
        else:
            asyncio.run(_speak_scene(scene["narration"], voice, audio_dest))

        shot_dest = job_dir / "shots" / f"shot_{idx:03d}.mp4"
        render_shot(image_dest, audio_dest, shot_dest, "in" if idx % 2 == 1 else "out")
        shots.append(shot_dest)
        scene_payload.append(
            {
                "id": idx,
                "narration": scene["narration"],
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

    total = sum(_ffprobe_duration(p) for p in shots)
    music = make_music(total, job_dir / "music.m4a", None)
    final = concat_and_mix(shots, music, job_dir / "final.mp4", progress)
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
    }
    (job_dir / "job.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done.")
    return final, "\n".join(logs), json.dumps(meta, ensure_ascii=False, indent=2)


with gr.Blocks(title="Beyond-style Documentary Editor", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
# Illustrated Documentary AI
Reference video ke style mein: **cartoon history frames, slow Ken Burns, documentary voiceover**.

Topic do. Agent script likhega, illustrations banayega, voice record karega, aur `final.mp4` cut karega.
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
                minutes = gr.Slider(0.5, 8.0, value=1.0, step=0.5, label="Target length (minutes)")
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

if __name__ == "__main__":
    demo.launch(inbrowser=True, server_name="127.0.0.1")
