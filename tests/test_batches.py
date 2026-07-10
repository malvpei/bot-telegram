import pytest

from app.batches import (
    BatchItemKind,
    build_batch_plan,
    normalize_schedule_time,
    parse_schedule_values,
)
from app.models import Language, VideoGender, VideoType


def test_first_batch_matches_requested_six_video_layout():
    plan = build_batch_plan(6, phase=0)

    assert [item.kind for item in plan] == [
        BatchItemKind.GENERATED,
        BatchItemKind.GENERATED,
        BatchItemKind.GENERATED,
        BatchItemKind.TOOLS,
        BatchItemKind.GENERATED,
        BatchItemKind.GENERATED,
    ]
    assert [item.video_type for item in plan] == [
        VideoType.TYPE_1,
        VideoType.TYPE_2,
        VideoType.TYPE_3,
        None,
        VideoType.TYPE_1,
        VideoType.TYPE_2,
    ]
    assert [item.language for item in plan] == [
        Language.ES,
        Language.ES,
        Language.EN,
        Language.ES,
        Language.EN,
        Language.ES,
    ]
    assert plan[-1].gender == VideoGender.FEMALE


def test_each_lane_runs_two_type_cycles_then_tools_and_restarts():
    first_lane = [build_batch_plan(1, phase)[0] for phase in range(8)]

    assert [item.video_type.value if item.video_type else "tools" for item in first_lane] == [
        "1",
        "2",
        "3",
        "1",
        "2",
        "3",
        "tools",
        "1",
    ]


def test_all_numeric_positions_advance_to_next_type_in_second_batch():
    plan = build_batch_plan(6, phase=1)

    assert [item.video_type.value if item.video_type else "tools" for item in plan] == [
        "2",
        "3",
        "1",
        "1",
        "2",
        "3",
    ]
    assert plan[-1].gender == VideoGender.FEMALE


def test_batch_size_can_repeat_the_six_lane_profile():
    plan = build_batch_plan(8, phase=0)

    assert len(plan) == 8
    assert plan[6].language == plan[0].language
    assert plan[6].video_type == plan[0].video_type
    assert plan[7].language == plan[1].language
    assert plan[7].video_type == plan[1].video_type


def test_schedule_parser_accepts_count_deduplicates_and_sorts_times():
    count, times = parse_schedule_values(["6", "18:00", "8:00", "08:00"])

    assert count == 6
    assert times == ["08:00", "18:00"]


def test_schedule_parser_uses_six_as_default_count():
    count, times = parse_schedule_values(["08:00", "18:00"])

    assert count == 6
    assert times == ["08:00", "18:00"]


@pytest.mark.parametrize("raw_value", ["24:00", "12:60", "8", "aa:bb"])
def test_invalid_schedule_times_are_rejected(raw_value):
    with pytest.raises(ValueError):
        normalize_schedule_time(raw_value)
