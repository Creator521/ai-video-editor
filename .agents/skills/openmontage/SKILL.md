---
name: openmontage
description: Plan and build documentary and explainer videos with OpenMontage's pipeline-driven production approach, especially when combining narration, real footage, generated visuals, graphics, and sound.
metadata:
  short-description: OpenMontage documentary workflow
---

# OpenMontage production workflow

Use this skill when a video needs a deliberate production plan with scene-by-scene intent, mixed visual sources, purposeful motion, and review gates. This workspace is a Python/Gradio documentary editor; this skill adapts OpenMontage's production approach to the local tools. It does not mean the upstream OpenMontage runtime or its providers are installed.

Upstream reference: [OpenMontage](https://github.com/OpenMontageInc/OpenMontage), especially its documentary-montage pipeline and stage skills. The upstream system separates pipeline instructions, available tools, and provider-specific skills. Follow the same distinction here: plan the creative job first, check which local tools are actually available, and never claim a provider or runtime exists just because it is described here.

## Production approach

1. **Understand the material.** Inspect the supplied narration/audio and any reference video. Transcribe the narration when needed; identify its actual claims, names, dates, emotional turns, and pacing. Analyze the reference for visual language and rhythm, not as a request to copy its content.
2. **Propose a treatment.** Define the central question, audience, narrative arc, visual grammar, chapter rhythm, sound plan, and delivery format. For a reference-led job, state what will carry over (such as painterly historical reconstruction, scene variety, and pacing) and what will be original to the subject.
3. **Plan scenes against speech.** Create time-coded scene beats from the narration. Each scene must illustrate the words being spoken at that moment. Put the matching narration excerpt, visual subject/action, shot scale, camera movement, graphic or animation idea, source type, and sound cue in the plan. Use a concrete visual change when the narration makes a new claim or changes place, time, scale, or emotion.
4. **Choose assets by evidence and purpose.** Prefer verified real photographs/footage for documented people, places, and artifacts; use AI-generated imagery for reconstructions that cannot be photographed, and label it internally as a reconstruction. Use multiple independent visual references and record provenance for sourced assets. Check historical details against research; do not let an attractive image silently assert an unsupported fact.
5. **Use mixed visual grammar.** Combine relevant moving footage or distinct stills with purposeful camera moves, animated maps, timelines, labeled diagrams, object closeups, archival documents, and restrained kinetic typography when they clarify the narration. Give each graphic a job. Avoid repeated image cards, generic filler, constant transitions, and captions as a substitute for visual storytelling.
6. **Design sound with the edit.** Keep supplied voiceover intelligible and aligned to the cut. Choose music for the story's emotional movement, set it beneath speech, and add restrained contextual sound effects only where they support a visible action or transition. Include source/license notes for external audio.
7. **Review before final render.** Preview representative scenes and the full edit. Check that image/action and spoken line match, visual references vary, graphics are legible, motion is intentional, pacing follows the narration, soundtrack does not mask speech, and the final file's duration/aspect ratio/audio are correct. Revise any scene that feels like an unrelated insert or a static slideshow.

## Local project fit

- The editor lives in `app.py` and `editor/`; generated jobs belong under `outputs/`.
- Inspect actual editor capabilities and installed dependencies before selecting a render path. If OpenMontage's full runtime is later added, use its pipeline manifest and stage director skills as the source of truth for that runtime.
- Do not promise AI image/video generation, stock retrieval, Remotion, HyperFrames, Blender, or a music provider unless the corresponding local tool, credential, and dependency are available.
- Keep the scene plan, prompts, research/provenance, generated assets, and final render together in the job output so the edit can be reviewed and revised.

## Upstream workflow reference

OpenMontage's documented documentary pipeline is idea → scene plan → assets → edit → compose, with explicit human review at creative gates. Its quality guidance also calls out slideshow risk, weak motion, repetition, and visuals that do not support the shot's intent. Apply those checks to this editor's scene plan and preview before export.
