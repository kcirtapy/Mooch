"""JumboLife — Tufts' events calendar, powered by CampusGroups.

CampusGroups publishes a public iCalendar feed of every group's public events:

    https://tufts.campusgroups.com/ical/tufts/ical_tufts.ics

No login, no API key, no reverse-engineered XHR. It 302s to a CDN, which
`requests` follows on its own.

The format has several quirks that this module exists to absorb:

  - SUMMARY and DESCRIPTION may carry ENCODING=QUOTED-PRINTABLE, which is a
    vCard 2.1 convention rather than anything in RFC 5545, so the icalendar
    library hands it back undecoded. Left alone, "Dean's Reception" arrives as
    "Dean=27s Reception".
  - LOCATION is often a placeholder: "TBD", or "Sign in to download the
    location" for events whose venue is gated behind SSO. Those are not venues
    and shouldn't be shown as ones.
  - Every DESCRIPTION ends with a "--- Event Details: <url>" footer, which is
    noise in the classifier prompt.
  - The feed includes events that have already happened. Those get dropped
    before they cost an API call.
"""

from __future__ import annotations

import hashlib
import logging
import quopri
import re
from datetime import date, datetime, time, timedelta, timezone

import requests
from icalendar import Calendar

from ..models import RawItem
from .base import Source, clean, utc

log = logging.getLogger("mooch.jumbolife")

DEFAULT_FEED = "https://tufts.campusgroups.com/ical/tufts/ical_tufts.ics"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# The trailing "--- Event Details: <link>" block CampusGroups appends to
# every description. The URL is already captured separately.
_FOOTER = re.compile(r"\n?-{3,}\s*\n?\s*Event Details:.*$", re.S)

# Placeholder locations that carry no information.
_JUNK_LOCATIONS = {
    "tbd",
    "tba",
    "n/a",
    "na",
    "none",
    "to be determined",
    "to be announced",
    "sign in to download the location",
    "please sign in to see the location",
}


