import pytest
from zoneinfo import ZoneInfo

from app.batches import (
    BATCH_ROTATION_CYCLE_LENGTH,
    ROTATION,
    BatchLane,
    BatchItemKind,
    build_batch_plan,
    normalize_schedule_time,
    parse_schedule_values,
    schedule_time_to_datetime_time,
)
from app.models import Language, VideoGender, VideoType


def test_first_batch_has_five_videos_and_no_female_lane():
    plan = build_batch_plan(5, phase=0)

    assert [item.kind for item in plan] == [
        BatchItemKind.GENERATED,
        BatchItemKind.GENERATED,
        BatchItemKind.GENERATED,
        BatchItemKind.AI,
        BatchItemKind.GENERATED,
    ]
    assert [item.video_type for item in plan] == [
        VideoType.TYPE_1,
        VideoType.TYPE_2,
        VideoType.TYPE_3,
        VideoType.TYPE_4,
        VideoType.TYPE_1,
    ]
    assert [item.language for item in plan] == [
        Language.ES,
        Language.ES,
        Language.EN,
        Language.ES,
        Language.EN,
    ]
    assert all(item.gender == VideoGender.MALE for item in plan)


def test_spanish_male_lane_runs_ai_after_each_type_cycle_then_tools():
    first_lane = [build_batch_plan(1, phase)[0] for phase in range(9)]

    assert [item.video_type.value if item.video_type else "tools" for item in first_lane] == [
        "1",
        "2",
        "3",
        "4",
        "1",
        "2",
        "3",
        "4",
        "tools",
    ]
    assert first_lane[3].kind == BatchItemKind.AI
    assert first_lane[7].kind == BatchItemKind.AI
    assert first_lane[-1].kind == BatchItemKind.TOOLS


def test_second_batch_advances_each_lane_and_can_schedule_english_ai():
    plan = build_batch_plan(5, phase=1)

    assert [item.video_type.value if item.video_type else "tools" for item in plan] == [
        "2",
        "3",
        "4",
        "1",
        "2",
    ]
    assert plan[2].kind == BatchItemKind.AI
    assert plan[2].language == Language.EN
    assert plan[3].kind == BatchItemKind.GENERATED
    assert plan[3].video_type == VideoType.TYPE_1
    assert all(item.gender == VideoGender.MALE for item in plan)


def test_batch_size_can_repeat_the_five_lane_profile():
    plan = build_batch_plan(7, phase=0)

    assert len(plan) == 7
    assert plan[5].language == plan[0].language
    assert plan[5].video_type == plan[0].video_type
    assert plan[6].language == plan[1].language
    assert plan[6].video_type == plan[1].video_type


def test_legacy_batch_lane_constructor_and_rotation_alias_stay_compatible():
    lane = BatchLane(Language.EN, VideoGender.MALE, 0)

    assert lane.rotation == ROTATION
    assert ROTATION == ("1", "2", "3", "ai", "1", "2", "3", "ai", "tools")


def test_ai_rotates_equally_in_english_and_spanish_and_no_women_enter_batches():
    assert BATCH_ROTATION_CYCLE_LENGTH == 9
    ai_items = {Language.ES: 0, Language.EN: 0}
    for phase in range(BATCH_ROTATION_CYCLE_LENGTH):
        plan = build_batch_plan(5, phase=phase)
        for item in plan:
            assert item.gender == VideoGender.MALE
            if item.kind == BatchItemKind.AI:
                ai_items[item.language] += 1
                assert item.gender == VideoGender.MALE
                assert item.video_type == VideoType.TYPE_4

    # There are three Spanish lanes and two English lanes, but each individual
    # lane contains exactly two AI slots in the same nine-step cycle.
    assert ai_items == {Language.ES: 6, Language.EN: 4}
    assert [item.short_label for item in build_batch_plan(5, 0)] == [
        item.short_label
        for item in build_batch_plan(5, BATCH_ROTATION_CYCLE_LENGTH)
    ]


def test_schedule_parser_accepts_count_deduplicates_and_sorts_times():
    count, times = parse_schedule_values(["6", "17:00", "8:00", "08:00"])

    assert count == 6
    assert times == ["08:00", "17:00"]


def test_schedule_parser_uses_five_as_default_count():
    count, times = parse_schedule_values(["08:00", "17:00"])

    assert count == 5
    assert times == ["08:00", "17:00"]


def test_schedule_preparation_can_start_two_hours_before_deadline():
    timezone = ZoneInfo("Europe/Madrid")

    morning = schedule_time_to_datetime_time(
        "08:00",
        timezone,
        minute_offset=-120,
    )
    afternoon = schedule_time_to_datetime_time(
        "17:00",
        timezone,
        minute_offset=-120,
    )

    assert (morning.hour, morning.minute) == (6, 0)
    assert (afternoon.hour, afternoon.minute) == (15, 0)
    assert morning.tzinfo == timezone


@pytest.mark.parametrize("raw_value", ["24:00", "12:60", "8", "aa:bb"])
def test_invalid_schedule_times_are_rejected(raw_value):
    with pytest.raises(ValueError):
        normalize_schedule_time(raw_value)
