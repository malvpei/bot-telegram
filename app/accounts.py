from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED_INSTAGRAM_PATHS = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "tv",
    "accounts",
    "about",
}


class AccountsFileError(RuntimeError):
    """Raised when the accounts file is missing or has no usable entries."""


def load_accounts(path: Path) -> list[str]:
    """Read one Instagram URL/username per line.

    Blank lines and anything after a ``#`` are ignored. Duplicates are kept in
    the order they first appear so the caller can decide the priority.
    """

    if not path.exists():
        raise AccountsFileError(
            f"No encuentro el archivo de cuentas en {path}. "
            "Crea el archivo y añade una cuenta por línea."
        )

    entries: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(line)

    if not entries:
        raise AccountsFileError(
            f"El archivo de cuentas {path} está vacío o solo tiene comentarios."
        )
    return entries


def remove_account(path: Path, account: str) -> int:
    """Remove every line matching an Instagram account from an accounts file."""

    if not path.exists():
        raise AccountsFileError(
            f"No encuentro el archivo de cuentas en {path}. "
            "Crea el archivo y añade una cuenta por línea."
        )

    target = normalize_account(account)
    if not target:
        return 0

    removed = 0
    kept_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        line = raw_line.split("#", 1)[0].strip()
        if line and normalize_account(line) == target:
            removed += 1
            continue
        kept_lines.append(raw_line)

    if removed:
        path.write_text("".join(kept_lines), encoding="utf-8")
    return removed


def normalize_account(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    if cleaned.startswith("@"):
        cleaned = cleaned[1:]

    if "instagram.com" not in cleaned and USERNAME_RE.fullmatch(cleaned):
        return cleaned.lower()

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return None
    if "instagram.com" not in parsed.netloc.lower():
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    username = parts[0]
    if username.lower() in RESERVED_INSTAGRAM_PATHS:
        return None
    if USERNAME_RE.fullmatch(username):
        return username.lower()
    return None
