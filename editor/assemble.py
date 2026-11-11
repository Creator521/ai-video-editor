from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from editor.style import KEN_BURNS, MUSIC_LEVEL_DB, VOICE_LEVEL_DB

Progress = Callable[[str], None]


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return float(json.loads(out)["format"]["duration"])


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{tail}")


def render_shot(image: Path, audio: Path, dest: Path, motion: str) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    voice_dur = _ffprobe_duration(audio)
    duration = max(KEN_BURNS["min_shot_sec"], voice_dur + KEN_BURNS["tail_pad_sec"])
    fps = KEN_BURNS["fps"]
    frames = int(duration * fps)
    zoom_to = 1.0 + KEN_BURNS["zoom_amount"]
    if motion == "out":
        z = f"if(eq(on,1),{zoom_to},max({zoom_to}-{KEN_BURNS['zoom_amount']}*on/{frames},1.0))"
    else:
        z = f"min(1.0+{KEN_BURNS['zoom_amount']}*on/{frames},{zoom_to})"
    vf = (
        f"scale=3200:1800:force_original_aspect_ratio=increase,"
        f"crop=3200:1800,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s=1920x1080:fps={fps},"
        "eq=saturation=1.05:contrast=1.04:gamma=1.02,"
        "vignette=PI/5,"
        "format=yuv420p"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-i",
            str(audio),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return duration


def make_music(total: float, dest: Path, user_music: Path | None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if user_music and user_music.exists():
        _run(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(user_music),
                "-t",
                f"{total:.3f}",
                "-af",
                f"loudnorm=I=-18:TP=-1.5,volume={MUSIC_LEVEL_DB}dB,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo",
                str(dest),
            ]
        )
        return dest
    wav = dest.with_suffix(".wav")
    fade_out_start = max(0.0, total - 2.5)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=110:sample_rate=44100:duration={total:.3f}",
            "-af",
            f"lowpass=f=280,volume={MUSIC_LEVEL_DB}dB,afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_start:.3f}:d=2.2",
            str(wav),
        ]
    )
    return wav


def concat_and_mix(
    shots: list[Path],
    music: Path,
    dest: Path,
    progress: Progress | None = None,
) -> Path:
    if progress:
        progress("Assembling final cut…")
    lst = dest.parent / "concat.txt"
    lines = []
    for shot in shots:
        p = shot.resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{p}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    silent_cut = dest.parent / "picture_voice.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(silent_cut),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_cut),
            "-i",
            str(music),
            "-filter_complex",
            f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={VOICE_LEVEL_DB}dB[v];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1[m];"
            f"[v][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return dest

