from app.instagram import extract_usernames, parse_instagram_username


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

