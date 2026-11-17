from __future__ import annotations

import json
import math
import random
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = 1920
HEIGHT = 1080
FPS = 30
TRANSITION_SECONDS = 0.40

Progress = Callable[[str], None]

_MOVES = ("zoom_in_safe", "pan_horizontal", "zoom_out_reveal", "tilt_down", "zoom_to_face")
_TRANSITIONS = {"cut", "dissolve", "wipe", "slide", "flash", "dip"}


def video_dimensions(aspect_ratio: str = "16:9") -> tuple[int, int]:
    return (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) for keyword in keywords)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ("C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/arialbd.ttf")
        if bold
        else ("C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/arial.ttf")
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def validate_timeline(scenes: list[dict[str, Any]], duration: float, fps: int = FPS) -> None:
    if not scenes:
        raise ValueError("A documentary needs at least one scene.")
    if duration <= 0 or fps <= 0:
        raise ValueError("Duration and frame rate must be positive.")

    ordered = sorted(scenes, key=lambda scene: float(scene["start"]))
    expected_start = 0
    for index, scene in enumerate(ordered, start=1):
        start = round(float(scene["start"]) * fps)
        end = round(float(scene["end"]) * fps)
        if end <= start:
            raise ValueError(f"Scene {index} has no renderable duration.")
        if start != expected_start:
            raise ValueError(f"Scene {index} leaves a gap or overlap in the timeline.")
        if not Path(scene["image"]).is_file():
            raise FileNotFoundError(f"Scene {index} image not found: {scene['image']}")
        expected_start = end

    if expected_start != round(duration * fps):
        raise ValueError("Scene timeline does not cover the requested video duration.")


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def camera_frame(image: Image.Image, move: str, progress: float) -> Image.Image:
    width, height = image.size
    progress = _ease(progress)
    max_zoom = 1.0 + (0.10 if move == "zoom_to_face" else 0.08)
    if move in ("zoom_out_reveal", "pull"):
        zoom = max_zoom - (max_zoom - 1.025) * progress
    elif move in ("pan_horizontal", "pan_left", "pan_right", "tilt_down", "tilt_up"):
        zoom = 1.075
    else:
        zoom = 1.025 + (max_zoom - 1.025) * progress

    crop_width = width / zoom
    crop_height = height / zoom
    max_x = width - crop_width
    max_y = height - crop_height
    if move == "pan_left":
        x0 = max_x * (1.0 - progress)
    elif move in ("pan_horizontal", "pan_right"):
        x0 = max_x * progress
    else:
        x0 = max_x * (0.35 + 0.20 * math.sin(progress * math.pi))

    if move == "tilt_up":
        y0 = max_y * (1.0 - progress)
    elif move == "tilt_down":
        y0 = max_y * progress
    else:
        y0 = max_y * 0.25

    box = (
        max(0.0, x0),
        max(0.0, y0),
        min(float(width), x0 + crop_width),
        min(float(height), y0 + crop_height),
    )
    return image.transform(
        (width, height),
        Image.Transform.EXTENT,
        box,
        resample=Image.Resampling.BICUBIC,
    )


def group_caption_words(words: Iterable[dict[str, Any]], max_words: int = 5) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def finish() -> None:
        if current:
            groups.append(
                {
                    "start": float(current[0]["start"]),
                    "end": float(current[-1]["end"]),
                    "words": current.copy(),
                }
            )
            current.clear()

    for item in words:
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        if current and float(item["start"]) - float(current[-1]["end"]) > 0.8:
            finish()
        current.append(
            {
                "word": word,
                "start": float(item["start"]),
                "end": float(item["end"]),
            }
        )
        if len(current) >= max_words or word.endswith((".", "!", "?", "।")):
            finish()
    finish()

    readable_groups: list[dict[str, Any]] = []
    for group in groups:
        if (
            readable_groups
            and group["end"] - group["start"] < 0.75
            and group["start"] - readable_groups[-1]["end"] <= 0.4
        ):
            previous = readable_groups[-1]
            previous["words"].extend(group["words"])
            previous["end"] = group["end"]
        else:
            readable_groups.append(group)
    if (
        len(readable_groups) > 1
        and readable_groups[0]["end"] - readable_groups[0]["start"] < 0.75
        and readable_groups[1]["start"] - readable_groups[0]["end"] <= 0.4
    ):
        first = readable_groups.pop(0)
        following = readable_groups[0]
        following["words"] = first["words"] + following["words"]
        following["start"] = first["start"]
    return readable_groups


def write_srt(words: Iterable[dict[str, Any]], destination: Path) -> Path:
    groups = group_caption_words(words)

    def stamp(seconds: float) -> str:
        milliseconds = max(0, round(seconds * 1000))
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"

    lines: list[str] = []
    for index, group in enumerate(groups, start=1):
        text = " ".join(item["word"] for item in group["words"])
        lines.extend(
            (
                str(index),
                f"{stamp(group['start'])} --> {stamp(group['end'])}",
                text,
                "",
            )
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _load_frame(path: Path, size: tuple[int, int] = (WIDTH, HEIGHT)) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.fit(
            source.convert("RGB"),
            size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.45),
        )


