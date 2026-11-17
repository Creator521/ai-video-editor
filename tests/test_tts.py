import asyncio

from editor import tts


def test_synthesized_tts_returns_word_boundaries(tmp_path, monkeypatch):
    class FakeCommunicate:
        def __init__(self, text, voice, rate):
            self.text = text

        async def stream(self):
            yield {"type": "audio", "data": b"audio-bytes"}
            yield {
                "type": "WordBoundary",
                "offset": 1_000_000,
                "duration": 5_000_000,
                "text": "Hello",
            }

    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
    destination = tmp_path / "voice" / "scene.mp3"
    words = asyncio.run(tts._synthesize_scene("Hello", "en-US-AndrewNeural", destination))

    assert destination.read_bytes() == b"audio-bytes"
    assert words == [{"word": "Hello", "start": 0.1, "end": 0.6}]
