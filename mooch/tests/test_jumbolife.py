"""Parser test against the real CampusGroups feed format.

The first two VEVENTs are copied verbatim from
https://tufts.campusgroups.com/ical/tufts/ical_tufts.ics — including the
quoted-printable SUMMARY param, the gated LOCATION, and the "Event Details"
footer. The rest are synthetic, covering cases the two samples don't.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the mooch/ engine folder
sys.path.insert(0, str(ROOT))
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo


from mooch.sources.jumbolife import JumboLifeSource, DEFAULT_FEED  # noqa: E402

TZ = ZoneInfo("America/New_York")
now = datetime.now(timezone.utc)
soon = now + timedelta(days=3)
later = now + timedelta(days=6)


def ics_stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


FIXTURE = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CampusGroups//NONSGML v1.0//EN
BEGIN:VEVENT
DTSTAMP:20260917T232348Z
LAST-MODIFIED:20260713T171833Z
CREATED:20230407T230340Z
SEQUENCE:6
ORGANIZER;CN="Office for Campus Life":mailto:noreply@tufts.campusgroups.com
CONTACT:https://tufts.campusgroups.com/ocl/rsvp_boot?id=374921#event_host
CATEGORIES;X-CG-CATEGORY=club_acronym:OCL
CATEGORIES;X-CG-CATEGORY=event_type:Undergraduate Student Organization Event
DTSTART:20260627T170000Z
DTEND:20260627T180000Z
UID:cbe7b53e0ce096cefec1aa20eb4b41be472023_7:03:40_PM@campusgroups.com
SUMMARY;ENCODING=QUOTED-PRINTABLE:Annual Gala Dinner
LOCATION:TBD
URL:https://tufts.campusgroups.com/rsvp?id=374921
DESCRIPTION:Ready for our Annual Gala Dinner This is one of our most demanded events with more than 200 people in attendance last year!\\n---\\nEvent Details: https://tufts.campusgroups.com/rsvp?id=374921
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20260917T232348Z
LAST-MODIFIED:20260824T180602Z
CREATED:20260713T190801Z
SEQUENCE:20
ORGANIZER;CN="Office for Campus Life":mailto:noreply@tufts.campusgroups.com
CONTACT:https://tufts.campusgroups.com/ocl/rsvp_boot?id=374958#event_host
CATEGORIES;X-CG-CATEGORY=club_acronym:OCL
CATEGORIES;X-CG-CATEGORY=event_type:Graduate Student Organization Event
DTSTART:20260713T170000Z
DTEND:20260713T180000Z
UID:ff41eeb9e28b85603659f48d135d6a217132026_3:08:01_PM@campusgroups.com
SUMMARY;ENCODING=QUOTED-PRINTABLE:On-Campus Event (Graduate)
LOCATION: Sign in to download the location
URL:https://tufts.campusgroups.com/rsvp?id=374958
DESCRIPTION: \\n---\\nEvent Details: https://tufts.campusgroups.com/rsvp?id=374958
END:VEVENT
BEGIN:VEVENT
DTSTAMP:{ics_stamp(now)}
CREATED:{ics_stamp(now - timedelta(days=2))}
ORGANIZER;CN="Taiwanese Association of Students at Tufts":mailto:noreply@tufts.campusgroups.com
CATEGORIES;X-CG-CATEGORY=club_acronym:TAST
DTSTART:{ics_stamp(soon)}
DTEND:{ics_stamp(soon + timedelta(hours=2))}
UID:future-boba-1@campusgroups.com
SUMMARY;ENCODING=QUOTED-PRINTABLE:Night Market =E2=80=94 Dean=27s Lawn
LOCATION:Mayer Campus Center
URL:https://tufts.campusgroups.com/rsvp?id=400001
DESCRIPTION:Free boba and popcorn chicken for everyone who comes!\\n---\\nEvent Details: https://tufts.campusgroups.com/rsvp?id=400001
END:VEVENT
BEGIN:VEVENT
DTSTAMP:{ics_stamp(now)}
DTSTART;VALUE=DATE:{later.strftime('%Y%m%d')}
UID:allday-1@campusgroups.com
SUMMARY:Community Potluck Day
LOCATION:Academic Quad
DESCRIPTION:Bring a dish or just come eat.\\n---\\nEvent Details: https://tufts.campusgroups.com/rsvp?id=400002
END:VEVENT
BEGIN:VEVENT
DTSTAMP:{ics_stamp(now)}
DTSTART:{ics_stamp(now + timedelta(days=4))}
UID:no-summary-or-desc@campusgroups.com
SUMMARY:
DESCRIPTION: \\n---\\nEvent Details: https://tufts.campusgroups.com/rsvp?id=400003
END:VEVENT
END:VCALENDAR
"""


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


