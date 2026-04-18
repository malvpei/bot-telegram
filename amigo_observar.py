from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests import HTTPError
from PIL import Image


ACCOUNTS_FILE = Path("collaborator_accounts.txt")
OUTPUT_ROOT = Path("collaborator_media")
STATE_FILE = Path("automation_state/collaborator_media_refresh.json")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
INSTAGRAM_APP_ID = "936619743392459"
INSTAGRAM_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
FEED_PAGE_SIZE = 12
REQUEST_TIMEOUT = 60
DEFAULT_POSTS_PER_ACCOUNT = 100
DEFAULT_MAX_IMAGES_PER_POST = 4
NORMALIZATION_PROFILE_VERSION = 1
FETCH_RETRY_ATTEMPTS = 3
CANONICAL_DOWNLOAD_APP_SEGMENTS = (
    (b"\xff\xe0", b"\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"),
    (
        b"\xff\xed",
        bytes.fromhex(
            "007c50686f746f73686f7020332e30003842494d04040000000000601c0228005a46424d44323330303039336430323030303064393730303030303961393430303030376162373030303064373636303130306533643730313030373036643032303064346630303230303736346130333030343965663033303000"
        ),
    ),
)
CANONICAL_DOWNLOAD_QTABLES = [
    [
        5, 6, 11, 11, 13, 14, 15, 16, 6, 8, 11, 11, 14, 13, 16, 16,
        11, 11, 11, 13, 14, 16, 15, 17, 11, 11, 13, 14, 17, 19, 19, 19,
        13, 14, 14, 17, 18, 20, 22, 22, 14, 13, 16, 19, 20, 22, 21, 25,
        15, 16, 15, 19, 22, 21, 22, 22, 16, 16, 17, 19, 22, 25, 22, 18,
    ],
    [
        5, 5, 10, 8, 11, 10, 12, 13, 5, 7, 9, 8, 10, 9, 11, 12,
        10, 9, 10, 9, 10, 10, 11, 12, 8, 8, 9, 9, 11, 11, 12, 13,
        11, 10, 10, 11, 8, 13, 10, 12, 10, 9, 10, 11, 13, 11, 13, 19,
        12, 11, 11, 12, 10, 13, 20, 19, 13, 12, 12, 13, 12, 19, 19, 156,
    ],
]


def username_from_url(url: str) -> str:
    path = urlparse(url.strip()).path.strip("/")
    if not path:
        raise ValueError(f"Could not parse Instagram username from {url!r}")
    return path.split("/")[0]


