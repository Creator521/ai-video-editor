# Video editing skill guides

These are project-scoped Codex skill guides under `.agents/skills/` for the five requested repositories. They describe how their tools or methods fit this project's Python/Gradio + FFmpeg workflow.

Only Lemo-Opuscar and PixelFX publish agent skills upstream, and those are Claude Code skills; this workspace contains Codex-oriented adaptations rather than the complete upstream packages. Three.js is a JavaScript library, MCP for Blender is an external Blender/client integration, and FreeCut is a separate full browser editor. Their guides explain use and setup, but do not install those runtimes or change global MCP settings.

Project architecture: `app.py` provides the Gradio UI, `editor/` contains research, script, image, TTS, pipeline, style, and FFmpeg assembly modules, and `outputs/` stores rendered jobs. Current video path is narration/scenes → research or generated images → voice/audio → FFmpeg still-shot motion and final MP4.