def _effect_name(scene: dict[str, Any]) -> str:
    explicit = str(scene.get("effect", "")).strip().lower()
    aliases = {
        "battle": "embers",
        "fire": "embers",
        "river": "water",
        "route": "map",
        "journey": "map",
        "off": "none",
    }
    if explicit in aliases:
        return aliases[explicit]
    if explicit in {"embers", "water", "map", "dust", "none"}:
        return explicit

    text = " ".join(
        str(scene.get(key, ""))
        for key in ("narration", "chapter", "title", "card", "image_prompt", "image")
    ).lower()
    if _has_keyword(text, ("battle", "siege", "war", "fire", "flame", "yudh", "ladai", "agni")):
        return "embers"
    if _has_keyword(text, ("map", "route", "journey", "travel", "migration", "march", "safar", "yatra", "raasta")):
        return "map"
    if _has_keyword(text, ("river", "barge", "water", "ocean", "sea", "ship", "boat", "nadi", "samundar", "jal")):
        return "water"
    return "dust"


def plan_scene_motion(scene: dict[str, Any], index: int) -> dict[str, str]:
    """Choose restrained, story-aware camera, graphic, and transition cues."""
    effect = _effect_name(scene)
    text = " ".join(
        str(scene.get(key, ""))
        for key in ("narration", "chapter", "title", "card", "image_prompt")
    ).lower()

    move = str(scene.get("move", "")).strip().lower()
    if move not in _MOVES:
        if effect in {"map", "water"}:
            move = "pan_horizontal"
        elif effect == "embers":
            move = "zoom_in_safe"
        elif any(token in text for token in ("portrait", "king", "queen", "person", "face")):
            move = "zoom_to_face"
        else:
            move = _MOVES[index % len(_MOVES)]

    if str(scene.get("year", "")).strip():
        graphic = "timeline"
    elif effect == "map":
        graphic = "route"
    elif effect == "embers":
        graphic = "impact"
    else:
        graphic = ""
    requested_graphic = str(scene.get("graphic", "")).strip().lower()
    if requested_graphic in {"timeline", "lineage", "route", "impact"}:
        graphic = requested_graphic

    transition = str(scene.get("transition", "")).strip().lower()
    if transition not in _TRANSITIONS:
        if effect == "map":
            transition = "wipe"
        elif effect == "embers" and index % 2 == 1:
            transition = "flash"
        elif str(scene.get("year", "")).strip() or index % 3 == 2:
            transition = "dissolve"
        else:
            transition = "cut"

    return {
        "move": move,
        "effect": effect,
        "graphic": graphic,
        "transition": transition,
    }


