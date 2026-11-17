---
name: freecut-editor
description: Edit existing footage in FreeCut with a multi-track timeline, keyframes, effects, transitions, audio processing, captions, and browser export. Use for hands-on editing of media beyond this project's automated documentary generation.
---

# FreeCut editing workflow

FreeCut is a separate browser-based editor. It complements this project: use this app to generate a documentary draft, then use FreeCut when a human needs timeline-based trimming, rearrangement, keyframe motion, effects, audio EQ, captions, or alternate exports.

## Workflow

1. Open FreeCut in a supported Chromium browser and choose a workspace folder.
2. Create a project, import the rendered MP4 and any separate audio/media, then arrange clips on tracks.
3. Use source in/out, ripple/rolling/slip/slide edits, markers, transitions, effects, masks, and keyframes as needed. Keep narration intelligible and check music under speech.
4. Review the complete sequence, captions, color, audio, and export settings before exporting.

The upstream repository is a full React/TypeScript browser editor, not a skill or dependency of this Python app. Its source setup uses Node.js 22+, npm 11+, `npm install`, and `npm run dev`; the browser workflow uses WebGPU/WebCodecs and local workspace files.

Source: https://github.com/walterlow/freecut
