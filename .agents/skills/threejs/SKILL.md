---
name: threejs
description: Create 3D scene, camera, lighting, and motion concepts or browser rendered elements for documentary shots. Use when a scene benefits from 3D maps, diagrams, reconstructions, or camera moves.
---

# Three.js for documentary shots

Three.js is a JavaScript 3D library. It is not currently part of this Python/Gradio editor. Use it as a separate browser-rendering or asset-generation path when a 3D shot is needed; export rendered frames or a video and bring them into the existing FFmpeg assembly workflow.

## Shot workflow

1. Define the shot's purpose, aspect ratio, duration, camera path, and assets before building geometry.
2. Set up a `Scene`, camera, lights, and `WebGLRenderer`; use an animation loop driven by elapsed time so each frame is reproducible.
3. Keep framing, lighting, and colors consistent with the documentary's visual treatment. Prefer restrained camera motion and clear silhouettes for maps, architecture, and explanatory diagrams.
4. Render a preview and check composition, clipping, performance, and frame pacing. Capture at the project's target resolution and frame rate before compositing.
5. Use the official Three.js docs/examples and check its MIT license and any asset licenses.

Install only when implementing the browser renderer: `npm install three`. Do not add this dependency to the Python project unless a Three.js rendering feature is actually being built.

Official references: https://threejs.org/docs/ and https://threejs.org/manual/
Source: https://github.com/mrdoob/three.js
