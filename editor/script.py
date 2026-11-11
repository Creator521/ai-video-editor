from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from editor.llm import chat_json
from editor.style import STYLE_BIBLE

Progress = Callable[[str], None]


def build_script(
    topic: str,
    minutes: float,
    language: str,
    job_dir: Path,
    progress: Progress | None = None,
    max_scenes: int | None = None,
) -> dict[str, Any]:
    words = int(minutes * 145)
    scenes_target = max(6, int(minutes * 10))
    system = (
        "You write illustrated YouTube history documentaries in the Beyond History style. "
        "Hook in the first 8 seconds. One visual idea per scene. Short spoken sentences. "
        "Return JSON only."
    )
    user = f"""
Write a {minutes:.1f}-minute illustrated documentary about: {topic}
Language of narration: {language}
Target spoken words: about {words}
Target scenes: about {scenes_target} (each 1-2 sentences, 4-8 seconds when spoken)

Visual style to describe in every image_prompt:
{STYLE_BIBLE}

JSON schema:
{{
  "title": "short documentary title",
  "subtitle": "one-line hook",
  "scenes": [
    {{
      "narration": "spoken line",
      "year": "optional date like 1839 or blank",
      "card": "optional on-screen label, else blank",
      "image_prompt": "full English illustration prompt matching the style bible"
    }}
  ]
}}

Rules:
- First scene is a hook, not a Wikipedia intro.
- Alternate wide establishing shots and closer character/object shots.
- Include at least one antique map/year-card scene if the story has dates.
- image_prompt must be English even if narration is Hindi.
- No citations, no hashtags.
"""
    if progress:
        progress("Writing documentary script…")
    try:
        data = chat_json(system, user)
    except Exception:
        if progress:
            progress("No LLM key found — using built-in script template.")
        data = fallback_script(topic, language)

    scenes = data.get("scenes") or []
    cleaned = []
    for i, scene in enumerate(scenes, start=1):
        narration = str(scene.get("narration", "")).strip()
        if not narration:
            continue
        prompt = str(scene.get("image_prompt", "")).strip()
        if not prompt:
            prompt = f"Educational cartoon illustration of: {narration}"
        cleaned.append(
            {
                "id": i,
                "narration": narration,
                "year": str(scene.get("year") or "").strip(),
                "card": str(scene.get("card") or "").strip(),
                "image_prompt": prompt,
            }
        )
    if not cleaned:
        data = fallback_script(topic, language)
        cleaned = data["scenes"]
    cap = max_scenes if max_scenes else max(4, int(minutes * 9))
    cleaned = cleaned[:cap]

    out = {
        "title": str(data.get("title") or topic).strip(),
        "subtitle": str(data.get("subtitle") or "").strip(),
        "language": language,
        "topic": topic,
        "scenes": cleaned,
    }
    (job_dir / "script.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def fallback_script(topic: str, language: str) -> dict[str, Any]:
    if language.lower().startswith("hindi"):
        lines = [
            f"{topic} ki kahani ek sawal se shuru hoti hai — ye log the kaun, aur unka sansar kaise bana?",
            "Jungle, nadiyan aur pathar ke shahar — yahi unki duniya ka pehla naksha tha.",
            "Raja, purohit aur kisan ek hi calendar ke neeche jeete the.",
            "Unhone aasmaan ko padha, faslein gin, aur itihas ko patthar par likha.",
            "Phir shehar so gaye. Jungle wapas aa gaya. Lekin nishaan ab bhi khade hain.",
            "Aaj hum un nishaano ko padhkar wahi duniya dobara dekhte hain.",
        ]
    else:
        lines = [
            f"The story of {topic} does not begin with a date. It begins with a question.",
            "Who built these cities in the forest, and why did the jungle take them back?",
            "Kings, farmers, and priests lived inside one shared calendar of sky and stone.",
            "They wrote history in glyphs, and they measured time more carefully than most empires.",
            "Then the great centers went quiet. The forest returned. The monuments stayed.",
            "Today we read those stones again — and the civilization still answers.",
        ]
    scenes = []
    visuals = [
        "wide jungle village with thatched huts, people farming, pyramids far in the mist",
        "explorers with notebooks standing before a mossy limestone pyramid",
        "a king in jade and feathers standing beside a carved stela and incense",
        "priests studying a night sky over a temple courtyard, fireflies, moon",
        "empty overgrown temples reclaimed by vines at dusk",
        "a modern scholar clapping at the base of a pyramid while a quetzal watches",
    ]
    for i, (line, visual) in enumerate(zip(lines, visuals), start=1):
        scenes.append(
            {
                "id": i,
                "narration": line,
                "year": "",
                "card": "",
                "image_prompt": f"{visual}. Subject: {topic}.",
            }
        )
    return {
        "title": topic.title(),
        "subtitle": "An illustrated history",
        "scenes": scenes,
    }
