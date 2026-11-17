from types import SimpleNamespace

from editor import transcribe
from editor.voice_beats import make_voice_scene_plan, validate_voice_scene_ranges


def test_transcription_keeps_word_level_timestamps(tmp_path, monkeypatch):
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"audio")
    calls = {}

    class FakeModel:
        def transcribe(self, path, **kwargs):
            calls["path"] = path
            calls["kwargs"] = kwargs
            word = SimpleNamespace(word=" namaste", start=0.2, end=0.65)
            segment = SimpleNamespace(words=[word])
            return [segment], SimpleNamespace(language="hi")

    monkeypatch.setattr(transcribe, "_load_model", lambda model_name: FakeModel())
    result = transcribe.transcribe_audio(audio, "Hindi")

    assert result["language"] == "hi"
    assert result["words"] == [{"word": "namaste", "start": 0.2, "end": 0.65}]
    assert calls["kwargs"]["word_timestamps"] is True
    assert calls["kwargs"]["language"] == "hi"


def test_voice_scene_plan_groups_words_and_covers_full_audio():
    words = [
        {"word": "The", "start": 0.2, "end": 0.45},
        {"word": "old", "start": 0.48, "end": 0.72},
        {"word": "city", "start": 0.75, "end": 1.05},
        {"word": "woke", "start": 1.1, "end": 1.4},
        {"word": "again.", "start": 1.45, "end": 1.9},
        {"word": "The", "start": 4.0, "end": 4.2},
        {"word": "river", "start": 4.25, "end": 4.8},
        {"word": "rose.", "start": 4.85, "end": 5.3},
    ]

    scenes = make_voice_scene_plan(words, 6.0, topic="Ancient city", max_seconds=2.0)

    assert len(scenes) >= 2
    assert scenes[0]["start"] == 0.0
    assert scenes[-1]["end"] == 6.0
    assert "Ancient city" in scenes[0]["image_prompt"]
    validate_voice_scene_ranges(scenes, 6.0)


def test_voice_scene_range_validation_rejects_gaps():
    scenes = [
        {"start": 0.0, "end": 1.0},
        {"start": 1.2, "end": 2.0},
    ]

    try:
        validate_voice_scene_ranges(scenes, 2.0)
    except ValueError as exc:
        assert "gap or overlap" in str(exc)
    else:
        raise AssertionError("A voice scene gap should be rejected.")
