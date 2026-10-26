from __future__ import annotations

import copy
import math
import subprocess

import pytest

from app.video_studio.quality import (
    MODEL_PRICES,
    _parse_media_log,
    build_plan,
    default_style,
    validate_plan,
    validate_render,
)


@pytest.fixture
def library():
    return [
        {"id": "reference-boy", "media_kind": "image", "tags": ["protagonist", "scene"], "approved": True},
        {"id": "web-real", "kind": "video", "duration": 1, "tags": ["screen", "web"], "approved": True},
        {"id": "failure", "kind": "video", "duration": 10, "tags": ["failure", "hook", "work"], "approved": True},
        {"id": "research", "kind": "video", "duration": 8, "tags": ["research"], "approved": True},
        {"id": "success", "kind": "video", "duration": 8, "tags": ["success", "office"], "approved": True},
    ]


def errors(plan):
    return {item["code"] for item in validate_plan(plan) if item["severity"] == "error"}


def test_style_preserves_requested_identity_and_caption_treatment():
    style = default_style()
    assert style["characters"]["protagonist"]["age"] == 23
    assert "black hoodie" in style["characters"]["protagonist"]["description"]
    assert style["captions"]["font_size"] == 80
    assert style["captions"]["outline"] == style["captions"]["shadow"] == 0
    assert style["quality"]["creative_review_required"] is True
    assert style["quality"]["zero_errors_guaranteed"] is False
    assert style["voice"]["roles"] == ["narrator", "son", "mother"]
    assert style["characters"]["protagonist"]["voice_role"] == "son"


@pytest.mark.parametrize("duration", [8, 12, 15, 20, 25, 30, 40])
def test_plan_duration_uses_exact_frames_and_one_brief_real_screen(library, duration):
    plan = build_plan({"duration": duration, "format": "story", "budget_usd": 10}, library)
    assert sum(round(shot["duration"] * 24) for shot in plan["shots"]) == duration * 24
    screens = [shot for shot in plan["shots"] if shot["role"] == "screen"]
    assert len(screens) == 1
    assert screens[0]["asset_id"] == "web-real"
    assert screens[0]["duration"] == 1
    assert screens[0]["mode"] == "library"
    assert plan["ready_for_delivery"] is False
    assert not errors(plan)


def test_default_plan_generates_new_visuals_without_reusing_old_story(library):
    plan = build_plan({"duration": 15}, library)
    assert all(shot["mode"] == "generate" for shot in plan["shots"] if shot["role"] != "screen")
    assert all(shot["native_audio"] == "mute" for shot in plan["shots"])
    assert all(shot["prepare_integrated_scene_image"] is False for shot in plan["shots"] if shot["mode"] == "generate")
    assert all(shot["image_preparation_status"] == "approved_reference" for shot in plan["shots"] if shot["mode"] == "generate")
    assert plan["cost_estimate"]["scene_images_usd"] == 0
    assert plan["estimated_cost_usd"] == plan["cost_estimate"]["video_first_take_usd"]


def test_store_seed_screen_tags_are_recognized(library):
    library[1].update(id="screen_reveal", tags=["website", "real_screen", "discovery"])
    plan = build_plan({}, library)
    screen = next(shot for shot in plan["shots"] if shot["role"] == "screen")
    assert screen["asset_id"] == "screen_reveal"
    assert not errors(plan)


@pytest.mark.parametrize("input_role", ["son", "protagonist"])
def test_son_voice_role_is_normalized(library, input_role):
    plan = build_plan({"voice_role": input_role}, library)
    assert plan["narrations"][0]["voice_role"] == "son"


def test_reuse_is_explicit_and_respects_approved_source_windows(library):
    library[2]["usable_in"] = 3
    library[2]["usable_out"] = 9
    plan = build_plan({"duration": 15, "reuse_library": True}, library)
    first = plan["shots"][0]
    assert first["asset_id"] == "failure"
    assert first["source_in"] == 3
    assert first["source_out"] <= 9
    assert plan["estimated_cost_usd"] == 0


def test_short_clip_is_not_frozen_or_looped_to_fill_longer_shot(library):
    library[2]["duration"] = 1
    plan = build_plan({"duration": 15, "reuse_library": True}, library)
    assert plan["shots"][0]["mode"] == "generate"


def test_missing_reference_blocks_generation(library):
    plan = build_plan({"duration": 15}, [item for item in library if item["id"] != "reference-boy"])
    assert "missing_reference" in errors(plan)
    assert all(shot["image_preparation_status"] == "missing_reference" for shot in plan["shots"] if shot["mode"] == "generate")


def test_unapproved_explicit_reference_is_not_silently_replaced(library):
    library.append({"id": "bad-reference", "kind": "image", "approved": False})
    plan = build_plan({"reference_asset_id": "bad-reference"}, library)
    assert "missing_reference" in errors(plan)


def test_explicit_reference_is_retained(library):
    library.append({"id": "reference-two", "kind": "image", "approved": True})
    plan = build_plan({"reference_asset_id": "reference-two"}, library)
    assert all(shot["reference_asset_id"] == "reference-two" for shot in plan["shots"] if shot["mode"] == "generate")


def test_screen_cannot_be_hallucinated_when_real_capture_missing(library):
    plan = build_plan({}, [item for item in library if item["id"] != "web-real"])
    assert "missing_library_asset" in errors(plan)
    screen = next(shot for shot in plan["shots"] if shot["role"] == "screen")
    screen["mode"] = "generate"
    assert "generated_web_forbidden" in errors(plan)