def _draw_particles(frame: Image.Image, effect: str, scene_id: int, local_time: float) -> Image.Image:
    if effect in ("none", "off"):
        return frame

    width, height = frame.size
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(scene_id * 7919)
    count = 22 if effect == "embers" else 16
    for particle in range(count):
        x0 = rng.uniform(0, width)
        y0 = rng.uniform(height * 0.20, height)
        speed = rng.uniform(16, 52)
        x = (x0 + math.sin(local_time * 0.7 + particle) * 28) % width
        y = (y0 - local_time * speed) % height
        radius = rng.uniform(1.5, 3.5) if effect == "embers" else rng.uniform(1.2, 2.7)
        pulse = 0.62 + 0.38 * math.sin(local_time * 2.0 + particle * 1.7)
        alpha = int((155 if effect == "embers" else 92) * pulse)
        color = (255, 158, 62, alpha) if effect == "embers" else (255, 239, 207, alpha)
        draw.ellipse((x, y, x + radius * 2, y + radius * 2), fill=color)

    if effect == "water":
        for line in range(5):
            y = int(height * (0.67 + 0.055 * line) + math.sin(local_time * 1.2 + line) * 5)
            x = int((local_time * (42 + line * 5) + line * 197) % width)
            draw.line((x, y, min(width, x + 150), y), fill=(255, 225, 160, 38), width=2)

    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_transition(
    current: Image.Image,
    previous: Image.Image,
    progress: float,
    transition: str = "wipe",
) -> Image.Image:
    width, height = current.size
    progress = _ease(progress)
    if transition == "cut":
        return current
    if transition == "dissolve":
        return Image.blend(previous, current, progress)
    if transition == "slide":
        offset = round(width * (1.0 - progress))
        frame = previous.copy()
        if offset < width:
            frame.paste(current.crop((0, 0, width - offset, height)), (offset, 0))
        return frame
    if transition == "dip":
        black = Image.new("RGB", current.size, (0, 0, 0))
        if progress < 0.5:
            return Image.blend(previous, black, progress * 2.0)
        return Image.blend(black, current, (progress - 0.5) * 2.0)
    if transition == "flash":
        blended = Image.blend(previous, current, progress)
        flash_alpha = int(54 * math.sin(math.pi * progress))
        if flash_alpha:
            flash = Image.new("RGB", current.size, (255, 242, 214))
            return Image.blend(blended, flash, flash_alpha / 255.0)
        return blended

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    edge = int(-height * 0.35 + (width + height * 0.7) * progress)
    draw.polygon(
        ((0, 0), (edge, 0), (edge - int(height * 0.35), height), (0, height)),
        fill=255,
    )
    feather = Image.new("L", (width, height), 0)
    feather_draw = ImageDraw.Draw(feather)
    feather_draw.line(
        (edge, 0, edge - int(height * 0.35), height),
        fill=255,
        width=10,
    )
    mask = Image.composite(feather, mask, feather.point(lambda value: value // 3))
    return Image.composite(current, previous, mask)


def _draw_chapter(
    frame: Image.Image,
    title: str,
    year: str,
    local_time: float,
) -> Image.Image:
    if not title and not year:
        return frame
    width, height = frame.size
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    alpha = int(235 * _ease(min(1.0, local_time / 0.45)))
    if title:
        font = _font(34, bold=True)
        text_width = min(1050, int(draw.textlength(title, font=font)))
        x = int(-min(60, max(0.0, 60.0 * (1.0 - _ease(local_time / 0.45)))) + 72)
        draw.rounded_rectangle(
            (x - 22, 52, x + text_width + 42, 116),
            radius=14,
            fill=(14, 18, 22, alpha),
            outline=(226, 182, 91, alpha),
            width=2,
        )
        draw.rounded_rectangle((x - 12, 66, x - 5, 102), radius=3, fill=(242, 192, 72, alpha))
        draw.text((x + 10, 64), title, font=font, fill=(255, 248, 229, alpha))
    if year:
        year_font = _font(30, bold=True)
        width = int(draw.textlength(year, font=year_font))
        x = frame.width - width - 106
        draw.rounded_rectangle(
            (x - 20, 52, frame.width - 70, 116),
            radius=14,
            fill=(14, 18, 22, alpha),
            outline=(226, 182, 91, alpha),
            width=2,
        )
        draw.text((x, 65), year, font=year_font, fill=(255, 226, 157, alpha))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_timeline(
    frame: Image.Image,
    t: float,
    start: float,
    end: float,
    events: list[dict[str, Any]],
) -> Image.Image:
    if end <= start:
        return frame
    width, height = frame.size
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, x1, y = 0.11 * width, 0.89 * width, int(0.165 * height)
    alpha = 220
    draw.rounded_rectangle((x0 - 34, y - 28, x1 + 34, y + 50), radius=18, fill=(12, 16, 20, 172))
    draw.line((x0, y, x1, y), fill=(208, 190, 155, 150), width=4)
    progress = max(0.0, min(1.0, (t - start) / (end - start)))
    active_x = int(x0 + (x1 - x0) * progress)
    draw.line((x0, y, active_x, y), fill=(238, 187, 71, alpha), width=5)

    font = _font(21, bold=True)
    for event in events:
        event_time = float(event["time"])
        if not start <= event_time <= end:
            continue
        label = str(event["label"])
        x = int(x0 + (x1 - x0) * (event_time - start) / (end - start))
        reached = t >= event_time
        color = (255, 224, 153, 255) if reached else (195, 190, 179, 185)
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color)
        draw.text((x - draw.textlength(label, font=font) / 2, y + 16), label, font=font, fill=color)

    pulse_radius = 12 + int((1.0 + math.sin(t * 3.4)) * 4)
    draw.ellipse(
        (active_x - pulse_radius, y - pulse_radius, active_x + pulse_radius, y + pulse_radius),
        outline=(255, 221, 130, 170),
        width=2,
    )
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_route_graphic(frame: Image.Image, local_time: float, language: str) -> Image.Image:
    entrance = _ease(min(1.0, local_time / 0.45))
    width, height = frame.size
    scale = min(width / 1080, height / 1080)
    panel_width, panel_height = round(430 * scale), round(210 * scale)
    x0 = width - panel_width - round(92 * scale) + round((1.0 - entrance) * 70 * scale)
    y0 = round(360 * scale)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    alpha = int(205 * entrance)
    draw.rounded_rectangle(
        (x0, y0, x0 + panel_width, y0 + panel_height),
        radius=20,
        fill=(10, 15, 20, int(160 * entrance)),
        outline=(230, 190, 112, alpha),
        width=2,
    )
    label = "YATRA" if language.lower().startswith("hindi") else "JOURNEY"
    font = _font(max(14, round(19 * scale)), bold=True)
    draw.text((x0 + 26, y0 + 18), label, font=font, fill=(247, 225, 185, alpha))

    points = [
        (x0 + round(42 * scale), y0 + round(154 * scale)),
        (x0 + round(132 * scale), y0 + round(124 * scale)),
        (x0 + round(228 * scale), y0 + round(142 * scale)),
        (x0 + round(350 * scale), y0 + round(84 * scale)),
    ]
    for left, right in zip(points, points[1:]):
        draw.line((left, right), fill=(187, 165, 126, int(125 * entrance)), width=3)

    progress = _ease(min(1.0, max(0.0, (local_time - 0.25) / 1.6)))
    segment = min(len(points) - 2, int(progress * (len(points) - 1)))
    segment_progress = min(1.0, progress * (len(points) - 1) - segment)
    active_x = round(points[segment][0] + (points[segment + 1][0] - points[segment][0]) * segment_progress)
    active_y = round(points[segment][1] + (points[segment + 1][1] - points[segment][1]) * segment_progress)
    for route_index in range(segment):
        draw.line(
            (points[route_index], points[route_index + 1]),
            fill=(238, 190, 92, int(235 * entrance)),
            width=4,
        )
    draw.line(
        (points[segment], (active_x, active_y)),
        fill=(238, 190, 92, int(235 * entrance)),
        width=4,
    )
    for point in (points[0], points[-1]):
        draw.ellipse((point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8), fill=(255, 228, 166, alpha))
    pulse = 13 + int(3 * (1 + math.sin(local_time * 5.0)))
    draw.ellipse(
        (active_x - pulse, active_y - pulse, active_x + pulse, active_y + pulse),
        fill=(241, 184, 70, alpha),
        outline=(255, 241, 204, alpha),
        width=3,
    )
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_impact_graphic(frame: Image.Image, local_time: float) -> Image.Image:
    duration = 0.85
    if local_time >= duration:
        return frame

    progress = local_time / duration
    eased = _ease(progress)
    alpha = int(170 * (1.0 - eased))
    width, height = frame.size
    scale = min(width / 1080, height / 1080)
    center_x, center_y = int(width * 0.66), int(height * 0.44)
    radius = int((38 + 190 * eased) * scale)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for inset in (0, round(42 * scale)):
        ring_radius = max(4, radius - inset)
        draw.ellipse(
            (center_x - ring_radius, center_y - ring_radius, center_x + ring_radius, center_y + ring_radius),
            outline=(255, 195, 91, max(0, alpha - inset // 2)),
            width=5 if inset == 0 else 3,
        )
    ray_length = int(55 * scale * (1.0 - eased))
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        inner = radius + 16
        outer = inner + ray_length
        draw.line(
            (
                center_x + math.cos(radians) * inner,
                center_y + math.sin(radians) * inner,
                center_x + math.cos(radians) * outer,
                center_y + math.sin(radians) * outer,
            ),
            fill=(255, 220, 151, alpha),
            width=3,
        )
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_lineage(frame: Image.Image, t: float, start: float, end: float) -> Image.Image:
    width, height = frame.size
    scale = min(width / 1080, height / 1080)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, x1, y = round(210 * scale), width - round(210 * scale), round(190 * scale)
    draw.rounded_rectangle((x0 - 48, 132, x1 + 48, 248), radius=22, fill=(10, 14, 18, 185))
    node_font = _font(max(13, round(20 * scale)), bold=True)
    label_font = _font(max(12, round(17 * scale)))
    current = max(0.0, min(1.0, (t - start) / max(0.01, end - start)))
    active_count = max(1, min(10, int(current * 10) + 1))
    positions = [int(x0 + (x1 - x0) * index / 9) for index in range(10)]
    draw.line((positions[0], y, positions[-1], y), fill=(195, 177, 139, 145), width=3)
    for index, x in enumerate(positions, start=1):
        reached = index <= active_count
        fill = (237, 187, 73, 255) if reached else (76, 80, 80, 220)
        radius = max(7, round(17 * scale))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
        numeral = str(index)
        width = draw.textlength(numeral, font=node_font)
        draw.text((x - width / 2, y - round(13 * scale)), numeral, font=node_font, fill=(22, 23, 24, 255))
        label = f"RAMA {index}"
        label_width = draw.textlength(label, font=label_font)
        draw.text((x - label_width / 2, y + round(27 * scale)), label, font=label_font, fill=(255, 239, 203, 235))
    active_x = positions[active_count - 1]
    active_radius = max(11, round(25 * scale))
    draw.ellipse((active_x - active_radius, y - active_radius, active_x + active_radius, y + active_radius), outline=(255, 229, 151, 190), width=3)
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


@lru_cache(maxsize=4)
def _paper_background(width: int, height: int) -> Image.Image:
    base = Image.new("RGB", (width, height), (235, 224, 195))
    draw = ImageDraw.Draw(base)
    line_gap = max(24, round(height * 0.026))
    for y in range(line_gap, height, line_gap):
        draw.line((0, y, width, y), fill=(202, 188, 157), width=1)
    margin_x = round(width * 0.065)
    draw.line((margin_x, 0, margin_x, height), fill=(200, 151, 127), width=2)
    draw.line((width - margin_x, 0, width - margin_x, height), fill=(220, 208, 178), width=1)
    return base


def _draw_paper_mascot(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, t: float) -> None:
    """Draw the same small orange-robed storyteller on every paper-style beat."""
    bob = round(math.sin(t * 1.8) * max(1, size * 0.025))
    y += bob
    center = x + size // 2
    skin = (188, 125, 81, 255)
    ink = (42, 31, 25, 255)
    robe = (220, 119, 37, 255)
    draw.ellipse((x + size * 0.12, y + size * 0.89, x + size * 0.88, y + size), fill=(84, 65, 45, 80))
    draw.line((center - size * 0.12, y + size * 0.68, center - size * 0.22, y + size * 0.91), fill=ink, width=max(2, size // 13))
    draw.line((center + size * 0.12, y + size * 0.68, center + size * 0.24, y + size * 0.91), fill=ink, width=max(2, size // 13))
    draw.polygon(
        (
            (center - size * 0.20, y + size * 0.34),
            (center + size * 0.18, y + size * 0.34),
            (center + size * 0.35, y + size * 0.76),
            (center, y + size * 0.84),
            (center - size * 0.33, y + size * 0.75),
        ),
        fill=robe,
        outline=ink,
    )
    draw.line((center - size * 0.15, y + size * 0.50, center + size * 0.16, y + size * 0.58), fill=(247, 191, 107, 255), width=max(2, size // 16))
    head_box = (center - size * 0.19, y + size * 0.10, center + size * 0.19, y + size * 0.43)
    draw.ellipse(head_box, fill=skin, outline=ink, width=max(2, size // 20))
    draw.pieslice((center - size * 0.22, y + size * 0.05, center + size * 0.22, y + size * 0.32), 180, 360, fill=ink)
    draw.polygon(
        (
            (center - size * 0.17, y + size * 0.29),
            (center + size * 0.17, y + size * 0.29),
            (center + size * 0.12, y + size * 0.47),
            (center, y + size * 0.53),
            (center - size * 0.15, y + size * 0.45),
        ),
        fill=ink,
    )
    draw.ellipse((center - size * 0.09, y + size * 0.23, center - size * 0.05, y + size * 0.27), fill=ink)
    draw.ellipse((center + size * 0.05, y + size * 0.23, center + size * 0.09, y + size * 0.27), fill=ink)


def _draw_paper_editorial(
    frame: Image.Image,
    title: str,
    scene_number: int,
    local_time: float,
) -> Image.Image:
    width, height = frame.size
    portrait = height > width
    base = _paper_background(width, height).copy()
    draw = ImageDraw.Draw(base)
    unit = max(0.75, min(1.0, width / 1080))
    margin = round(width * 0.09)
    micro = _font(round(20 * unit), bold=True)
    headline_size = round(43 * unit)
    headline = _font(headline_size, bold=True)

    draw.text((margin, round(height * 0.027)), "VOICE NOTES", font=micro, fill=(76, 61, 44))
    draw.text((width - margin, round(height * 0.027)), "FIG. %02d" % scene_number, font=micro, fill=(76, 61, 44), anchor="ra")
    draw.line((margin, round(height * 0.061), width - margin, round(height * 0.061)), fill=(120, 101, 74), width=2)
    mascot_size = round(96 * unit)
    _draw_paper_mascot(draw, width - margin - mascot_size, round(height * 0.068), mascot_size, local_time)

    heading = (title or f"VISUAL BEAT {scene_number:02d}").strip().upper()
    title_y = round(height * 0.083)
    max_title_width = width - 2 * margin - round(100 * unit)
    while draw.textlength(heading, font=headline) > max_title_width and headline_size > 25:
        headline_size -= 2
        headline = _font(headline_size, bold=True)
    label_width = min(max_title_width, int(draw.textlength(heading, font=headline) + 38 * unit))
    label_height = round(headline_size * 1.35)
    draw.polygon(
        (
            (margin - 5, title_y + 4),
            (margin + label_width, title_y),
            (margin + label_width + 10, title_y + label_height - 3),
            (margin + 2, title_y + label_height + 5),
        ),
        fill=(237, 166, 55),
    )
    draw.text((margin + round(12 * unit), title_y + round(2 * unit)), heading, font=headline, fill=(36, 31, 25))

    if portrait:
        card_width, card_height = round(width * 0.72), round(height * 0.62)
        card_left, card_top = (width - card_width) // 2, round(height * 0.205)
    else:
        card_width, card_height = round(width * 0.62), round(height * 0.55)
        card_left, card_top = (width - card_width) // 2, round(height * 0.205)

    # Offset paper sheets, a soft shadow, and a torn lower edge create the cutout stack.
    draw.rectangle(
        (card_left + 17, card_top + 20, card_left + card_width + 17, card_top + card_height + 20),
        fill=(110, 88, 59),
    )
    draw.polygon(
        (
            (card_left - 15, card_top + 17),
            (card_left + card_width - 10, card_top - 10),
            (card_left + card_width + 9, card_top + card_height - 24),
            (card_left + 30, card_top + card_height + 15),
        ),
        fill=(255, 247, 225),
    )
    border = round(20 * unit)
    inner_w, inner_h = card_width - 2 * border, card_height - 2 * border
    hero = ImageOps.fit(
        frame.convert("RGB"),
        (inner_w, inner_h),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.45),
    )
    base.paste(hero, (card_left + border, card_top + border))
    draw = ImageDraw.Draw(base)
    draw.rectangle(
        (card_left, card_top, card_left + card_width, card_top + card_height),
        outline=(255, 250, 235),
        width=border,
    )
    tear_y = card_top + card_height - round(20 * unit)
    tear = [(card_left, tear_y)]
    teeth = 18
    for index in range(teeth + 1):
        x = card_left + round(card_width * index / teeth)
        y = tear_y + (round(9 * unit) if index % 2 else 0)
        tear.append((x, y))
    tear.extend(((card_left + card_width, card_top + card_height), (card_left, card_top + card_height)))
    draw.polygon(tear, fill=(245, 237, 216))

    tape_w, tape_h = round(112 * unit), round(28 * unit)
    tape_x = card_left + card_width - tape_w - round(38 * unit)
    tape_y = card_top - round(9 * unit)
    draw.rectangle((tape_x, tape_y, tape_x + tape_w, tape_y + tape_h), fill=(233, 181, 81))
    draw.line((tape_x + 8, tape_y + tape_h // 2, tape_x + tape_w - 8, tape_y + tape_h // 2), fill=(245, 214, 148), width=2)

    # A repeated detail crop acts like a small overlapping scrapbook photograph.
    detail_w = round(card_width * 0.25)
    detail_h = round(card_height * (0.23 if portrait else 0.30))
    detail_border = max(9, round(13 * unit))
    detail_label_h = max(22, round(29 * unit))
    detail_art = ImageOps.fit(
        frame.convert("RGB"),
        (detail_w, detail_h),
        method=Image.Resampling.LANCZOS,
        centering=(0.62, 0.45),
    )
    detail_card = Image.new(
        "RGBA",
        (detail_w + detail_border * 2, detail_h + detail_border * 2 + detail_label_h),
        (255, 250, 235, 255),
    )
    detail_card.paste(detail_art, (detail_border, detail_border))
    detail_draw = ImageDraw.Draw(detail_card)
    detail_draw.text(
        (detail_border, detail_h + detail_border + 4),
        "DETAIL STUDY",
        font=_font(max(12, round(14 * unit)), bold=True),
        fill=(87, 67, 43, 255),
    )
    detail_card = detail_card.rotate(-3.5, resample=Image.Resampling.BICUBIC, expand=True)
    detail_x = card_left + card_width - detail_card.width - round(32 * unit)
    detail_y = card_top + card_height - detail_card.height + round(math.sin(local_time * 1.2) * 3)
    base.paste(detail_card, (detail_x, detail_y), detail_card)

    footer_font = _font(round(16 * unit), bold=True)
    footer_y = round(height * 0.965)
    draw.text((margin, footer_y), "A STORY IN MOTION", font=footer_font, fill=(87, 70, 49))
    draw.text((width - margin, footer_y), f"{scene_number:02d}", font=footer_font, fill=(87, 70, 49), anchor="ra")
    return base


def _draw_caption(
    frame: Image.Image,
    group: dict[str, Any] | None,
    t: float,
    paper_editorial: bool = False,
) -> Image.Image:
    if not group:
        return frame
    words = group.get("words", [])
    if not words:
        text = str(group.get("text", "")).strip()
        if not text:
            return frame
        words = [{"word": text, "start": group["start"], "end": group["end"]}]

    width, height = frame.size
    font_size = max(
        30,
        round(min(width * 0.045, height * 0.052)) if paper_editorial else round(width * 0.021),
    )
    font = _font(font_size, bold=True)
    small_font = _font(max(26, round(font_size * 0.9)), bold=True)
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_width = width - round(width * (0.16 if paper_editorial else 0.125))
    rows: list[list[dict[str, Any]]] = [[]]
    row_widths = [0.0]
    for item in words:
        word_width = measure.textlength(item["word"], font=font)
        index = len(rows) - 1
        projected = row_widths[index] + (round(font_size * 0.30) if rows[index] else 0) + word_width
        if projected > max_width and rows[index]:
            rows.append([])
            row_widths.append(0.0)
            index += 1
        row_widths[index] += (round(font_size * 0.30) if rows[index] else 0) + word_width
        rows[index].append(item)

    if len(rows) > 2:
        return _draw_caption(
            frame,
            {"start": group["start"], "end": group["end"], "text": " ".join(x["word"] for x in words)},
            t,
            paper_editorial=paper_editorial,
        )

    line_height = round(font_size * 1.34)
    box_height = len(rows) * line_height + round(font_size * 0.65)
    bottom_margin = round(height * (0.082 if paper_editorial else 0.10))
    top = height - bottom_margin - box_height
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    total_width = max(row_widths)
    left = (width - total_width) / 2
    draw.rounded_rectangle(
        (left - font_size * 0.65, top - 8, left + total_width + font_size * 0.65, top + box_height),
        radius=round(font_size * 0.42),
        fill=(248, 239, 216, 245) if paper_editorial else (10, 12, 14, 218),
        outline=(119, 82, 45, 230) if paper_editorial else (219, 174, 76, 180),
        width=2,
    )

    for row_index, row in enumerate(rows):
        x = (width - row_widths[row_index]) / 2
        y = top + row_index * line_height
        for item in row:
            text = item["word"]
            text_width = measure.textlength(text, font=font)
            active = float(item["start"]) <= t < float(item["end"])
            if active:
                draw.rounded_rectangle(
                    (x - 7, y + 1, x + text_width + 7, y + font_size * 1.15),
                    radius=round(font_size * 0.20),
                    fill=(241, 172, 51, 255),
                )
            draw.text(
                (x, y),
                text,
                font=font if text_width < max_width else small_font,
                fill=(34, 29, 22, 255) if (active or paper_editorial) else (250, 247, 239, 255),
            )
            x += text_width + round(font_size * 0.30)
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _draw_progress(frame: Image.Image, t: float, duration: float) -> Image.Image:
    width, height = frame.size
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, x1, y = round(width * 0.04), width - round(width * 0.04), height - max(18, round(height * 0.018))
    draw.rounded_rectangle((x0, y, x1, y + 6), radius=4, fill=(18, 18, 18, 150))
    progress = max(0.0, min(1.0, t / duration))
    end = int(x0 + (x1 - x0) * progress)
    draw.rounded_rectangle((x0, y, max(x0 + 1, end), y + 6), radius=4, fill=(238, 185, 68, 220))
    draw.ellipse((end - 5, y - 4, end + 5, y + 10), fill=(255, 230, 160, 245))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _caption_for_time(
    captions: list[dict[str, Any]],
    scene: dict[str, Any],
    t: float,
) -> dict[str, Any] | None:
    low, high = 0, len(captions)
    while low < high:
        middle = (low + high) // 2
        if float(captions[middle]["end"]) <= t:
            low = middle + 1
        else:
            high = middle
    if low < len(captions) and float(captions[low]["start"]) <= t < float(captions[low]["end"]):
        return captions[low]
    if scene.get("has_word_captions"):
        return None
    if scene.get("narration"):
        return {
            "start": float(scene["start"]),
            "end": float(scene["end"]),
            "text": str(scene["narration"]),
        }
    return None


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        tail = (result.stderr or result.stdout)[-3000:]
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{tail}")


def render_storyboard(
    scenes: list[dict[str, Any]],
    duration: float,
    destination: Path,
    captions: list[dict[str, Any]] | None = None,
    fps: int = FPS,
    progress: Progress | None = None,
    aspect_ratio: str = "16:9",
    visual_style: str = "Cinematic Documentary",
) -> Path:
    validate_timeline(scenes, duration, fps)
    width, height = video_dimensions(aspect_ratio)
    canvas_size = (width, height)
    paper_editorial = visual_style == "Paper Editorial"
    ordered = sorted(scenes, key=lambda scene: float(scene["start"]))
    caption_groups = captions or []
    if caption_groups and "word" in caption_groups[0]:
        caption_groups = group_caption_words(caption_groups)
    frames_total = round(duration * fps)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{width}x{height}",
        "-pix_fmt",
        "rgb24",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vf",
        (
            "eq=saturation=1.02:contrast=1.01,noise=alls=1:allf=t"
            if paper_editorial
            else "eq=saturation=1.04:contrast=1.03:gamma=1.01,vignette=PI/6,noise=alls=2:allf=t"
        ),
        "-frames:v",
        str(frames_total),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    previous_frame: Image.Image | None = None
    written = 0

    try:
        for scene_index, scene in enumerate(ordered):
            start_frame = round(float(scene["start"]) * fps)
            end_frame = round(float(scene["end"]) * fps)
            scene_frames = end_frame - start_frame
            image = _load_frame(Path(scene["image"]), canvas_size)
            visual_plan = plan_scene_motion(scene, scene_index)
            move = visual_plan["move"]
            effect = visual_plan["effect"]
            transition = "dissolve" if paper_editorial else visual_plan["transition"]
            transition_seconds = 0.18 if transition == "flash" else TRANSITION_SECONDS
            transition_frames = (
                0 if transition == "cut" else max(1, round(transition_seconds * fps))
            )
            year = str(scene.get("year", "") or "")
            title = str(
                scene.get("chapter", "")
                or scene.get("title", "")
                or scene.get("card", "")
                or ""
            )
            if paper_editorial and not title:
                narration_words = str(scene.get("narration", "")).split()
                title = " ".join(narration_words[:5]) + ("…" if len(narration_words) > 5 else "")
            for frame_index in range(scene_frames):
                global_frame = start_frame + frame_index
                global_time = global_frame / fps
                local_time = frame_index / fps
                fraction = frame_index / max(1, scene_frames - 1)
                camera_progress = (
                    global_frame / max(1, frames_total - 1)
                    if paper_editorial
                    else fraction
                )
                background = camera_frame(
                    image,
                    "pan_horizontal" if paper_editorial else move,
                    camera_progress,
                )
                background = _draw_particles(background, effect, scene_index + 1, local_time)

                frame = (
                    _draw_paper_editorial(background, title, scene_index + 1, global_time)
                    if paper_editorial
                    else _draw_chapter(background, title, year, local_time)
                )
                graphic = str(scene.get("graphic", ""))
                if graphic == "timeline":
                    frame = _draw_timeline(
                        frame,
                        global_time,
                        float(scene.get("graphic_start", 0.0)),
                        float(scene.get("graphic_end", duration)),
                        list(scene.get("timeline_events", [])),
                    )
                elif graphic == "lineage":
                    frame = _draw_lineage(
                        frame,
                        global_time,
                        float(scene.get("graphic_start", 0.0)),
                        float(scene.get("graphic_end", duration)),
                    )
                if effect == "map" or graphic == "route":
                    frame = _draw_route_graphic(
                        frame,
                        local_time,
                        str(scene.get("language", "English")),
                    )
                elif effect == "embers" or graphic == "impact":
                    frame = _draw_impact_graphic(frame, local_time)
                frame = _draw_caption(
                    frame,
                    _caption_for_time(caption_groups, scene, global_time),
                    global_time,
                    paper_editorial=paper_editorial,
                )
                frame = _draw_progress(frame, global_time, duration)
                if previous_frame is not None and frame_index < transition_frames:
                    frame = _draw_transition(
                        frame,
                        previous_frame,
                        (frame_index + 1) / transition_frames,
                        transition,
                    )
                assert process.stdin is not None
                process.stdin.write(frame.tobytes())
                written += 1
                if frame_index == scene_frames - 1:
                    previous_frame = frame

            if progress:
                progress(f"Animated scene {scene_index + 1}/{len(ordered)}")

        assert process.stdin is not None
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"FFmpeg render failed ({return_code}): {stderr.decode(errors='replace')[-3000:]}")
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise

    if written != frames_total:
        raise RuntimeError(f"Rendered {written} frames; expected {frames_total}.")
    return destination


def concatenate_audio(audio_paths: list[Path], destination: Path) -> float:
    if not audio_paths:
        raise ValueError("At least one narration clip is required.")
    for path in audio_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Narration audio not found: {path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for index, path in enumerate(audio_paths):
        inputs.extend(("-i", str(path)))
        label = f"audio{index}"
        filters.append(
            f"[{index}:a]aresample=44100,aformat=sample_fmts=fltp:"
            f"sample_rates=44100:channel_layouts=stereo[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(audio_paths)}:v=0:a=1[out]")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    _run(command)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def mux_documentary_audio(
    video: Path,
    voice: Path,
    destination: Path,
    music: Path | None = None,
    sfx: Path | None = None,
    music_gain: float = 0.50,
    sfx_gain: float = 0.40,
) -> Path:
    if not video.is_file() or not voice.is_file():
        raise FileNotFoundError("The rendered video and narration audio are both required.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["-i", str(video), "-i", str(voice)]
    filters = [
        "[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "loudnorm=I=-16:TP=-1.5,asplit=2[voice][voice_sc]"
    ]
    mix_labels = ["[voice]"]
    input_index = 2

    if music is not None:
        if not music.is_file():
            raise FileNotFoundError(f"Background music not found: {music}")
        inputs.extend(("-i", str(music)))
        filters.append(
            f"[{input_index}:a]aresample=44100,aformat=sample_fmts=fltp:"
            f"channel_layouts=stereo,loudnorm=I=-23:TP=-1.5:LRA=11,"
            f"volume={music_gain:.3f}[music_pre]"
        )
        filters.append(
            "[music_pre][voice_sc]sidechaincompress=threshold=0.04:ratio=4:"
            "attack=120:release=900[music]"
        )
        mix_labels.append("[music]")
        input_index += 1
    if sfx is not None:
        if not sfx.is_file():
            raise FileNotFoundError(f"Sound effects track not found: {sfx}")
        inputs.extend(("-i", str(sfx)))
        filters.append(
            f"[{input_index}:a]aresample=44100,aformat=sample_fmts=fltp:"
            f"channel_layouts=stereo,volume={sfx_gain:.3f}[sfx]"
        )
        mix_labels.append("[sfx]")

    filters.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:"
        "dropout_transition=1:normalize=0,alimiter=limit=0.94[aout]"
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return destination
