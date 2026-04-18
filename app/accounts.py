from __future__ import annotations

from pathlib import Path


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
