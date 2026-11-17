---
name: pixelfx
description: Add, design, or export pixel-art effects and transitions for video scenes, titles, or overlays. Use for retro, 8-bit, game-like visual treatments.
---

# PixelFX for video overlays

PixelFX is a JavaScript pixel-art effect library, not a Python/FFmpeg plugin. Use it for a browser/canvas overlay or render its effect frames to transparent sprite sheets, then composite those frames into a video with the editor's existing FFmpeg pipeline.

## Workflow

1. Pick an effect from the upstream catalog (for example weather, fire, impact, magic, glitch, or transition) and decide its screen position, duration, palette, and layer order.
2. Prefer a deterministic seeded effect and keep the pixel resolution intentionally low; scale it with nearest-neighbor interpolation for crisp pixels.
3. Render a contact sheet or short preview and inspect for seams, stray pixels, clipping, and timing. For character actions, include wind-up, contact pause, target reaction, and recovery rather than displaying a static effect alone.
4. Export transparent PNG frames/sheets and composite them in the video timeline. Keep original resolution and frame timing documented.
5. Check the upstream license and NOTICE for any asset/font before shipping.

Upstream usage: `npm i github:patch-gg/pixelfx`; effects are under `src/fx/<category>/<name>.js`, and `node tools/render.mjs <effect-id> --sheet` exports a sheet. This JavaScript dependency is not installed in this Python project by this guide.

Source: https://github.com/patch-gg/pixelfx
