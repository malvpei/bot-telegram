from dataclasses import replace
import json
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


def test_collector_local_folder_limits_posts_not_images() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "_test_tmp"
        / f"instagram-{uuid4().hex}"
    )
    root.mkdir(parents=True)
    try:
        downloads_dir = root / "downloads"
        account_dir = downloads_dir / "alpha"
        account_dir.mkdir(parents=True)
        for post in ("POST1", "POST2", "POST3"):
            for index in range(3):
                image_path = account_dir / f"{post}_{index}.jpg"
                Image.new("RGB", (64, 64), (100, 120, 140)).save(image_path)
        settings = replace(
            get_settings(),
            data_dir=root,
            downloads_dir=downloads_dir,
            max_posts_per_account=2,
            account_cache_ttl_hours=0,
        )
        collector = InstagramCollector(settings)

        media = collector.collect_one("alpha")

        assert len(media) == 6
        assert {item.source_id.split(":")[1] for item in media} == {"POST1", "POST2"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_collector_cache_limits_posts_not_images() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "_test_tmp"
        / f"instagram-{uuid4().hex}"
    )
    root.mkdir(parents=True)
    try:
        downloads_dir = root / "downloads"
        account_dir = downloads_dir / "alpha"
        account_dir.mkdir(parents=True)
        settings = replace(
            get_settings(),
            data_dir=root,
            downloads_dir=downloads_dir,
            max_posts_per_account=2,
            account_cache_ttl_hours=0,
        )
        collector = InstagramCollector(settings)
        items = []
        for post in ("POST1", "POST2", "POST3"):
            for index in range(3):
                image_path = account_dir / f"{post}_{index}.jpg"
                Image.new("RGB", (64, 64), (100, 120, 140)).save(image_path)
                items.append(
                    {
                        "source_id": f"alpha:{post}:{index}",
                        "local_path": str(image_path),
                        "permalink": f"https://www.instagram.com/p/{post}/",
                        "caption": post,
                        "width": 64,
                        "height": 64,
                        "created_at": "local",
                    }
                )
        (account_dir / "meta.json").write_text(
            json.dumps({"cache_version": 3, "items": items}),
            encoding="utf-8",
        )

        media = collector.collect_one("alpha")

        assert len(media) == 6
        assert {item.source_id.split(":")[1] for item in media} == {"POST1", "POST2"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_collector_repairs_truncated_cache_from_local_folder() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "_test_tmp"
        / f"instagram-{uuid4().hex}"
    )
    root.mkdir(parents=True)
    try:
        downloads_dir = root / "downloads"
        account_dir = downloads_dir / "alpha"
        account_dir.mkdir(parents=True)
        all_items = []
        for post in ("POST1", "POST2"):
            for index in range(3):
                image_path = account_dir / f"{post}_{index}.jpg"
                Image.new("RGB", (64, 64), (100, 120, 140)).save(image_path)
                all_items.append(
                    {
                        "source_id": f"alpha:{post}:{index}",
                        "local_path": str(image_path),
                        "permalink": f"https://www.instagram.com/p/{post}/",
                        "caption": post,
                        "width": 64,
                        "height": 64,
                        "created_at": "local",
                    }
                )
        (account_dir / "meta.json").write_text(
            json.dumps({"cache_version": 3, "items": all_items[:2]}),
            encoding="utf-8",
        )
        settings = replace(
            get_settings(),
            data_dir=root,
            downloads_dir=downloads_dir,
            max_posts_per_account=2,
            account_cache_ttl_hours=0,
        )
        collector = InstagramCollector(settings)

        media = collector.collect_one("alpha")

        assert len(media) == 6
        assert {item.source_id for item in media} == {
            f"alpha:{post}:{index}"
            for post in ("POST1", "POST2")
            for index in range(3)
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_collector_local_folder_treats_manual_files_as_separate_posts() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "_test_tmp"
        / f"instagram-{uuid4().hex}"
    )
    root.mkdir(parents=True)
    try:
        downloads_dir = root / "downloads"
        account_dir = downloads_dir / "alpha"
        account_dir.mkdir(parents=True)
        for name in ("manual_a.jpg", "manual_b.jpg", "manual_c.jpg"):
            Image.new("RGB", (64, 64), (100, 120, 140)).save(account_dir / name)
        settings = replace(
            get_settings(),
            data_dir=root,
            downloads_dir=downloads_dir,
            max_posts_per_account=2,
            account_cache_ttl_hours=0,
        )
        collector = InstagramCollector(settings)

        media = collector.collect_one("alpha")

        assert len(media) == 2
        assert [item.source_id for item in media] == [
            "alpha:local:manual_a",
            "alpha:local:manual_b",
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_source_id_from_arbitrary_local_file_is_stable() -> None:
    assert (
        _source_id_from_local_path("alpha", Path("manual_photo.jpg"))
        == "alpha:local:manual_photo"
    )
