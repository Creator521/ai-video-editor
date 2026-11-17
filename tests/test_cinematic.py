from PIL import Image, ImageChops

from app import split_manual_script
from editor.cinematic import (
    HEIGHT,
    WIDTH,
    _draw_impact_graphic,
    _draw_route_graphic,
    _draw_transition,
    _caption_for_time,
    plan_scene_motion,
)


def test_scene_motion_uses_narration_context():
    battle = plan_scene_motion({"narration": "The battle set the palace on fire."}, 1)
    journey = plan_scene_motion({"narration": "The army followed a route across the river."}, 0)

    assert battle["effect"] == "embers"
    assert battle["graphic"] == "impact"
    assert battle["transition"] == "flash"
    assert journey["effect"] == "map"
    assert journey["move"] == "pan_horizontal"
    assert journey["graphic"] == "route"


def test_map_scenes_get_a_route_graphic_and_wipe():
    plan = plan_scene_motion(
        {"narration": "A long journey began.", "image_prompt": "An illustrated map"},
        1,
    )

    assert plan["effect"] == "map"
    assert plan["transition"] == "wipe"


def test_year_scenes_get_a_timeline_and_intentional_dissolve():
    plan = plan_scene_motion({"narration": "The kingdom began.", "year": "1857"}, 0)

    assert plan["graphic"] == "timeline"
    assert plan["transition"] == "dissolve"


def test_cut_and_dissolve_transitions():
    previous = Image.new("RGB", (1920, 1080), (0, 0, 0))
    current = Image.new("RGB", (1920, 1080), (255, 255, 255))

    assert _draw_transition(current, previous, 0.5, "cut").getpixel((960, 540)) == (255, 255, 255)
    assert _draw_transition(current, previous, 0.5, "dissolve").getpixel((960, 540)) == (127, 127, 127)


def test_slide_transition_has_correct_endpoints():
    previous = Image.new("RGB", (1920, 1080), (0, 0, 0))
    current = Image.new("RGB", (1920, 1080), (255, 255, 255))

    assert _draw_transition(current, previous, 0.0, "slide").getpixel((960, 540)) == (0, 0, 0)
    assert _draw_transition(current, previous, 1.0, "slide").getpixel((960, 540)) == (255, 255, 255)


def test_contextual_graphics_animate_and_then_clear():
    frame = Image.new("RGB", (WIDTH, HEIGHT), (30, 30, 30))

    route_early = _draw_route_graphic(frame, 0.0, "English")
    route_late = _draw_route_graphic(frame, 1.8, "English")
    impact = _draw_impact_graphic(frame, 0.2)
    impact_finished = _draw_impact_graphic(frame, 1.0)

    assert ImageChops.difference(route_early, route_late).getbbox() is not None
    assert ImageChops.difference(frame, impact).getbbox() is not None
    assert ImageChops.difference(frame, impact_finished).getbbox() is None


def test_manual_scene_split_keeps_sentences_in_the_same_paragraph():
    scenes = split_manual_script("First sentence. Another sentence.\n\nA second scene.")

    assert len(scenes) == 2
    assert scenes[0]["narration"] == "First sentence. Another sentence."
    assert scenes[1]["narration"] == "A second scene."


def test_word_timed_caption_gap_does_not_show_the_whole_narration():
    scene = {
        "start": 0.0,
        "end": 2.0,
        "narration": "A short narration.",
        "has_word_captions": True,
    }

    assert _caption_for_time([], scene, 1.0) is None
