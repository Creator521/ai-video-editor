import json

import pytest

from app import manual_voice_entries, resolve_manual_image_mode
from editor.jobs import create_job_dir
from editor.script import build_script, fallback_script


def test_job_directories_are_unique_and_keep_pipeline_subfolders(tmp_path):
    first = create_job_dir(tmp_path / "outputs")
    second = create_job_dir(tmp_path / "outputs")

    assert first != second
    assert all((first / name).is_dir() for name in ("shots", "audio", "images"))
    assert all((second / name).is_dir() for name in ("shots", "audio", "images"))


def test_legacy_scene_image_mode_does_not_override_current_global_choice():
    reviewed = {"image_mode": "AI illustration"}

    assert resolve_manual_image_mode(reviewed, "Wikimedia photo") == "Wikimedia photo"
    assert resolve_manual_image_mode(
        {"image_mode_override": "AI illustration"}, "Wikimedia photo"
    ) == "AI illustration"


def test_additional_voice_files_require_a_scene_one_clip():
    with pytest.raises(ValueError, match="scene 1"):
        manual_voice_entries(["scene2.mp3"], None, 2)

    assert manual_voice_entries(["scene2.mp3"], "scene1.mp3", 2) == [
        "scene1.mp3",
        "scene2.mp3",
    ]


def test_fallback_script_does_not_use_maya_specific_visuals():
    script = fallback_script("Roman history", "English")
    joined = " ".join(
        scene["narration"] + " " + scene["image_prompt"] for scene in script["scenes"]
    ).lower()

    assert script["scenes"]
    assert "pyramid" not in joined
    assert "jungle" not in joined


def test_script_uses_and_records_research_sources(tmp_path, monkeypatch):
    source = {
        "title": "Sample source",
        "url": "https://example.test/source",
        "extract": "A short verified excerpt.",
    }
    prompt_seen = {}

    def fake_chat_json(system, user):
        prompt_seen["user"] = user
        return {
            "title": "Sample",
            "subtitle": "",
            "scenes": [
                {
                    "narration": "A short scene.",
                    "image_prompt": "A relevant illustration.",
                }
            ],
        }

    monkeypatch.setattr("editor.script.chat_json", fake_chat_json)
    result = build_script(
        "Sample topic",
        0.5,
        "English",
        tmp_path,
        research_sources=[source],
    )

    assert "A short verified excerpt." in prompt_seen["user"]
    assert result["sources"] == [{"title": source["title"], "url": source["url"]}]
    saved = json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))
    assert saved["sources"] == result["sources"]
