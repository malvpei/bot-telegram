from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import instaloader
import requests
from instaloader.exceptions import (
    BadCredentialsException,
    ConnectionException,
    LoginException,
    LoginRequiredException,
    PrivateProfileNotFollowedException,
    ProfileNotExistsException,
    QueryReturnedBadRequestException,
    QueryReturnedNotFoundException,
    TwoFactorAuthRequiredException,
)
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.models import MediaCandidate


LOGGER = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED_PATHS = {"p", "reel", "reels", "stories", "explore", "tv", "accounts", "about"}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "198387",
    "X-IG-WWW-Claim": "0",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}


class InstagramCollectorError(RuntimeError):
    """Raised for any user-visible Instagram collection failure."""


class InstagramCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
            user_agent=DEFAULT_USER_AGENT,
        )
        self._http_session = requests.Session()
        self._http_session.headers.update(DEFAULT_HEADERS)
        self._logged_in = False
        self._inject_ig_app_id()

    def _probe_rate_limit(self, username: str) -> None:
        # Instaloader masks 429 as "profile does not exist". Detect it here
        # so the user sees a meaningful error and we fail fast.
        try:
            session = self.loader.context._session  # type: ignore[attr-defined]
        except AttributeError:
            return
        try:
            response = session.get(
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                timeout=15,
            )
        except requests.RequestException:
            return
        if response.status_code == 429:
            raise InstagramCollectorError(
                "Instagram está aplicando rate limit a esta cuenta o IP "
                "(HTTP 429). Espera 30-60 min, usa otra cuenta en "
                "INSTAGRAM_USERNAME, o prueba desde otra IP (no VPN / "
                "datacenter)."
            )
        if response.status_code == 401:
            raise InstagramCollectorError(
                "La sesión de Instagram caducó (HTTP 401). Borra el archivo "
                "en INSTAGRAM_SESSION_PATH y vuelve a generar la sesión."
            )

    def _inject_ig_app_id(self) -> None:
        # Instagram rejects GraphQL profile lookups as "not found" when the
        # X-IG-App-ID header is missing. Inject it into instaloader's
        # internal session so Profile.from_username actually resolves.
        try:
            session = self.loader.context._session  # type: ignore[attr-defined]
        except AttributeError:
            return
        session.headers.update({
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.instagram.com/",
        })

    def _ensure_login(self) -> None:
        # Lazy login: don't blow up the bot at startup if Instagram refuses.
        if self._logged_in:
            return
        username = self.settings.instagram_username
        password = self.settings.instagram_password
        if not username:
            self._logged_in = True
            return

        session_path = self.settings.instagram_session_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_file = session_path / username if session_path.is_dir() or not session_path.suffix else session_path

        # Try to reuse a saved session before re-authenticating.
        if session_file.exists():
            try:
                self.loader.load_session_from_file(username, str(session_file))
                self._inject_ig_app_id()
                LOGGER.info("Reused stored Instagram session for @%s", username)
                self._logged_in = True
                return
            except Exception as error:  # pragma: no cover - depends on env
                LOGGER.warning("Stored Instagram session unusable, re-login: %s", error)

        if not password:
            raise InstagramCollectorError(
                "INSTAGRAM_USERNAME está definido pero falta INSTAGRAM_PASSWORD "
                "o un session file en INSTAGRAM_SESSION_PATH."
            )

        try:
            self.loader.login(username, password)
        except TwoFactorAuthRequiredException as error:
            raise InstagramCollectorError(
                "Instagram pide 2FA. Genera un session file localmente con "
                "instaloader --login y colócalo en INSTAGRAM_SESSION_PATH."
            ) from error
        except BadCredentialsException as error:
            raise InstagramCollectorError(
                "Credenciales de Instagram inválidas."
            ) from error
        except ConnectionException as error:
            raise InstagramCollectorError(
                f"Instagram bloqueó el login: {error}"
            ) from error
        except LoginException as error:
            raise InstagramCollectorError(
                "Instagram rechazó el login desde este entorno "
                f"({error}). Genera un session file localmente con "
                f"`instaloader --login {username}` y súbelo a "
                "INSTAGRAM_SESSION_PATH; el bot lo reutilizará sin volver "
                "a autenticar."
            ) from error

        try:
            session_file.parent.mkdir(parents=True, exist_ok=True)
            self.loader.save_session_to_file(str(session_file))
            self._inject_ig_app_id()
            LOGGER.info("Saved Instagram session to %s", session_file)
        except Exception as error:  # pragma: no cover
            LOGGER.warning("Could not persist Instagram session: %s", error)
        self._logged_in = True

    def collect_from_inputs(self, account_inputs: list[str]) -> dict[str, list[MediaCandidate]]:
        usernames = extract_usernames(account_inputs, self.settings.max_urls_per_job)
        if not usernames:
            raise InstagramCollectorError(
                "No encontré URLs o nombres de usuario válidos de Instagram."
            )

        # Defer login until we actually need to fetch a profile.
        self._ensure_login()

        catalog: dict[str, list[MediaCandidate]] = {}
        errors: list[str] = []
        for index, username in enumerate(usernames):
            if index > 0:
                time.sleep(1.5)
            try:
                catalog[username] = self._collect_account(username)
            except InstagramCollectorError as error:
                errors.append(f"@{username}: {error}")
            except (
                ProfileNotExistsException,
                PrivateProfileNotFollowedException,
                LoginRequiredException,
                QueryReturnedNotFoundException,
                QueryReturnedBadRequestException,
                ConnectionException,
            ) as error:
                errors.append(f"@{username}: {error}")
            except Exception as error:  # last-resort safety net
                LOGGER.exception("Unexpected error collecting @%s", username)
                errors.append(f"@{username}: {error}")

        if not catalog:
            detail = "\n".join(errors) if errors else "Sin detalles adicionales."
            raise InstagramCollectorError(
                f"No pude descargar ninguna cuenta válida.\n{detail}"
            )
        return catalog

    def collect_one(self, username: str) -> list[MediaCandidate]:
        """Fetch a single account. Used by the random-account picker."""
        cached = self._load_cached_account(username)
        if cached is not None:
            LOGGER.info("Using cached images for @%s (%d items)", username, len(cached))
            return cached

        if not self.settings.instagram_username:
            items = self._collect_account_anonymous(username)
            self._save_account_cache(username, items)
            return items

        self._ensure_login()
        return self._collect_account(username)

    def _load_browser_cookies(self) -> None:
        # Reads Instagram cookies from installed browsers (Chrome, Edge,
        # Firefox, Brave). If the user is logged into IG in any of them,
        # we pick up their session cookies and the anonymous path becomes
        # an authenticated one — no username/password required in .env.
        try:
            import browser_cookie3
        except ImportError:
            LOGGER.warning("browser-cookie3 not installed; skipping browser cookie load.")
            return
        loaders = [
            ("chrome", getattr(browser_cookie3, "chrome", None)),
            ("edge", getattr(browser_cookie3, "edge", None)),
            ("brave", getattr(browser_cookie3, "brave", None)),
            ("firefox", getattr(browser_cookie3, "firefox", None)),
            ("opera", getattr(browser_cookie3, "opera", None)),
        ]
        for name, loader in loaders:
            if loader is None:
                continue
            try:
                jar = loader(domain_name="instagram.com")
            except Exception as error:  # pragma: no cover - platform specific
                LOGGER.debug("browser %s unavailable: %s", name, error)
                continue
            sessionid = None
            for cookie in jar:
                if "instagram.com" not in (cookie.domain or ""):
                    continue
                self._http_session.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain
                )
                if cookie.name == "sessionid":
                    sessionid = cookie.value
            if sessionid:
                LOGGER.info("Loaded Instagram cookies from %s", name)
                return
        LOGGER.warning(
            "No se encontraron cookies de Instagram en ningún navegador. "
            "Abre Chrome/Edge/Firefox, inicia sesión en instagram.com y "
            "relanza el bot."
        )

    def _collect_account_anonymous(self, username: str) -> list[MediaCandidate]:
        self._bootstrap_anonymous_session()
        user = self._fetch_user_json(username)
        if user is None:
            raise InstagramCollectorError(f"La cuenta @{username} no existe.")
        if user.get("is_private"):
            raise InstagramCollectorError(
                f"La cuenta @{username} es privada."
            )

        timeline = (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []
        account_dir = self.settings.downloads_dir / username
        account_dir.mkdir(parents=True, exist_ok=True)

        items: list[MediaCandidate] = []
        for edge in timeline[: self.settings.max_posts_per_account]:
            node = edge.get("node") or {}
            shortcode = node.get("shortcode") or ""
            caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            caption = caption_edges[0]["node"]["text"] if caption_edges else ""
            created_at = _iso_from_ts(node.get("taken_at_timestamp"))
            for node_index, image_url in enumerate(_iter_image_urls(node)):
                file_stem = f"{shortcode}_{node_index}"
                target_path = account_dir / f"{file_stem}.jpg"
                if not target_path.exists() or target_path.stat().st_size == 0:
                    if not self._download_image(image_url, target_path):
                        continue
                try:
                    width, height = read_image_size(target_path)
                except (UnidentifiedImageError, OSError):
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                    continue
                items.append(
                    MediaCandidate(
                        source_account=username,
                        source_id=f"{username}:{shortcode}:{node_index}",
                        local_path=target_path,
                        permalink=f"https://www.instagram.com/p/{shortcode}/",
                        caption=caption.strip(),
                        width=width,
                        height=height,
                        created_at=created_at,
                    )
                )

        if not items:
            raise InstagramCollectorError(
                f"La cuenta @{username} no tiene imágenes utilizables."
            )
        return items

    def _fetch_user_json(self, username: str) -> dict:
        # Try a list of public endpoints until one returns valid user data.
        # IG has closed / hardened them progressively, so we keep fallbacks.
        endpoints = [
            (
                "https://i.instagram.com/api/v1/users/web_profile_info/"
                f"?username={username}",
                "json_api",
            ),
            (
                "https://www.instagram.com/api/v1/users/web_profile_info/"
                f"?username={username}",
                "json_api",
            ),
            (f"https://www.instagram.com/{username}/", "html_embed"),
        ]
        last_status: int | None = None
        last_body: str = ""
        for url, kind in endpoints:
            try:
                response = self._http_session.get(url, timeout=20, allow_redirects=True)
            except requests.RequestException as error:
                LOGGER.warning("HTTP error on %s: %s", url, error)
                continue
            last_status = response.status_code
            body_text = response.text or ""
            last_body = body_text[:500]
            LOGGER.info(
                "IG fetch @%s via %s -> HTTP %s (len=%d, final=%s)",
                username,
                kind,
                response.status_code,
                len(body_text),
                response.url,
            )
            if response.status_code == 404:
                raise InstagramCollectorError(f"La cuenta @{username} no existe.")
            if response.status_code != 200:
                continue
            if "/accounts/login" in str(response.url) or "loginForm" in body_text:
                LOGGER.info("IG redirected @%s to login page; need valid cookies", username)
                continue
            if kind == "json_api":
                try:
                    user = response.json()["data"]["user"]
                except (ValueError, KeyError, TypeError):
                    continue
                if user:
                    return user
            elif kind == "html_embed":
                user = _extract_user_from_html(body_text)
                if user:
                    LOGGER.info(
                        "Extracted %d posts from HTML for @%s",
                        len(user.get("edge_owner_to_timeline_media", {}).get("edges", [])),
                        username,
                    )
                    return user
                LOGGER.info(
                    "HTML parse failed for @%s (first 400 chars): %r",
                    username,
                    body_text[:400],
                )
        if last_status == 429:
            raise InstagramCollectorError(
                f"Rate limit para @{username} (HTTP 429). Usa cookies de "
                "una cuenta IG nueva o cambia de IP."
            )
        if last_status == 401:
            raise InstagramCollectorError(
                f"IG exige login para @{username} (HTTP 401). Añade cookies "
                "válidas en IG_SESSIONID/IG_DS_USER_ID/IG_CSRFTOKEN."
            )
        raise InstagramCollectorError(
            f"Ningún endpoint público devolvió datos para @{username} "
            f"(último HTTP {last_status}). Cuerpo: {last_body!r}"
        )

    def _bootstrap_anonymous_session(self) -> None:
        session = self._http_session
        env_loaded = self._load_env_cookies()
        if not env_loaded and not session.cookies.get("sessionid"):
            self._load_browser_cookies()
        if not session.cookies.get("mid") or not session.cookies.get("csrftoken"):
            self._warmup_session()
        csrftoken = session.cookies.get("csrftoken")
        if csrftoken:
            session.headers["X-CSRFToken"] = csrftoken

    def _warmup_session(self) -> None:
        # Fetch the IG homepage so the server sets the `mid`, `ig_did` and
        # fresh `csrftoken` cookies that real browsers carry. Without these
        # the subsequent API call looks like a scraper and gets 429/401.
        try:
            self._http_session.get("https://www.instagram.com/", timeout=15)
        except requests.RequestException as error:
            LOGGER.warning("Session warmup failed: %s", error)

    def _load_env_cookies(self) -> bool:
        sessionid = self.settings.ig_sessionid
        if not sessionid:
            return False
        for name, value in [
            ("sessionid", sessionid),
            ("ds_user_id", self.settings.ig_ds_user_id),
            ("csrftoken", self.settings.ig_csrftoken),
        ]:
            if value:
                self._http_session.cookies.set(name, value, domain=".instagram.com")
        LOGGER.info("Loaded Instagram cookies from .env")
        return True

    def _collect_account(self, username: str) -> list[MediaCandidate]:
        cached = self._load_cached_account(username)
        if cached is not None:
            LOGGER.info("Using cached images for @%s (%d items)", username, len(cached))
            return cached

        self._probe_rate_limit(username)
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
        except ProfileNotExistsException as error:
            raise InstagramCollectorError(
                f"La cuenta no existe (o IG devolvió 404 por rate limit): {error}"
            ) from error

        if profile.is_private and not profile.followed_by_viewer:
            raise InstagramCollectorError(
                f"La cuenta @{username} es privada y no se puede usar."
            )

        account_dir = self.settings.downloads_dir / username
        account_dir.mkdir(parents=True, exist_ok=True)

        media_items: list[MediaCandidate] = []
        try:
            for index, post in enumerate(profile.get_posts()):
                if index >= self.settings.max_posts_per_account:
                    break
                try:
                    media_items.extend(self._collect_post_media(username, post, account_dir))
                except Exception as error:
                    LOGGER.warning("Skipping post %s of @%s: %s", post.shortcode, username, error)
        except (ConnectionException, QueryReturnedBadRequestException) as error:
            if not media_items:
                raise InstagramCollectorError(
                    f"Instagram cortó la descarga de @{username}: {error}"
                ) from error
            LOGGER.warning("Partial download for @%s: %s", username, error)

        if not media_items:
            raise InstagramCollectorError(
                f"La cuenta @{username} no tiene imágenes utilizables."
            )
        self._save_account_cache(username, media_items)
        return media_items

    def _cache_path(self, username: str) -> Path:
        return self.settings.downloads_dir / username / "meta.json"

    def _load_cached_account(self, username: str) -> list[MediaCandidate] | None:
        cache_path = self._cache_path(username)
        if not cache_path.exists():
            return None
        ttl_hours = self.settings.account_cache_ttl_hours
        if ttl_hours > 0:
            age = time.time() - cache_path.stat().st_mtime
            if age > ttl_hours * 3600:
                return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        items: list[MediaCandidate] = []
        for raw in payload.get("items", []):
            local = Path(raw["local_path"])
            if not local.exists():
                continue
            items.append(
                MediaCandidate(
                    source_account=username,
                    source_id=raw["source_id"],
                    local_path=local,
                    permalink=raw.get("permalink", ""),
                    caption=raw.get("caption", ""),
                    width=int(raw.get("width", 0)),
                    height=int(raw.get("height", 0)),
                    created_at=raw.get("created_at", ""),
                )
            )
        return items if items else None

    def _save_account_cache(self, username: str, items: list[MediaCandidate]) -> None:
        cache_path = self._cache_path(username)
        payload = {
            "cached_at": time.time(),
            "items": [
                {
                    "source_id": item.source_id,
                    "local_path": str(item.local_path),
                    "permalink": item.permalink,
                    "caption": item.caption,
                    "width": item.width,
                    "height": item.height,
                    "created_at": item.created_at,
                }
                for item in items
            ],
        }
        try:
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as error:  # pragma: no cover
            LOGGER.warning("Could not write cache for @%s: %s", username, error)

    def _collect_post_media(
        self,
        username: str,
        post: instaloader.Post,
        account_dir: Path,
    ) -> list[MediaCandidate]:
        media: list[MediaCandidate] = []
        items = list(iter_post_images(post))
        for node_index, item in enumerate(items):
            file_stem = f"{post.shortcode}_{node_index}"
            target_path = account_dir / f"{file_stem}.jpg"
            if not target_path.exists() or target_path.stat().st_size == 0:
                if not self._download_image(item["url"], target_path):
                    continue
            try:
                width, height = read_image_size(target_path)
            except (UnidentifiedImageError, OSError):
                # Bad file on disk; remove and skip rather than poison the catalog.
                try:
                    target_path.unlink()
                except OSError:
                    pass
                continue
            media.append(
                MediaCandidate(
                    source_account=username,
                    source_id=f"{username}:{post.shortcode}:{node_index}",
                    local_path=target_path,
                    permalink=f"https://www.instagram.com/p/{post.shortcode}/",
                    caption=(post.caption or "").strip(),
                    width=width,
                    height=height,
                    created_at=post.date_utc.isoformat(),
                )
            )
        return media

    def _download_image(self, url: str, target_path: Path) -> bool:
        attempts = max(1, self.settings.download_retries)
        backoff = max(0.0, self.settings.download_backoff_seconds)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self._http_session.get(url, timeout=30)
                if response.status_code in {403, 410}:
                    # CDN URL expired; further retries won't help.
                    LOGGER.warning("Skipping %s (HTTP %s)", target_path.name, response.status_code)
                    return False
                response.raise_for_status()
                payload = response.content
                if not payload:
                    raise ValueError("empty response body")
                target_path.write_bytes(payload)
                return True
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt < attempts:
                    sleep_for = backoff * (2 ** (attempt - 1))
                    time.sleep(sleep_for)
        LOGGER.warning("Failed to download %s after %d attempts: %s", url, attempts, last_error)
        return False


def _clean_cdn_url(raw: str) -> str:
    return (
        raw
        .replace("\\u0026", "&")
        .replace("\\/", "/")
        .replace("&amp;", "&")
    )


def _is_profile_pic_url(url: str) -> bool:
    # IG CDN path `/t51.2885-19/` is used for profile pics / avatars — we
    # don't want those in the post grid. `/150x150/` and `/44x44/` size
    # suffixes are also used for small avatars.
    if "/t51.2885-19/" in url:
        return True
    if re.search(r"/s\d{2,3}x\d{2,3}/", url) and "/t51.29350-15/" not in url:
        return True
    return False


def _extract_user_from_html(html: str) -> dict | None:
    if not html:
        return None

    # Legacy shape: still emitted for a tiny % of regions / app builds.
    shared = re.search(
        r"window\._sharedData\s*=\s*(\{.*?\});</script>", html, re.DOTALL
    )
    if shared:
        try:
            data = json.loads(shared.group(1))
            legacy = (
                data.get("entry_data", {})
                .get("ProfilePage", [{}])[0]
                .get("graphql", {})
                .get("user")
            )
            if legacy:
                return legacy
        except json.JSONDecodeError:
            pass

    # Modern shape: inline JSON payloads inside <script data-sjs> tags.
    # Keys and URLs are string-escaped (\" and \/ variants). Rather than
    # untangle the Relay shell, we collect post-image CDN URLs directly.
    candidate_pattern = re.compile(
        r"https:(?:\\?/){2}[a-z0-9\-\.]+\.(?:cdninstagram\.com|fbcdn\.net)"
        r"(?:\\?/|/)[^\s\"'<>\\]+?\.(?:jpg|jpeg|webp|heic)(?:[^\s\"'<>\\]*)"
    )
    collected: list[str] = []
    seen: set[str] = set()
    for match in candidate_pattern.finditer(html):
        url = _clean_cdn_url(match.group(0))
        # Strip lingering backslashes that survive unicode escapes.
        url = url.replace("\\", "")
        if url in seen:
            continue
        if _is_profile_pic_url(url):
            continue
        seen.add(url)
        collected.append(url)

    if not collected:
        return None

    edges = []
    for index, url in enumerate(collected):
        edges.append({
            "node": {
                "shortcode": f"html-{index}",
                "display_url": url,
                "is_video": False,
                "taken_at_timestamp": 0,
                "edge_media_to_caption": {"edges": []},
            }
        })

    is_private = '"is_private":true' in html
    return {
        "is_private": is_private,
        "edge_owner_to_timeline_media": {"edges": edges},
    }


def _iso_from_ts(ts: object) -> str:
    if not isinstance(ts, (int, float)):
        return ""
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def _iter_image_urls(node: dict) -> Iterable[str]:
    if node.get("__typename") == "GraphSidecar" or node.get("edge_sidecar_to_children"):
        children = (node.get("edge_sidecar_to_children") or {}).get("edges") or []
        for child in children:
            child_node = child.get("node") or {}
            if child_node.get("is_video"):
                continue
            url = child_node.get("display_url")
            if url:
                yield url
        return
    if node.get("is_video"):
        return
    url = node.get("display_url")
    if url:
        yield url


def iter_post_images(post: instaloader.Post) -> Iterable[dict[str, str]]:
    if post.typename == "GraphSidecar":
        for sidecar in post.get_sidecar_nodes():
            if sidecar.is_video:
                continue
            yield {"url": sidecar.display_url}
        return

    if post.is_video:
        return
    yield {"url": post.url}


def extract_usernames(raw_items: list[str], limit: int) -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()

    for raw_item in raw_items:
        candidate = parse_instagram_username(raw_item)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        usernames.append(candidate)
        if len(usernames) >= limit:
            break
    return usernames


def parse_instagram_username(value: str) -> str | None:
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
    if username.lower() in RESERVED_PATHS:
        return None
    if USERNAME_RE.fullmatch(username):
        return username.lower()
    return None


def read_image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return image.size
