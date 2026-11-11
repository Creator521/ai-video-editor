"""Short local render to verify FFmpeg + TTS + Ken Burns."""

from editor.pipeline import run_pipeline


if __name__ == "__main__":
    result = run_pipeline(
        topic="Maya civilization",
        minutes=0.5,
        language="English",
        max_scenes=2,
        progress=print,
    )
    print(result)