def read_accounts(path: Path) -> list[str]:
    return [username_from_url(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def image_count(directory: Path) -> int:
    return sum(1 for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_feed_page(
    session: requests.Session,
    username: str,
    *,
    count: int,
    max_id: str | None = None,
) -> dict:
    url = f"https://www.instagram.com/api/v1/feed/user/{username}/username/"
    params = {"count": count}
    if max_id:
        params["max_id"] = max_id
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"Instagram feed returned unexpected status for {username}: {payload.get('status')!r}")
    return payload


def fetch_feed_page_with_retry(
    session: requests.Session,
    username: str,
    *,
    count: int,
    max_id: str | None = None,
) -> tuple[dict, requests.Session]:
    last_error: Exception | None = None
    active_session = session
    for attempt in range(1, FETCH_RETRY_ATTEMPTS + 1):
        try:
            return fetch_feed_page(active_session, username, count=count, max_id=max_id), active_session
        except HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in {401, 429} or attempt == FETCH_RETRY_ATTEMPTS:
                raise
            active_session = build_session()
            prepare_instagram_session(active_session, username)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == FETCH_RETRY_ATTEMPTS:
                raise
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Failed to fetch Instagram feed for {username}.")


def best_image_url(media: dict) -> str | None:
    candidates = media.get("image_versions2", {}).get("candidates", [])
    if not candidates:
        return None
    return candidates[0].get("url")


def image_targets(item: dict, output_dir: Path, max_images_per_post: int) -> list[tuple[Path, str, datetime]]:
    taken_at = datetime.fromtimestamp(item["taken_at"], tz=timezone.utc)
    stamp = taken_at.strftime("%Y-%m-%d_%H-%M-%S_UTC")
    stem = output_dir / stamp

    if item.get("media_type") == 8:
        targets: list[tuple[Path, str, datetime]] = []
        for index, media in enumerate(item.get("carousel_media", []), start=1):
            if media.get("media_type") != 1:
                continue
            image_url = best_image_url(media)
            if not image_url:
                continue
            targets.append((stem.with_name(f"{stem.name}_{index}.jpg"), image_url, taken_at))
            if len(targets) >= max_images_per_post:
                break
        return targets

    if item.get("media_type") != 1:
        return []

    image_url = best_image_url(item)
    if not image_url:
        return []
    return [(stem.with_suffix(".jpg"), image_url, taken_at)]


def last_full_refresh(state: dict) -> datetime | None:
    last_refresh_raw = state.get("last_full_refresh_utc") or state.get("last_refresh_utc")
    if not last_refresh_raw:
        return None
    try:
        last_refresh = datetime.fromisoformat(last_refresh_raw)
    except ValueError:
        return None
    if last_refresh.tzinfo is None:
        last_refresh = last_refresh.replace(tzinfo=timezone.utc)
    return last_refresh


def sync_plan(
    accounts: list[str],
    posts_per_account: int,
    max_images_per_post: int,
    stale_after_days: int,
) -> tuple[bool, list[str], list[str], str]:
    state = load_state()
    previous_accounts = state.get("accounts", [])
    previous_account_set = set(previous_accounts)
    current_account_set = set(accounts)
    if state.get("normalization_profile_version") != NORMALIZATION_PROFILE_VERSION:
        return True, accounts, sorted(previous_account_set - current_account_set), "normalization profile changed"
    legacy_images_per_account = state.get("images_per_account")
    if legacy_images_per_account is not None:
        return True, accounts, sorted(previous_account_set - current_account_set), "legacy image-count mode detected"
    if state.get("posts_per_account") != posts_per_account:
        return True, accounts, sorted(previous_account_set - current_account_set), "post limit changed"
    if state.get("max_images_per_post") != max_images_per_post:
        return True, accounts, sorted(previous_account_set - current_account_set), "per-post image cap changed"

    last_refresh = last_full_refresh(state)
    if last_refresh is None:
        return True, accounts, sorted(previous_account_set - current_account_set), "no valid full refresh timestamp"

    refresh_deadline = last_refresh + timedelta(days=stale_after_days)
    if datetime.now(timezone.utc) >= refresh_deadline:
        return True, accounts, sorted(previous_account_set - current_account_set), f"last full refresh is older than {stale_after_days} days"

    recorded_counts = state.get("counts", {})
    accounts_to_sync: list[str] = []
    for username in accounts:
        account_dir = OUTPUT_ROOT / username
        if not account_dir.exists():
            accounts_to_sync.append(username)
            continue
        current_count = image_count(account_dir)
        recorded_count = recorded_counts.get(username)
        if recorded_count is None:
            accounts_to_sync.append(username)
            continue
        if current_count != recorded_count:
            accounts_to_sync.append(username)
            continue
        if username not in previous_account_set:
            accounts_to_sync.append(username)

    accounts_to_remove = sorted(previous_account_set - current_account_set)
    if accounts_to_sync or accounts_to_remove:
        added_accounts = [username for username in accounts if username not in previous_account_set]
        reasons: list[str] = []
        if added_accounts:
            reasons.append(f"new collaborators added: {', '.join(added_accounts)}")
        missing_accounts = [username for username in accounts_to_sync if not (OUTPUT_ROOT / username).exists()]
        if missing_accounts:
            reasons.append(f"missing media folder: {', '.join(missing_accounts)}")
        mismatched_accounts = [username for username in accounts_to_sync if state.get("counts", {}).get(username) is not None]
        if mismatched_accounts:
            reasons.append(f"media count changed: {', '.join(mismatched_accounts)}")
        if accounts_to_remove:
            reasons.append(f"removed collaborators: {', '.join(accounts_to_remove)}")
        return False, sorted(set(accounts_to_sync)), accounts_to_remove, "; ".join(reasons)

    return False, [], [], "cache is fresh"


def download_file(
    session: requests.Session,
    target_path: Path,
    url: str,
    taken_at: datetime,
) -> None:
    response = session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    with target_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                handle.write(chunk)
    normalize_downloaded_image(target_path)
    timestamp = taken_at.timestamp()
    os.utime(target_path, (timestamp, timestamp))


def parse_jpeg_structure(data: bytes) -> tuple[list[tuple[bytes, bytes]], bytes]:
    if data[:2] != b"\xff\xd8":
        raise ValueError("Not a JPEG file.")
    index = 2
    segments: list[tuple[bytes, bytes]] = []
    while index < len(data):
        if data[index] != 0xFF:
            raise ValueError("Invalid JPEG marker stream.")
        marker = data[index : index + 2]
        if marker == b"\xff\xd9":
            return segments, marker
        index += 2
        if marker == b"\xff\xda":
            size = int.from_bytes(data[index : index + 2], "big")
            payload = data[index : index + size]
            remainder = marker + payload + data[index + size :]
            return segments, remainder
        size = int.from_bytes(data[index : index + 2], "big")
        payload = data[index : index + size]
        segments.append((marker, payload))
        index += size
    raise ValueError("Missing JPEG scan data.")


def rewrite_jpeg_to_canonical_download_profile(path: Path) -> None:
    data = path.read_bytes()
    segments, remainder = parse_jpeg_structure(data)
    other_segments = [
        (marker, payload)
        for marker, payload in segments
        if not (0xE0 <= marker[1] <= 0xEF) and marker not in {b"\xff\xdb", b"\xff\xc4"}
    ]
    dqt_payloads = [payload[2:] for marker, payload in segments if marker == b"\xff\xdb"]
    dht_payloads = [payload[2:] for marker, payload in segments if marker == b"\xff\xc4"]

    rebuilt = bytearray(b"\xff\xd8")
    for marker, payload in CANONICAL_DOWNLOAD_APP_SEGMENTS:
        rebuilt.extend(marker)
        rebuilt.extend(payload)
    if dqt_payloads:
        combined = b"".join(dqt_payloads)
        rebuilt.extend(b"\xff\xdb")
        rebuilt.extend((len(combined) + 2).to_bytes(2, "big"))
        rebuilt.extend(combined)
    for marker, payload in other_segments:
        rebuilt.extend(marker)
        rebuilt.extend(payload)
    if dht_payloads:
        combined = b"".join(dht_payloads)
        rebuilt.extend(b"\xff\xc4")
        rebuilt.extend((len(combined) + 2).to_bytes(2, "big"))
        rebuilt.extend(combined)
    rebuilt.extend(remainder)
    path.write_bytes(bytes(rebuilt))


def normalize_downloaded_image(path: Path) -> None:
    image = Image.open(path).convert("RGB")
    image.save(
        path,
        format="JPEG",
        qtables=CANONICAL_DOWNLOAD_QTABLES,
        optimize=True,
        progressive=True,
    )
    rewrite_jpeg_to_canonical_download_profile(path)


def download_profile(
    username: str,
    posts_limit: int,
    max_images_per_post: int,
    output_root: Path,
) -> int:
    output_dir = output_root / username
    output_dir.mkdir(parents=True, exist_ok=True)
    download_session = build_session()
    feed_session = build_session()
    prepare_instagram_session(feed_session, username)

    downloaded = 0
    collected_posts = 0
    max_id: str | None = None
    while collected_posts < posts_limit:
        payload, feed_session = fetch_feed_page_with_retry(feed_session, username, count=FEED_PAGE_SIZE, max_id=max_id)
        items = payload.get("items", [])
        if not items:
            break
        for item in items:
            targets = image_targets(item, output_dir, max_images_per_post)
            if not targets:
                continue
            collected_posts += 1
            for target_path, url, taken_at in targets:
                download_file(download_session, target_path, url, taken_at)
                downloaded += 1
            if collected_posts >= posts_limit:
                return downloaded
        if not payload.get("more_available"):
            break
        max_id = payload.get("next_max_id")
        if not max_id:
            break
    return downloaded


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": INSTAGRAM_USER_AGENT,
            "X-IG-App-ID": INSTAGRAM_APP_ID,
            "Referer": "https://www.instagram.com/",
        }
    )
    return session


