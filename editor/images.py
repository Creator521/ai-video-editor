from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from editor.style import KEN_BURNS

Progress = Callable[[str], None]


STYLE_PREFIX = (
    "2D educational cartoon documentary illustration, ink outlines, "
    "warm earth tones, parchment sky, historically themed, cinematic 16:9, no text"
)


def generate_scene_image(prompt: str, dest: Path, seed: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    visual = " ".join(prompt.replace("\n", " ").split())
    if len(visual) > 420:
        visual = visual[:420]
    full = f"{visual}. {STYLE_PREFIX}"
    encoded = urllib.parse.quote(full, safe="")
    params = urllib.parse.urlencode(
        {"width": 1920, "height": 1080, "seed": seed, "nologo": "true"}
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
    _fit_frame(dest)
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
        _maybe_card(dest, scene)
        paths.append(dest)
    return paths


def _fit_frame(path: Path) -> None:
    w, h = KEN_BURNS["width"], KEN_BURNS["height"]
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


def _maybe_card(path: Path, scene: dict) -> None:
    year = scene.get("year") or ""
    card = scene.get("card") or ""
    if not year and not card:
        return
    im = Image.open(path).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    label = "  ".join(p for p in (year, card) if p)
    font = _font(48)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 28, 16
    x = (im.width - tw) // 2
    y = im.height - th - 90
    box = [x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y]
    draw.rounded_rectangle(box, radius=8, fill=(20, 14, 10, 170), outline=(220, 190, 130, 220), width=2)
    draw.text((x, y), label, font=font, fill=(245, 230, 190, 255))
    out = Image.alpha_composite(im, overlay).convert("RGB")
    out = out.filter(ImageFilter.SMOOTH)
    out.save(path, "PNG")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/arial.ttf"):
        p = Path(name)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()
