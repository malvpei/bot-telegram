import hashlib
import random
from pathlib import Path

from PIL import Image

from app.models import Language, SlideRole, VideoGender, VideoType
from app.parkez import (
    PARKEZ_FEMALE_FIXED_IMAGE_NAME,
    PARKEZ_MALE_FIXED_IMAGE_NAME,
    PARKEZ_ROLES,
    build_parkez_script,
    parkez_fixed_image_name,
)
from app.state import StateStore


class _FirstChoice:
    @staticmethod
    def choice(values):
        return values[0]


def test_parkez_copy_has_four_separate_messages_and_promotes_parkez(tmp_path):
    store = StateStore(tmp_path / "state")

    for gender in VideoGender:
        package = build_parkez_script(store, gender, rng=random.Random(7))

        assert list(package.slides_by_role) == list(PARKEZ_ROLES)
        assert len(package.ordered_slides) == 4
        assert package.ordered_slides[0]
        assert "ParkEz" in package.slides_by_role[SlideRole.PARKEZ_PROMO]
        assert package.social_copy.messages == []


def test_parkez_base_packs_keep_the_attached_hooks_and_tips(tmp_path):
    store = StateStore(tmp_path / "state")
    female = build_parkez_script(
        store,
        VideoGender.FEMALE,
        rng=_FirstChoice(),  # type: ignore[arg-type]
    )
    male = build_parkez_script(
        store,
        VideoGender.MALE,
        rng=_FirstChoice(),  # type: ignore[arg-type]
    )

    assert female.ordered_slides[0] == "Cómo bajar el cortisol con 3 sencillos tips 😉"
    assert female.ordered_slides[1] == (
        "Cuando sientas estrés mastica chicle, esto hace que tu cuerpo se "
        "relaje inconscientemente."
    )
    assert female.ordered_slides[2] == (
        "El agua fría activa tu instinto, tu cuerpo se relaja pasado 10 segundos."
    )
    assert female.ordered_slides[3] == (
        "Relájate a la hora de aparcar usando aplicaciones como ParkEz que te "
        "dicen dónde hay sitio."
    )
    assert male.ordered_slides[0] == "Trucos de vida que deberían ser ilegales 🤫"
    assert male.ordered_slides[1] == (
        "Si sientes ansiedad, lávate las manos con agua caliente. Engañarás a "
        "tu cerebro pensando que estás a salvo."
    )
    assert male.ordered_slides[2] == (
        "Para cruzar multitudes, mira fijamente hacia tu destino y no a la "
        "gente. Se apartarán solos."
    )
    assert male.ordered_slides[3] == (
        "Quítate el estrés de aparcar, usa aplicaciones como ParkEz para "
        "encontrar aparcamiento libre en la calle."
    )


def test_parkez_copy_does_not_repeat_the_previous_pack(tmp_path):
    store = StateStore(tmp_path / "state")
    first = build_parkez_script(store, VideoGender.FEMALE, rng=random.Random(3))
    store.set_last_text_choice(
        VideoType.PARKEZ,
        Language.ES,
        first.choice_key,
        profile=VideoGender.FEMALE.value,
    )

    second = build_parkez_script(store, VideoGender.FEMALE, rng=random.Random(3))

    assert second.choice_key != first.choice_key
    assert second.signature != first.signature


def test_parkez_copy_rotates_independently_when_profiles_alternate(tmp_path):
    store = StateStore(tmp_path / "state")
    female_first = build_parkez_script(
        store,
        VideoGender.FEMALE,
        rng=_FirstChoice(),  # type: ignore[arg-type]
    )
    store.set_last_text_choice(
        VideoType.PARKEZ,
        Language.ES,
        female_first.choice_key,
        profile=VideoGender.FEMALE.value,
    )
    male = build_parkez_script(
        store,
        VideoGender.MALE,
        rng=_FirstChoice(),  # type: ignore[arg-type]
    )
    store.set_last_text_choice(
        VideoType.PARKEZ,
        Language.ES,
        male.choice_key,
        profile=VideoGender.MALE.value,
    )

    female_second = build_parkez_script(
        store,
        VideoGender.FEMALE,
        rng=_FirstChoice(),  # type: ignore[arg-type]
    )

    assert female_second.choice_key != female_first.choice_key


def test_parkez_fixed_image_name_matches_gender():
    assert parkez_fixed_image_name(VideoGender.MALE) == PARKEZ_MALE_FIXED_IMAGE_NAME
    assert (
        parkez_fixed_image_name(VideoGender.FEMALE)
        == PARKEZ_FEMALE_FIXED_IMAGE_NAME
    )


def test_parkez_fixed_assets_are_clean_reference_images():
    fixed_dir = Path(__file__).resolve().parents[1] / "assets" / "fixed"
    expected_hashes = {
        PARKEZ_MALE_FIXED_IMAGE_NAME: (
            "52a7db745d1d5c9dac9e8faeccf43316e864698a480e6d0810bbf6fa9e3bcc22"
        ),
        PARKEZ_FEMALE_FIXED_IMAGE_NAME: (
            "bf3251d2b5714dee153fcc2bc487e12b9c17c8f97aeefecad0a14c301c3be1b4"
        ),
    }

    for name in (PARKEZ_MALE_FIXED_IMAGE_NAME, PARKEZ_FEMALE_FIXED_IMAGE_NAME):
        asset_path = fixed_dir / name
        assert hashlib.sha256(asset_path.read_bytes()).hexdigest() == expected_hashes[name]
        with Image.open(asset_path) as image:
            assert image.size == (960, 1280)
            image.load()
