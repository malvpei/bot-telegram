from app.instagram import _feed_item_has_image, extract_usernames, parse_instagram_username


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
