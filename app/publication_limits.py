"""Shared limits for publication titles, independent of video format."""

import unicodedata


MAX_PUBLICATION_TITLE_LENGTH = 90


def limit_publication_title(title: str) -> str:
    """Keep titles on one line and use whole words when a legacy title is long."""
    title = unicodedata.normalize("NFC", " ".join(title.split()))
    if len(title) <= MAX_PUBLICATION_TITLE_LENGTH:
        return title
    clipped = title[:MAX_PUBLICATION_TITLE_LENGTH]
    if not title[MAX_PUBLICATION_TITLE_LENGTH].isspace() and " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:-–—")
