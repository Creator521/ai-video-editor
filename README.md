# Illustrated Documentary AI

Turns a topic into an illustrated documentary with continuous camera motion, animated editorial graphics, documentary voiceover, and a mixed final MP4.

The renderer uses 1920×1080, 30 fps illustrated scenes, continuous camera moves, animated chapter graphics, and voice-led pacing. It is a local 2.5D animation pipeline; it does not generate AI video footage.

## Setup

```powershell
cd "C:\path\to\AI Video Editor"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

FFmpeg must be installed and available on `PATH`.

## Run

```powershell
python app.py
```

Browser opens on `http://127.0.0.1:7860`. Enter a topic, pick English or Hindi, click **Edit documentary**.

## Manual Studio

Open the **Manual Studio** tab to write narration, record/upload audio, and prepare scene research. Use a blank line between paragraphs to create scenes. Record or upload the first scene's voice clip, then add additional scene clips in order. Scenes without supplied audio use the selected fallback TTS voice.

Manual Studio defaults to **AI illustration**: each image prompt uses that scene's narration and the top Wikipedia research result as context. Choose **Wikimedia photo** to use an attributed Commons image instead. Review and edit the scene JSON, including each scene's `image_prompt`, before rendering. Generated illustrations can invent historical details, so review them for accuracy. Commons candidates include the file page, creator and license metadata when provided; generated jobs save `research.json` and `attribution.txt` alongside the video. Wikipedia is a starting reference, not independent fact-checking, and image licenses/attributions should be reviewed before publication.

If no suitable Commons image is found or download fails, the scene uses a generated placeholder rather than an unverified external image.

## Better scripts (optional)

Without an LLM, the app writes a clearly marked generic outline, not a researched documentary script. For a topic-specific draft set one of:

- `GROQ_API_KEY` (free at console.groq.com)
- `OPENAI_API_KEY`
- local [Ollama](https://ollama.com) with `OLLAMA_MODEL=llama3.1`

Images default to [Pollinations](https://pollinations.ai) (no key). Voice is Microsoft Edge TTS (no key).

## Image sources and generation

You do not need to copy images into a project folder. In **AI Documentary**, the script creates one English `image_prompt` per scene; Pollinations receives that prompt and returns a 1920×1080 still image. The app saves it under `outputs/<job>/images/`. If the image service fails, the app uses a placeholder card. This creates still illustrations, not AI video footage.

In **Manual Studio**, choose **AI illustration** to generate a still from the scene narration and the first Wikipedia result as context. You can edit `image_prompt` in the scene JSON before rendering. Choose **Wikimedia photo** to search Wikimedia Commons; edit `selected_image` in the JSON to choose a candidate. The file page, creator, and license details are saved in `attribution.txt` when available. There is no separate local image-upload control in the current UI.

For a full voice recording, open **Voice-led visuals**, record/upload the narration, and click **Transcribe & plan visuals**. Local Faster-Whisper transcription creates word timestamps, groups nearby words into visual beats, and proposes one image prompt per beat. Adjust **Approx. seconds per visual beat** to get more or fewer image changes. Review/edit the JSON, choose AI illustration or Wikimedia photo, and click **Render voice-led video**. Word-timed captions and scene-aware camera/motion graphics are rendered against the same recording. Choose **Paper Editorial** for ruled parchment, layered paper image cards, a recurring illustrated storyteller, continuous camera drift across beat changes, and an amber-highlighted active word. Voice-led output supports 9:16 YouTube Shorts and 16:9 landscape videos. Wikimedia mode uses the first Commons match for each beat; when no usable match is available, the app tries to generate a matching illustration. Review the attribution file before publishing. The first transcription can download the Whisper model; set `WHISPER_MODEL` to choose another installed/downloadable model size.

The voice-led transcription runs locally; its generated image prompts are sent to Pollinations when AI illustration is selected. Other narration text may be sent to the selected online TTS/image services. Wikipedia and Wikimedia Commons are contacted for research and image search. Avoid entering material you do not want sent to those services.

## Motion and transitions

The renderer uses still illustrations with animated camera moves, scene-aware dust, water, ember, and route graphics, date timelines, and transitions chosen from scene context. Edge TTS and voice-led Faster-Whisper transcription provide word timings for active-word captions; older uploaded scene clips use scene-level captions. Cinematic Documentary favors clean cuts, dissolves, wipes, or brief flashes. Paper Editorial uses a shared camera drift and dissolves while the visual beat cards change. Both styles animate still images and graphics; the app does not generate live-action or AI video footage.

## Output

Each run writes `outputs/<timestamp>_<unique-id>/final.mp4` plus the script, scene images, narration, research references, and a `picture.mp4` intermediate. Manual Studio also writes image attribution details.
