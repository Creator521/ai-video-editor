from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from editor.style import KEN_BURNS


def make_title_card(title: str, subtitle: str, dest: Path) -> Path:
    w, h = KEN_BURNS["width"], KEN_BURNS["height"]
    im = Image.new("RGB", (w, h), (18, 14, 10))
    draw = ImageDraw.Draw(im)
    draw.rectangle([70, 70, w - 70, h - 70], outline=(210, 180, 120), width=3)
    draw.rectangle([86, 86, w - 86, h - 86], outline=(160, 120, 70), width=1)
    title_font = _font(72)
    sub_font = _font(32)
    draw.text((w // 2, h // 2 - 30), title, fill=(236, 220, 175), font=title_font, anchor="mm")
    if subtitle:
        draw.text((w // 2, h // 2 + 50), subtitle, fill=(190, 170, 130), font=sub_font, anchor="mm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    return dest


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/times.ttf"):
        p = Path(name)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()
