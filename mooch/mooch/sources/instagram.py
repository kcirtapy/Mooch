"""Instagram, via the burner account's own timeline feed.

The important design choice: follow the clubs from the burner and read the
home timeline once, instead of iterating over N profiles. One request instead
of forty, and the access pattern looks like a person opening the app rather
than an enumeration sweep. Profile-by-profile polling is available as a
fallback but is off by default.

Stories are deliberately not fetched -- they trip rate limits faster and
require OCR, and this tool only cares about dated future events anyway.
"""

from __future__ import annotations

import logging
import random
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import RawItem
from .base import Source, clean, utc

log = logging.getLogger("mooch.instagram")


class InstagramAuthError(Exception):
    pass


def _client(conf: dict, password: str | None, interactive: bool = False):
    """Return a logged-in instagrapi client, reusing the saved session.

    Re-authenticating on every run is the fastest way to get challenged, so
    the session file is the primary path and the password is a fallback.
    """
    try:
        from instagrapi import Client
    except ImportError as exc:
        raise InstagramAuthError(
            "The Instagram library isn't installed in this venv. With (.venv) active, "
            'run:  pip install -e ".[instagram]"'
        ) from exc

    username = conf.get("username")
    if not username:
        raise InstagramAuthError("instagram.username is not set in config.yaml")

    session_path = Path(str(conf.get("session_file", "~/.mooch/ig_session.json"))).expanduser()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    cl = Client()
    delay = conf.get("delay_range") or [3, 9]
    cl.delay_range = [int(delay[0]), int(delay[1])]

    if session_path.exists():
        try:
            cl.load_settings(session_path)
            cl.get_timeline_feed()  # cheap liveness probe
            log.info("Reusing saved Instagram session")
            return cl
        except Exception as exc:  # noqa: BLE001
            log.warning("Saved session is stale (%s); logging in again", exc)

    if not password:
        raise InstagramAuthError(
            "No usable session and MOOCH_IG_PASSWORD is not set. Run `mooch ig-login`."
        )

    cl.login(username, password)
    cl.dump_settings(session_path)
    try:
        session_path.chmod(0o600)
    except OSError:
        pass
    log.info("Logged in and saved session to %s", session_path)
    return cl


def login(conf: dict, password: str | None):
    """Used by `mooch ig-login` to create the session file up front."""
    session_path = Path(str(conf.get("session_file", "~/.mooch/ig_session.json"))).expanduser()
    if session_path.exists():
        session_path.unlink()
    return _client(conf, password, interactive=True)