class JumboLifeSource(Source):
    name = "jumbolife"

    def __init__(self, conf: dict, tz):
        self.conf = conf
        self.tz = tz
        self.headers = {"User-Agent": UA, **(conf.get("headers") or {})}

    def _feeds(self) -> list[str]:
        """Configured feeds, or the campus-wide one.

        More than one is useful once you sign in and grab a personal feed from
        the Subscribe dialog: that one also carries members-only events for
        groups you belong to, which the public feed omits.
        """
        feeds = self.conf.get("feeds")
        if isinstance(feeds, str):
            feeds = [feeds]
        feeds = [f.strip() for f in (feeds or []) if f and f.strip()]

        # Back-compat with the single-URL key the config used to have.
        legacy = (self.conf.get("ics_url") or "").strip()
        if legacy and legacy not in feeds:
            feeds.append(legacy)

        return feeds or [DEFAULT_FEED]

    def fetch(self, seen: set[str]) -> list[RawItem]:
        items: list[RawItem] = []
        errors: list[str] = []

        for url in self._feeds():
            try:
                items.extend(self._fetch_one(url, seen))
            except Exception as exc:  # noqa: BLE001 - one bad feed shouldn't kill the rest
                errors.append(f"{url}: {exc}")
                log.warning("Feed failed, continuing: %s (%s)", url, exc)

        if errors and not items:
            raise RuntimeError("; ".join(errors))
        return items

    def _fetch_one(self, url: str, seen: set[str]) -> list[RawItem]:
        resp = requests.get(url, headers=self.headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        body = resp.content
        if b"BEGIN:VCALENDAR" not in body[:2048]:
            raise ValueError(
                "That URL didn't return an iCalendar feed. If it redirected to a "
                "sign-in page, the feed needs a token — grab a fresh one from the "
                "Subscribe dialog on the JumboLife events page."
            )

        cal = Calendar.from_ical(body)
        # An event that ended over three hours ago is no longer moochable.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=3)

        items: list[RawItem] = []
        skipped_past = 0

        for comp in cal.walk("VEVENT"):
            start = _ical_dt(comp.get("DTSTART"), self.tz)
            end = _ical_dt(comp.get("DTEND"), self.tz)

            # Drop what's already over, so it never reaches the classifier.
            effective_end = end or start
            if effective_end is not None and effective_end < cutoff:
                skipped_past += 1
                continue

            title = _text(comp, "SUMMARY")
            uid = str(comp.get("UID") or "").strip()
            if not uid:
                uid = "gen-" + hashlib.sha1(
                    f"{title}|{start}".encode("utf-8", "replace")
                ).hexdigest()[:20]
            if uid in seen:
                continue

            description = _FOOTER.sub("", _text(comp, "DESCRIPTION")).strip()
            location = _location(comp)
            link = str(comp.get("URL") or "").strip() or None
            author = _author(comp)

            if comp.get("RRULE"):
                # CampusGroups normally emits each occurrence as its own VEVENT,
                # so this is unexpected; only the first instance is captured.
                log.debug("Recurring event, taking first occurrence only: %s", title)

            body_text = "\n\n".join(filter(None, [title, description])) or title
            if not body_text.strip():
                continue  # nothing for the classifier to read

            items.append(
                RawItem(
                    source=self.name,
                    external_id=uid,
                    title=title or None,
                    author=author,
                    text=body_text,
                    url=link,
                    posted_at=_posted_at(comp),
                    starts_at=start,
                    ends_at=end,
                    location=location,
                )
            )

        log.info(
            "%s: %d upcoming, %d already over", url.rsplit("/", 1)[-1], len(items), skipped_past
        )
        return items


# -- field helpers ----------------------------------------------------------


def _text(comp, key: str) -> str:
    """Read a property, decoding quoted-printable when the feed used it."""
    prop = comp.get(key)
    if prop is None:
        return ""

    raw = str(prop)
    encoding = ""
    params = getattr(prop, "params", None)
    if params:
        encoding = str(params.get("ENCODING", "") or "")

    if encoding.upper() == "QUOTED-PRINTABLE" or re.search(r"=[0-9A-F]{2}", raw):
        try:
            decoded = quopri.decodestring(raw.encode("utf-8", "replace"))
            raw = decoded.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - keep the original on any failure
            pass

    return clean(raw)


def _location(comp) -> str | None:
    value = _text(comp, "LOCATION")
    if not value:
        return None
    if value.strip().lower() in _JUNK_LOCATIONS:
        return None
    return value


def _author(comp) -> str | None:
    """The hosting group.

    ORGANIZER carries a CN, but CampusGroups sets it to the umbrella office for
    a lot of events, so the club_acronym category is a useful supplement.
    """
    organizer = comp.get("ORGANIZER")
    name = ""
    if organizer is not None:
        params = getattr(organizer, "params", None)
        if params:
            name = str(params.get("CN", "") or "").strip().strip('"')

    acronym = ""
    for cat in _categories(comp):
        prop, _, value = cat.partition(":")
        if prop == "club_acronym":
            acronym = value.strip()
            break

    if name and acronym and acronym.lower() not in name.lower():
        return f"{name} ({acronym})"
    return name or acronym or None


def _categories(comp) -> list[str]:
    """Flatten CATEGORIES into "<x-cg-category>:<value>" strings."""
    out: list[str] = []
    raw = comp.get("CATEGORIES")
    if raw is None:
        return out

    entries = raw if isinstance(raw, list) else [raw]
    for entry in entries:
        params = getattr(entry, "params", None)
        kind = str(params.get("X-CG-CATEGORY", "") or "") if params else ""
        try:
            values = [str(c) for c in entry.cats]  # icalendar's vCategory
        except AttributeError:
            values = [str(entry)]
        for value in values:
            out.append(f"{kind}:{value}" if kind else f":{value}")
    return out


def _posted_at(comp) -> datetime:
    """When the listing appeared, preferring CREATED over the fetch time.

    The classifier resolves relative dates against this, and undated hits are
    aged out by it, so a real timestamp beats now().
    """
    for key in ("CREATED", "LAST-MODIFIED", "DTSTAMP"):
        value = _ical_dt(comp.get(key), timezone.utc)
        if value is not None:
            return value
    return utc(None)


def _ical_dt(prop, tz) -> datetime | None:
    if prop is None:
        return None
    value = getattr(prop, "dt", None)
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc(value if value.tzinfo else value.replace(tzinfo=tz))
    if isinstance(value, date):
        # An all-day entry. Noon local keeps it on the right calendar day.
        return utc(datetime.combine(value, time(12, 0)).replace(tzinfo=tz))
    return None