results = {"calls": []}


def fake_get(url, **kwargs):
    results["calls"].append((url, kwargs))
    return FakeResponse(FIXTURE.encode("utf-8"))


src = JumboLifeSource({}, TZ)
with patch("mooch.sources.jumbolife.requests.get", side_effect=fake_get):
    items = src.fetch(set())

print(f"default feed used: {results['calls'][0][0]}")
assert results["calls"][0][0] == DEFAULT_FEED, results["calls"][0][0]
assert results["calls"][0][1]["allow_redirects"] is True, "must follow the CDN 302"

print(f"\nparsed {len(items)} item(s) from 5 VEVENTs\n" + "=" * 72)
for it in items:
    start = it.starts_at.astimezone(TZ).strftime("%a %Y-%m-%d %I:%M %p") if it.starts_at else "—"
    print(f"  title    {it.title!r}")
    print(f"  author   {it.author!r}")
    print(f"  starts   {start}")
    print(f"  location {it.location!r}")
    print(f"  posted   {it.posted_at.astimezone(TZ).strftime('%Y-%m-%d')}")
    print(f"  url      {it.url}")
    print(f"  text     {it.text!r}")
    print("-" * 72)

by_id = {it.external_id: it for it in items}

# Past events (June + July, today is September) must be dropped before classifying.
assert not any("472023" in k for k in by_id), "past Gala event should be skipped"
assert not any("7132026" in k for k in by_id), "past grad event should be skipped"

# An event with neither a title nor a description has nothing to classify.
assert "no-summary-or-desc@campusgroups.com" not in by_id, "empty event should be skipped"

assert len(items) == 2, f"expected 2 usable events, got {len(items)}"

# Quoted-printable decoding: =E2=80=94 is an em dash, =27 an apostrophe.
boba = by_id["future-boba-1@campusgroups.com"]
assert boba.title == "Night Market — Dean's Lawn", repr(boba.title)
print("quoted-printable decoded correctly:", boba.title)

# Organizer CN plus the club acronym.
assert boba.author == "Taiwanese Association of Students at Tufts (TAST)", repr(boba.author)
print("author built from ORGANIZER CN + club_acronym:", boba.author)

# The "--- Event Details:" footer is stripped, the real copy kept.
assert "Event Details" not in boba.text, boba.text
assert "---" not in boba.text, boba.text
assert "Free boba and popcorn chicken" in boba.text
print("footer stripped, description preserved")

# Junk locations become None; real ones survive.
assert boba.location == "Mayer Campus Center"
print("real location kept:", boba.location)

# posted_at comes from CREATED, not the fetch time.
assert (now - boba.posted_at).days == 2, boba.posted_at
print("posted_at read from CREATED, not now()")

# All-day event lands on the right calendar day, not shifted by the UTC offset.
allday = by_id["allday-1@campusgroups.com"]
assert allday.starts_at.astimezone(TZ).date() == later.date(), (
    allday.starts_at.astimezone(TZ).date(), later.date()
)
print("all-day event stays on its own calendar day:", allday.starts_at.astimezone(TZ).date())

# Dedup: a second pass with those ids already seen yields nothing.
with patch("mooch.sources.jumbolife.requests.get", side_effect=fake_get):
    again = src.fetch(set(by_id))
assert again == [], f"expected no new items, got {len(again)}"
print("dedup by UID works on the second pass")

# Multiple feeds, one broken: the good one still comes through.
calls = {"n": 0}


def flaky_get(url, **kwargs):
    calls["n"] += 1
    if "broken" in url:
        raise requests_exc("boom")
    return FakeResponse(FIXTURE.encode("utf-8"))


import requests  # noqa: E402

requests_exc = requests.exceptions.ConnectionError

multi = JumboLifeSource({"feeds": ["https://broken.example/x.ics", DEFAULT_FEED]}, TZ)
with patch("mooch.sources.jumbolife.requests.get", side_effect=flaky_get):
    partial = multi.safe_fetch(set())
assert len(partial) == 2, f"one bad feed shouldn't lose the other: got {len(partial)}"
print("one failing feed doesn't take down the others")

# A sign-in page instead of a feed produces a message worth reading.
with patch("mooch.sources.jumbolife.requests.get",
           side_effect=lambda url, **kw: FakeResponse(b"<html><body>Sign in</body></html>")):
    broke = JumboLifeSource({}, TZ).safe_fetch(set())
assert broke == []
print("non-iCalendar response handled without crashing")

print("\nALL JUMBOLIFE CHECKS PASSED")
