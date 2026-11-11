# Illustrated Documentary AI

Turns a topic into a **Beyond History–style** illustrated documentary: cartoon frames, slow Ken Burns moves, documentary voiceover, title card, and a mixed final MP4.

The reference in this folder (`The Entire History of Maya Civilization…mp4`) is 1920×1080, 30 fps, illustrated 2D scenes cut to narration. This editor copies that grammar.

## Setup

```powershell
cd "E:\AI agent for video editor"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

FFmpeg must be on PATH (already used to inspect the reference video).

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

Without an LLM, a built-in template is used. For a real documentary script set one of:

- `GROQ_API_KEY` (free at console.groq.com)
- `OPENAI_API_KEY`
- local [Ollama](https://ollama.com) with `OLLAMA_MODEL=llama3.1`

Images default to [Pollinations](https://pollinations.ai) (no key). Voice is Microsoft Edge TTS (no key).

## Output

Each run writes `outputs/<timestamp>/final.mp4` plus `script.json`, scene images, narration, and shots.