class InstagramSource(Source):
    name = "instagram"

    def __init__(self, conf: dict, password: str | None, tz):
        self.conf = conf
        self.password = password
        self.tz = tz

    def _within_active_hours(self) -> bool:
        hours = self.conf.get("active_hours")
        if not hours or len(hours) != 2:
            return True
        hour = datetime.now(timezone.utc).astimezone(self.tz).hour
        start, end = int(hours[0]), int(hours[1])
        return start <= hour <= end if start <= end else (hour >= start or hour <= end)

    def fetch(self, seen: set[str]) -> list[RawItem]:
        if not self._within_active_hours():
            log.info("Outside active hours, skipping Instagram this run")
            return []

        cl = _client(self.conf, self.password)
        limit = int(self.conf.get("max_items_per_run", 60))

        items = self._from_timeline(cl, seen, limit)

        for handle in self.conf.get("poll_usernames") or []:
            if len(items) >= limit:
                break
            items.extend(self._from_profile(cl, handle, seen, limit - len(items)))

        return items

    # -- timeline (default path) --------------------------------------------

    def _from_timeline(self, cl, seen: set[str], limit: int) -> list[RawItem]:
        """Read the home feed, a page at a time, until there's nothing new.

        One page is only five to ten posts, which with dozens of followed clubs
        and a run every few hours would miss most of them. So this scrolls,
        the same way the app does, and stops at whichever comes first:

          - Instagram's "You're all caught up" marker, after which the feed is
            suggested posts from accounts the burner doesn't follow
          - a page where every post is either already seen or too old
          - `timeline_pages` pages, or `max_items_per_run` new posts
        """
        max_pages = max(1, int(self.conf.get("timeline_pages", 5)))
        max_age = timedelta(days=int(self.conf.get("max_post_age_days", 10)))
        cutoff = datetime.now(timezone.utc) - max_age
        delay = [float(x) for x in (self.conf.get("delay_range") or [3, 9])]

        items: list[RawItem] = []
        seen_now = set(seen)
        max_id = None
        pages = 0

        while pages < max_pages and len(items) < limit:
            if pages:
                # A person pauses to read before scrolling. So does this.
                _time.sleep(random.uniform(*delay))
                payload = cl.get_timeline_feed(reason="pagination", max_id=max_id)
            else:
                payload = cl.get_timeline_feed()
            pages += 1

            payload = payload or {}
            fresh_on_page = 0
            caught_up = False

            for entry in payload.get("feed_items") or []:
                if not isinstance(entry, dict):
                    continue
                if "end_of_feed_demarcator" in entry:
                    caught_up = True
                    break
                media = entry.get("media_or_ad")
                if not isinstance(media, dict):
                    continue  # ads, suggested-user carousels, story trays
                if _is_suggested(media):
                    continue

                taken = media.get("taken_at")
                if isinstance(taken, (int, float)):
                    if datetime.fromtimestamp(taken, tz=timezone.utc) < cutoff:
                        continue

                item = _media_to_item(media, seen_now)
                if item is None:
                    continue
                seen_now.add(item.external_id)
                items.append(item)
                fresh_on_page += 1
                if len(items) >= limit:
                    break

            if caught_up:
                log.debug("Reached the end of followed posts after %d page(s)", pages)
                break
            if fresh_on_page == 0 and pages > 1:
                log.debug("Page %d had nothing new, stopping", pages)
                break

            max_id = payload.get("next_max_id")
            if not max_id or not payload.get("more_available", True):
                break

        log.info("Instagram: %d new post(s) across %d page(s)", len(items), pages)
        return items

    # -- per-profile (fallback) ---------------------------------------------

    def _from_profile(self, cl, handle: str, seen: set[str], limit: int) -> list[RawItem]:
        handle = handle.lstrip("@").strip()
        if not handle:
            return []
        try:
            _time.sleep(random.uniform(*[float(x) for x in (self.conf.get("delay_range") or [3, 9])]))
            user_id = cl.user_id_from_username(handle)
            medias = cl.user_medias(user_id, amount=min(limit, 8))
        except Exception as exc:  # noqa: BLE001
            log.warning("Profile poll failed for @%s: %s", handle, exc)
            return []

        items: list[RawItem] = []
        for m in medias:
            code = getattr(m, "code", None)
            pk = str(getattr(m, "pk", "") or code or "")
            if not pk or f"{pk}" in seen:
                continue
            caption = clean(getattr(m, "caption_text", "") or "")
            if not caption:
                continue
            items.append(
                RawItem(
                    source="instagram",
                    external_id=pk,
                    author=f"@{handle}",
                    text=caption,
                    url=f"https://www.instagram.com/p/{code}/" if code else None,
                    posted_at=utc(getattr(m, "taken_at", None)),
                )
            )
        return items


def _is_suggested(media: dict) -> bool:
    """True for posts Instagram injected from accounts the burner doesn't follow.

    The home feed mixes these in. They're never Tufts clubs, and classifying
    them would cost money for nothing. When Instagram includes the burner's
    relationship to the poster, trust it; when it doesn't, keep the post.
    """
    if media.get("is_suggested") or media.get("explore"):
        return True
    status = (media.get("user") or {}).get("friendship_status")
    if isinstance(status, dict) and "following" in status:
        return not status["following"]
    return False


def _media_to_item(media: dict, seen: set[str]) -> RawItem | None:
    pk = str(media.get("pk") or media.get("id") or "").split("_")[0]
    if not pk or pk in seen:
        return None

    caption = media.get("caption") or {}
    text = clean(caption.get("text") if isinstance(caption, dict) else "")
    if not text:
        return None  # image-only post; nothing to classify without vision

    user = media.get("user") or {}
    handle = user.get("username")
    code = media.get("code")
    taken = media.get("taken_at")
    posted = (
        datetime.fromtimestamp(taken, tz=timezone.utc)
        if isinstance(taken, (int, float))
        else utc(None)
    )

    return RawItem(
        source="instagram",
        external_id=pk,
        author=f"@{handle}" if handle else None,
        text=text,
        url=f"https://www.instagram.com/p/{code}/" if code else None,
        posted_at=posted,
    )
