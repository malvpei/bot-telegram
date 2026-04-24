from dataclasses import replace
from pathlib import Path
import shutil
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.instagram import (
    InstagramCollector,
    _feed_item_has_image,
    _source_id_from_local_path,
    extract_usernames,
    parse_instagram_username,
)


def test_parse_instagram_username_variants() -> None:
    assert parse_instagram_username("https://www.instagram.com/usuario/") == "usuario"
    assert parse_instagram_username("instagram.com/usuario?hl=es") == "usuario"
    assert parse_instagram_username("@usuario.prueba") == "usuario.prueba"
    assert parse_instagram_username("usuario_prueba") == "usuario_prueba"
    assert parse_instagram_username("https://www.instagram.com/p/abc123/") is None


def test_extract_usernames_deduplicates() -> None:
    usernames = extract_usernames(
        [
            "https://instagram.com/usuario1",
            "@usuario1",
            "usuario2",
        ],
        limit=5,
    )
    assert usernames == ["usuario1", "usuario2"]


def test_feed_item_has_image_ignores_videos_and_accepts_carousel_images() -> None:
    image_candidate = {"image_versions2": {"candidates": [{"url": "https://cdn/image.jpg"}]}}

    assert _feed_item_has_image({"media_type": 2, **image_candidate}) is False
    assert _feed_item_has_image({"media_type": 1, **image_candidate}) is True
    assert _feed_item_has_image(
        {
            "media_type": 8,
            "carousel_media": [
                {"media_type": 2, **image_candidate},
                {"media_type": 1, **image_candidate},
            ],
        }
    ) is True


def test_collector_rebuilds_catalog_from_local_account_folder() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"instagram-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        downloads_dir = root / "downloads"
        account_dir = downloads_dir / "alpha"
        account_dir.mkdir(parents=True)
        image_path = account_dir / "POST123_0.jpg"
        Image.new("RGB", (64, 64), (100, 120, 140)).save(image_path)
        settings = replace(
            get_settings(),
            data_dir=root,
            downloads_dir=downloads_dir,
            account_cache_ttl_hours=0,
        )
        collector = InstagramCollector(settings)

        media = collector.collect_one("alpha")

        assert len(media) == 1
        assert media[0].source_account == "alpha"
        assert media[0].source_id == "alpha:POST123:0"
        assert media[0].local_path == image_path
        assert (account_dir / "meta.json").exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_source_id_from_arbitrary_local_file_is_stable() -> None:
    assert (
        _source_id_from_local_path("alpha", Path("manual_photo.jpg"))
        == "alpha:local:manual_photo"
    )