def test_spoken_brand_is_forbidden_even_with_mixed_case(library):
    plan = build_plan({"script": "Entonces encontré DropRadar."}, library)
    assert "spoken_brand" in errors(plan)


def test_promised_income_is_blocked(library):
    plan = build_plan({"script": "Aquí tienes ingresos garantizados."}, library)
    assert "guaranteed_income" in errors(plan)


def test_long_script_requires_edit_instead_of_cut_or_speedup(library):
    plan = build_plan({"duration": 8, "script": "Una frase demasiado larga para entrar completa. " * 8}, library)
    assert "speech_would_be_cut" in errors(plan)
    assert len(plan["narrations"]) == 1
    assert plan["narrations"][0]["text"].endswith("completa.")


def test_actual_elevenlabs_duration_overrides_word_estimate(library):
    plan = build_plan({"duration": 8}, library)
    plan["narrations"][0]["duration"] = 8.1
    plan["narrations"][0]["estimated_duration"] = 1
    assert "speech_would_be_cut" in errors(plan)


def test_visible_speech_requires_lipsync_review(library):
    plan = build_plan({}, library)
    plan["shots"][0]["visible_lip_dialogue"] = True
    assert "lipsync_review" in errors(plan)
    plan["shots"][0]["lipsync_approved"] = True
    assert "lipsync_review" not in errors(plan)


def test_historical_dialogue_can_be_previewed_but_is_not_delivery_ready(library):
    library[4]["contains_dialogue"] = True
    production = build_plan({"reuse_library": True}, library)
    preview = build_plan({"reuse_library": True, "technical_preview": True}, library)
    assert "lipsync_review" in errors(production)
    assert "lipsync_review" not in errors(preview)
    assert any(issue["code"] == "lipsync_review" and issue["severity"] == "warning" for issue in preview["issues"])
    assert preview["ready_for_delivery"] is False


def test_budget_counts_generation_rounding_and_retry_reserve(library):
    plan = build_plan({"duration": 8, "model": "h3_turbo", "budget_usd": 0.3, "max_attempts": 2}, library)
    generated = [shot for shot in plan["shots"] if shot["mode"] == "generate"]
    assert [shot["generation_duration"] for shot in generated] == [5, 5]
    assert plan["cost_estimate"]["video_first_take_usd"] == 0.4
    assert plan["estimated_max_cost_usd"] > 0.8
    assert "budget_exceeded" in errors(plan)


def test_a_gap_between_shots_blocks_export(library):
    plan = build_plan({}, library)
    plan["shots"][1]["timeline_start"] += 0.5
    assert "timeline_gap_or_overlap" in errors(plan)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -3, 0, True, "not a number"])
def test_invalid_duration_is_rejected(library, bad):
    with pytest.raises(ValueError):
        build_plan({"duration": bad}, library)


def test_media_parser_uses_input_not_output_dimensions_and_keeps_night_warnings():
    log = """Input #0, mov,mp4, from 'test.mp4':
  Duration: 00:00:08.00, start: 0.000000, bitrate: 100 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 1080x1920 [SAR 1:1 DAR 9:16], 24 fps, 24 tbr
  Stream #0:1: Audio: aac, 48000 Hz, stereo
Output #0, null, to 'pipe:':
  Stream #0:0: Video: wrapped_avframe, yuv420p, 64x112, 30 fps
[blackdetect] black_start:1 black_end:1.5 black_duration:0.5
[silencedetect] silence_start: 6
[silencedetect] silence_end: 8 | silence_duration: 2
[astats] Peak level dB: -4.100000
"""
    result = _parse_media_log(log)
    assert (result["width"], result["height"], result["fps"]) == (1080, 1920, 24)
    assert result["duration"] == 8
    assert result["black_intervals"] == [{"start": 1, "end": 1.5, "duration": 0.5}]
    assert result["audio_peak_dbfs"] == -4.1


def test_missing_render_is_not_approved(tmp_path):
    report = validate_render(tmp_path / "missing.mp4", {"duration": 8})
    assert report["technical_passed"] is False
    assert report["ready_for_delivery"] is False


def test_actual_mp4_decode_checks_do_not_claim_creative_approval(tmp_path):
    import imageio_ffmpeg
    binary = imageio_ffmpeg.get_ffmpeg_exe()
    path = tmp_path / "fixture.mp4"
    completed = subprocess.run([
        binary, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x112:r=24:d=8",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", str(path),
    ], capture_output=True, timeout=30, check=False)
    assert completed.returncode == 0, completed.stderr.decode()
    report = validate_render(path, {"duration": 8, "width": 64, "height": 112, "fps": 24, "narrations": [{"text": "Prueba", "start": 0.2, "duration": 4}]}, binary)
    assert report["technical_passed"] is True, report
    assert report["ready_for_delivery"] is False
    assert report["review_required"] is True
    assert all(item["passed"] is None for item in report["creative_checks"])


def test_word_timestamps_beyond_render_are_blocking(tmp_path, monkeypatch):
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"a" * 2048)
    log = "Duration: 00:00:08.00\nStream #0:0: Video: h264, yuv420p, 1080x1920, 24 fps\nStream #0:1: Audio: aac, 48000 Hz\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "", log))
    report = validate_render(path, {"duration": 8, "fps": 24, "narrations": [{"start": 1, "alignment": {"character_end_times_seconds": [7.8]}}]}, "fake-ffmpeg")
    assert report["technical_passed"] is False
    assert "word_cut_in_render" in {item["code"] for item in report["issues"]}
