from dataclasses import replace

import pytest
from PIL import Image

from app.config import get_settings
from app.parkez import PARKEZ_ROLES, build_parkez_script
from app.models import Language, MediaCandidate, SlidePlan, VideoGender, VideoPlan, VideoType
from app.parkez_mode3 import (
    PARKEZ_MODE3_SOCIAL_COPY_IDS,
    build_parkez_mode3_script,
)
from app.state import StateStore
from app.render import VideoRenderer
from app.service import VideoCreationService


def test_mode3_preserves_the_exact_hook_and_screenshot_texts(tmp_path):
    package = build_parkez_mode3_script(StateStore(tmp_path / "state"))

    assert package.ordered_slides == [
        "Los 3 trucos que nadie te cuenta cuando te sacas el carnet",
        "Tu coche siempre te marca menos velocidad a la real, échale cuenta a la "
        "velocidad del GPS para ahórrate multas",
        "Ten cuidado con justo frenar antes de llegar al radar, muchos puntos "
        "tienen radares dobles para pillarte antes de que frenes",
        "Para no dar vueltas buscando dónde aparcar, usa apps como ParkEz y ve "
        "directamente donde hay aparcamiento",
    ]
    assert package.plain_text == "\n\n".join(package.ordered_slides)
    assert package.social_copy.hook == ""
    assert package.social_copy.messages == [
        package.social_copy.title, package.social_copy.description
    ]


def test_mode3_rotates_15_distinct_pairs_persistently_without_consuming_on_peek(tmp_path):
    state_dir = tmp_path / "state"
    ids, titles, descriptions = [], [], []
    for _ in range(15):
        # A new instance each time also simulates restarting the bot.
        store = StateStore(state_dir)
        package = build_parkez_mode3_script(store)
        assert build_parkez_mode3_script(store) == package
        ids.append(package.social_choice_key)
        titles.append(package.social_copy.title)
        descriptions.append(package.social_copy.description)
        assert store.remember_parkez_mode3_social_copy_choice(
            package.social_choice_key, PARKEZ_MODE3_SOCIAL_COPY_IDS
        )

    assert len(set(ids)) == len(set(titles)) == len(set(descriptions)) == 15
    assert set(ids) == set(PARKEZ_MODE3_SOCIAL_COPY_IDS)
    restarted = build_parkez_mode3_script(StateStore(state_dir))
    assert restarted.social_choice_key in ids
    assert restarted.social_choice_key != ids[-1]


def test_mode3_queue_is_independent_of_hombre_and_tools(tmp_path):
    store = StateStore(tmp_path / "state")
    first = build_parkez_mode3_script(store)
    build_parkez_script(store, VideoGender.MALE)
    tools_id, _ = store.peek_next_cartools_social_copy_id(["tools-1", "tools-2"])
    store.remember_cartools_social_copy_choice(tools_id, ["tools-1", "tools-2"])
    assert build_parkez_mode3_script(store) == first
    next_tools_id, _ = store.peek_next_cartools_social_copy_id(["tools-1", "tools-2"])
    store.remember_parkez_mode3_social_copy_choice(
        first.social_choice_key, PARKEZ_MODE3_SOCIAL_COPY_IDS
    )
    assert store.peek_next_cartools_social_copy_id(["tools-1", "tools-2"])[0] == next_tools_id


def test_mode3_real_render_matches_clean_hombre_images_and_preserves_fixed_close(tmp_path):
    settings = replace(get_settings(), width=72, height=128)
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = settings
    service.renderer = VideoRenderer(settings)
    package = build_parkez_mode3_script(StateStore(tmp_path / "state"))
    slides = []
    expected_images = []
    for index, role in enumerate(PARKEZ_ROLES, start=1):
        path = tmp_path / f"source_{index}.png"
        Image.new("RGB", (90, 120), (index * 40, 60, 80)).save(path)
        slide = SlidePlan(
            index=index, role=role, text=package.slides_by_role[role],
            media=MediaCandidate(
                source_account="fixed" if index == 4 else "alpha",
                source_id=f"source:{index}", local_path=path,
                permalink="", caption="", width=90, height=120, created_at="",
            ),
            fixed_asset=index == 4,
        )
        slides.append(slide)
        if index < 4:
            expected_images.append(service.renderer.render_slide_still(
                replace(slide, text=""), VideoType.PARKEZ
            ))
    fixed_path = slides[-1].media.local_path
    fixed_bytes = fixed_path.read_bytes()
    plan = VideoPlan(
        chosen_account="alpha", video_type=VideoType.PARKEZ_MODE3,
        language=Language.ES, slides=slides,
    )

    video_path, script_path = service._render_outputs(
        plan, tmp_path / "output", embed_slide_text=False
    )

    assert video_path is None  # Like Hombre, this is a carousel, not an MP4.
    for text in package.ordered_slides:
        assert text in script_path.read_text(encoding="utf-8")
    for slide, expected in zip(slides[:3], expected_images, strict=True):
        with Image.open(slide.media.local_path) as rendered:
            assert rendered.size == (72, 128)
            assert rendered.tobytes() == expected.convert("RGB").tobytes()
    assert slides[-1].media.local_path == fixed_path
    assert fixed_path.read_bytes() == fixed_bytes

    # Missing source images must not silently produce an incomplete carousel.
    slides[0].media = replace(slides[0].media, local_path=tmp_path / "missing.png")
    with pytest.raises(FileNotFoundError, match="Falta una imagen de mode3"):
        service._render_outputs(plan, tmp_path / "missing-output", embed_slide_text=False)
