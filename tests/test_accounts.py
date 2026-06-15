from pathlib import Path

from app.accounts import load_accounts, normalize_account, remove_account


def test_remove_account_deletes_matching_username_variants(tmp_path: Path):
    accounts_path = tmp_path / "accounts.txt"
    accounts_path.write_text(
        "\n".join(
            [
                "# hombres",
                "@Alpha",
                "https://www.instagram.com/beta/ # keep",
                "instagram.com/alpha/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    removed = remove_account(accounts_path, "alpha")

    assert removed == 2
    assert load_accounts(accounts_path) == ["https://www.instagram.com/beta/"]


def test_normalize_account_accepts_urls_and_usernames():
    assert normalize_account("@Alpha") == "alpha"
    assert normalize_account("instagram.com/Beta/") == "beta"
    assert normalize_account("https://www.instagram.com/gamma/?hl=es") == "gamma"
