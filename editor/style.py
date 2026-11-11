"""Visual language extracted from the Beyond History Maya reference video."""

STYLE_BIBLE = """
Illustrated documentary, 2D educational cartoon, clean black ink outlines,
flat but rich coloring, warm earth tones, parchment cream skies, jungle greens,
limestone beige temples, historically themed, cinematic 16:9 wide shot,
one clear story beat per frame, no photorealism, no 3D render, no collage,
no watermark, no captions, no title text inside the illustration.
"""

IMAGE_NEGATIVE = (
    "photorealistic, photo, 3d, cgi, blurry, watermark, text, logo, "
    "subtitles, collage, messy composition, extra fingers"
)

KEN_BURNS = {
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "zoom_amount": 0.08,
    "min_shot_sec": 3.5,
    "tail_pad_sec": 0.35,
}

VOICES = {
    "English (US, documentary)": "en-US-AndrewNeural",
    "English (UK, documentary)": "en-GB-RyanNeural",
    "English (US, female)": "en-US-AvaNeural",
    "Hindi (male)": "hi-IN-MadhurNeural",
    "Hindi (female)": "hi-IN-SwaraNeural",
}

MUSIC_LEVEL_DB = -22
VOICE_LEVEL_DB = 0
