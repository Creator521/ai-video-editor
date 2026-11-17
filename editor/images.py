from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from editor.style import KEN_BURNS

Progress = Callable[[str], None]


STYLE_PREFIX = (
    "2D educational cartoon documentary illustration, ink outlines, "
    "warm earth tones, parchment sky, historically themed, no text"
)

PAPER_EDITORIAL_PREFIX = (
    "Handmade editorial illustration for a paper-collage documentary, "
    "flat cut-paper shapes layered like a crafted scrapbook, delicate ink outlines, "
    "warm parchment cream, amber and ochre accents, tactile paper grain, "
    "strong simple composition, one clear subject, no lettering, no captions, no watermark"
)


def generate_scene_image(
    prompt: str,
    dest: Path,
    seed: int,
    aspect_ratio: str = "16:9",
    visual_style: str = "Cinematic Documentary",
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    visual = " ".join(prompt.replace("\n", " ").split())
    if len(visual) > 420:
        visual = visual[:420]
    if aspect_ratio == "9:16":
        width, height = 1080, 1920
        composition = "Vertical 9:16 portrait composition; keep the main subject large and inside the center safe area."
    else:
        width, height = 1920, 1080
        composition = "Wide 16:9 landscape composition; keep the main subject clear and inside the center safe area."
    style_prefix = PAPER_EDITORIAL_PREFIX if visual_style == "Paper Editorial" else STYLE_PREFIX
    full = f"{visual}. {composition} {style_prefix}"
    encoded = urllib.parse.quote(full, safe="")
    params = urllib.parse.urlencode(
        {"width": width, "height": height, "seed": seed, "nologo": "true"}
    )
    url = f"https://image.pollinations.ai/prompt/{encoded}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 BeyondEditor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        if not resp.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Image provider returned a non-image response")
        image_bytes = resp.read(25 * 1024 * 1024 + 1)
        if len(image_bytes) > 25 * 1024 * 1024:
            raise ValueError("Generated image is larger than 25 MB")
        dest.write_bytes(image_bytes)
    _fit_frame(dest, width, height)
    return dest


def generate_all_images(script: dict, job_dir: Path, progress: Progress | None = None) -> list[Path]:
    img_dir = job_dir / "images"
    img_dir.mkdir(exist_ok=True)
    paths: list[Path] = []
    scenes = script["scenes"]
    for scene in scenes:
        dest = img_dir / f"scene_{scene['id']:03d}.png"
        if progress:
            progress(f"Drawing scene {scene['id']}/{len(scenes)}…")
        seed = int(hashlib.md5(scene["image_prompt"].encode("utf-8")).hexdigest()[:8], 16)
        try:
            generate_scene_image(scene["image_prompt"], dest, seed)
        except Exception as exc:  # noqa: BLE001
            (dest.with_suffix(".err.txt")).write_text(str(exc), encoding="utf-8")
            _placeholder(dest, scene)
        paths.append(dest)
    return paths


def _fit_frame(path: Path, width: int | None = None, height: int | None = None) -> None:
    w = int(width or KEN_BURNS["width"])
    h = int(height or KEN_BURNS["height"])
    im = Image.open(path).convert("RGB")
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    im.crop((left, top, left + w, top + h)).save(path, "PNG")


def _placeholder(path: Path, scene: dict) -> None:
    w, h = KEN_BURNS["width"], KEN_BURNS["height"]
    im = Image.new("RGB", (w, h), (42, 32, 24))
    draw = ImageDraw.Draw(im)
    draw.rectangle([80, 80, w - 80, h - 80], outline=(210, 180, 120), width=4)
    font = _font(54)
    text = scene.get("card") or scene.get("year") or f"Scene {scene['id']}"
    draw.text((w // 2, h // 2), text, fill=(236, 220, 180), font=font, anchor="mm")
    im.save(path, "PNG")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/arial.ttf"):
        p = Path(name)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()
