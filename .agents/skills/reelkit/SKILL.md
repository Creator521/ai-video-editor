---
name: reelkit
description: Plan, assemble, and render programmatic short-form and documentary videos using Reelkit's video-as-code methodology. Specializes in word-level caption synchronization, kinetic typography, dynamic camera moves, transition sound effects, motion graphics overlays, and local high-definition rendering.
metadata:
  short-description: Reelkit programmatic video-as-code production workflow
---

# Reelkit Programmatic Video Production Workflow

Reelkit transforms coding agents into automated video directors and compositors. Rather than relying on static slideshows or basic slide transitions, Reelkit treats video as code—combining frame-accurate timing, word-by-word kinetic captions, animated graphical overlays, dynamic camera physics, and layered sound design.

---

## Core Principles of Reelkit

1. **Word-Level Synchronization (No Lazy Holds)**
   - Every spoken phrase or sentence is broken down into word-level timestamps.
   - Captions are animated dynamically (karaoke style / highlighted active words), keeping viewer eyes focused on the screen.
   - Visual transitions align with spoken phrase boundaries (never drifting or terminating early).

2. **Multi-Layered Visual Compositing**
   - **Background Layer**: 16:9 or 9:16 primary artwork, moving footage, or painterly illustration with subtle continuous Ken Burns motion (push-in, pan, or float).
   - **Asset / Badge Overlay Layer**: Contextual graphic badges (year scrolls, maps, character title cards, battle seals) that pop in with ease-out bounce and subtle floating physics.
   - **Kinetic Typography Layer**: Dynamic word captions with glowing drop-shadows, bold contrast colors (gold, yellow, white), and highlighted keywords that scale slightly on emphasis.
   - **Vignette & Lighting Grade**: Cinematic dark edges and warm color grading that unifies diverse visual assets into a coherent broadcast aesthetic.

3. **Layered Sound Design (SFX + Music + Vocals)**
   - **Voiceover (Vocal Track)**: Normalized, compressed, and crisp at 0dB reference.
   - **Sound Effects (SFX Track)**: Subtly placed whooshes on camera transitions, parchment rustles on maps, deep sub-booms on dramatic turns, and chime rings on year badges.
   - **Ambient / Score Bed**: Continuous low-frequency cinematic drone or traditional instrumental track ducked by -18dB whenever speech is active.

4. **Structured Project Architecture (`plan.json`)**
   A standard Reelkit project maintains a deterministic state:
   - `plan.json`: The complete timecoded blueprint of scenes, assets, movements, captions, and sound cues.
   - `assets/`: 2D illustrations, portraits, vector graphics, badges, and sound effects.
   - `audio/`: Master vocal track and word-level Whisper transcription.
   - `out/`: Master compiled render.

5. **Rendering Pipeline**
   - High-throughput frame streaming to FFmpeg (`libx264` / `aac`) ensuring 100% frame-accuracy without memory leaks or dropped frames.
   - Strict duration matching with master vocal audio: `total_frames = round(master_audio_duration * fps)`.

---

## When to Use Reelkit

- When videos must match dynamic YouTube video styles (like Beyond History, Vox, MagnatesMedia, or Reels).
- When viewer retention demands fast visual cuts (every 2.5–4.5s), animated subtitles, and kinetic typography.
- When adding audio sound effects (whooshes, hits, ambient textures) to elevate an edit above a silent slideshow.
- When rendering complex multi-layer graphics (badges, maps, borders, lower-thirds) programmatically.
