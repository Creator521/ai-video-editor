from __future__ import annotations

from typing import Any


def group_words_into_beats(
    words: list[dict[str, Any]],
    max_seconds: float = 5.0,
    max_words: int = 14,
) -> list[dict[str, Any]]:
    """Group transcript words into short visual beats without losing word timing."""
    if max_seconds <= 0 or max_words <= 0:
        raise ValueError("Beat duration and word limit must be positive.")

    ordered = sorted(words, key=lambda item: float(item["start"]))
    beats: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def finish() -> None:
        if not current:
            return
        beats.append(
            {
                "start": float(current[0]["start"]),
                "end": float(current[-1]["end"]),
                "narration": " ".join(str(item["word"]).strip() for item in current),
                "words": current.copy(),
            }
        )
        current.clear()

    for item in ordered:
        word = str(item.get("word", "")).strip()
        start, end = float(item["start"]), float(item["end"])
        if not word or end <= start:
            continue
        if current:
            gap = start - float(current[-1]["end"])
            duration_with_word = end - float(current[0]["start"])
            last_word = str(current[-1]["word"]).strip()
            sentence_end = last_word.endswith((".", "!", "?", "।"))
            split = (
                gap >= 0.65
                or duration_with_word > max_seconds
                or len(current) >= max_words
                or (sentence_end and float(current[-1]["end"]) - float(current[0]["start"]) >= 1.5)
            )
            if split:
                finish()
        current.append({"word": word, "start": start, "end": end})
    finish()

    # Very short tails look better as part of an adjacent visual beat.
    merged: list[dict[str, Any]] = []
    for beat in beats:
        if merged and beat["end"] - beat["start"] < 1.2:
            previous = merged[-1]
            combined_duration = beat["end"] - previous["start"]
            if beat["start"] - previous["end"] <= 0.8 and combined_duration <= max_seconds * 1.5:
                previous["end"] = beat["end"]
                previous["narration"] = f"{previous['narration']} {beat['narration']}"
                previous["words"].extend(beat["words"])
                continue
        merged.append(beat)
    return merged


def make_voice_scene_plan(
    words: list[dict[str, Any]],
    duration: float,
    topic: str = "",
    max_seconds: float = 5.0,
    source_excerpt: str = "",
) -> list[dict[str, Any]]:
    if duration <= 0:
        raise ValueError("The voice recording has no duration.")
    beats = group_words_into_beats(words, max_seconds=max_seconds)
    if not beats:
        raise ValueError("No timestamped speech beats were detected.")

    boundaries = [0.0]
    for previous, current in zip(beats, beats[1:]):
        boundaries.append((float(previous["end"]) + float(current["start"])) / 2)
    boundaries.append(float(duration))

    scenes = []
    for index, beat in enumerate(beats):
        start = max(0.0, min(float(duration), boundaries[index]))
        end = max(start, min(float(duration), boundaries[index + 1]))
        if end <= start:
            continue
        context = f" Documentary context: {topic.strip()}." if topic.strip() else ""
        source_note = f" Reference note: {source_excerpt[:350]}" if source_excerpt else ""
        scenes.append(
            {
                "id": len(scenes) + 1,
                "start": start,
                "end": end,
                "narration": beat["narration"],
                "image_prompt": (
                    "Create one historically careful illustrated documentary frame for this spoken phrase: "
                    f"{beat['narration']}.{context}{source_note} "
                    "Show the described visual idea, avoid captions and text."
                ),
                "word_count": len(beat["words"]),
                "year": "",
                "chapter": "",
            }
        )
    if not scenes:
        raise ValueError("Could not create any visual beats from the recording.")
    scenes[0]["start"] = 0.0
    scenes[-1]["end"] = float(duration)
    return scenes


def validate_voice_scene_ranges(
    scenes: list[dict[str, Any]],
    duration: float,
    fps: int = 30,
) -> None:
    if not scenes or duration <= 0 or fps <= 0:
        raise ValueError("The voice plan needs scenes and a positive audio duration.")
    if any(not isinstance(scene, dict) for scene in scenes):
        raise ValueError("Every visual beat must be a JSON object.")
    ordered = sorted(scenes, key=lambda item: float(item["start"]))
    expected_start = 0
    for index, scene in enumerate(ordered, start=1):
        start = round(float(scene["start"]) * fps)
        end = round(float(scene["end"]) * fps)
        if end <= start:
            raise ValueError(f"Visual beat {index} has no renderable duration.")
        if start != expected_start:
            raise ValueError(f"Visual beat {index} leaves a gap or overlap in the timeline.")
        expected_start = end
    if expected_start != round(duration * fps):
        raise ValueError("Visual beats do not cover the full voice recording.")