def prepare_instagram_session(session: requests.Session, username: str) -> None:
    response = session.get(f"https://www.instagram.com/{username}/", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    csrf_token = session.cookies.get("csrftoken")
    if csrf_token:
        session.headers["X-CSRFToken"] = csrf_token


def replace_existing_media(accounts: list[str], staging_root: Path) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for username in accounts:
        destination = OUTPUT_ROOT / username
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staging_root / username), str(destination))


def remove_existing_media(accounts: list[str]) -> None:
    for username in accounts:
        destination = OUTPUT_ROOT / username
        if destination.exists():
            shutil.rmtree(destination)


def current_counts(accounts: list[str]) -> dict[str, int]:
    return {username: image_count(OUTPUT_ROOT / username) for username in accounts if (OUTPUT_ROOT / username).exists()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-per-account", type=int, help="Legacy alias for the old image-count mode.")
    parser.add_argument("--posts-per-account", type=int, default=DEFAULT_POSTS_PER_ACCOUNT)
    parser.add_argument("--max-images-per-post", type=int, default=DEFAULT_MAX_IMAGES_PER_POST)
    parser.add_argument("--stale-after-days", type=int, default=5)
    parser.add_argument("--refresh-if-stale", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    accounts = read_accounts(ACCOUNTS_FILE)
    posts_per_account = args.posts_per_account
    max_images_per_post = args.max_images_per_post

    if args.images_per_account is not None:
        posts_per_account = args.images_per_account
        max_images_per_post = 1

    if args.force_refresh:
        full_refresh = True
        accounts_to_sync = accounts
        accounts_to_remove = sorted(set(load_state().get("accounts", [])) - set(accounts))
        reason = "force refresh requested"
    elif args.refresh_if_stale:
        full_refresh, accounts_to_sync, accounts_to_remove, reason = sync_plan(
            accounts,
            posts_per_account,
            max_images_per_post,
            args.stale_after_days,
        )
    else:
        full_refresh = True
        accounts_to_sync = accounts
        accounts_to_remove = sorted(set(load_state().get("accounts", [])) - set(accounts))
        reason = "manual refresh requested"

    if not full_refresh and not accounts_to_sync and not accounts_to_remove:
        print(f"Collaborator media refresh skipped: {reason}.")
        return

    if full_refresh:
        print(f"Refreshing collaborator media: {reason}.")
    else:
        print(f"Syncing collaborator media incrementally: {reason}.")

    sync_counts: dict[str, int] = {}
    staging_root = Path(tempfile.mkdtemp(prefix="collaborator-media-refresh-", dir="."))
    try:
        for username in accounts_to_sync:
            print(f"Downloading latest images for {username}...")
            count = download_profile(username, posts_per_account, max_images_per_post, staging_root)
            sync_counts[username] = count
            print(f"{username}: downloaded {count} images")

        replace_existing_media(accounts_to_sync, staging_root)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    if accounts_to_remove:
        print(f"Removing media for collaborators no longer in the list: {', '.join(accounts_to_remove)}")
        remove_existing_media(accounts_to_remove)

    now = datetime.now(timezone.utc).isoformat()
    state = load_state()
    last_full_refresh_utc = now if full_refresh else state.get("last_full_refresh_utc") or state.get("last_refresh_utc")
    save_state(
        {
            "last_sync_utc": now,
            "last_full_refresh_utc": last_full_refresh_utc,
            "last_refresh_utc": last_full_refresh_utc,
            "normalization_profile_version": NORMALIZATION_PROFILE_VERSION,
            "accounts": accounts,
            "posts_per_account": posts_per_account,
            "max_images_per_post": max_images_per_post,
            "stale_after_days": args.stale_after_days,
            "counts": current_counts(accounts),
        }
    )


if __name__ == "__main__":
    main()
