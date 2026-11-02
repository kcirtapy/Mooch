"""Instagram timeline scrolling, against a simulated feed. No network, no account.

One page of the home feed is only 5-10 posts, so Mooch scrolls. It must stop
at Instagram's "You're all caught up" marker (everything after it is
suggested posts), at a page with nothing new, at the page cap, or when
Instagram says there's no more. Along the way it skips suggested posts,
captionless posts and posts older than max_post_age_days.

Run:  python tests/test_instagram.py
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the mooch/ engine folder
sys.path.insert(0, str(ROOT))

from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import mooch.sources.instagram as ig  # noqa: E402

now = int(time.time())


def post(pk, user="tuftsclub", following=True, age_days=0, caption="free pizza", suggested=False):
    media = {
        "pk": pk,
        "code": f"c{pk}",
        "taken_at": now - age_days * 86400,
        "caption": {"text": caption} if caption else None,
        "user": {"username": user, "friendship_status": {"following": following}},
    }
    if suggested:
        media["is_suggested"] = True
    return {"media_or_ad": media}


class FakeClient:
    """Stands in for instagrapi's Client: hands out pre-built feed pages."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get_timeline_feed(self, reason="pull_to_refresh", max_id=None):
        page = self.pages[len(self.calls)]
        self.calls.append((reason, max_id))
        return page


def run(pages, seen=(), conf=None):
    client = FakeClient(pages)
    source = ig.InstagramSource({"delay_range": [0, 0], **(conf or {})}, None, ZoneInfo("America/New_York"))
    with patch.object(ig._time, "sleep"):
        items = source._from_timeline(client, set(seen), 60)
    return items, client.calls


# 1. Scrolls across pages, skips the junk, stops at "all caught up".
pages = [
    {"feed_items": [post(1), post(2, following=False), post(3, caption=None), {"suggested_users": {}}],
     "next_max_id": "A", "more_available": True},
    {"feed_items": [post(4), post(5, age_days=30), post(6, suggested=True)],
     "next_max_id": "B", "more_available": True},
    {"feed_items": [post(7), {"end_of_feed_demarcator": {}}, post(8, following=False)],
     "next_max_id": "C", "more_available": True},
    {"feed_items": [post(99)], "next_max_id": None},
]
items, calls = run(pages)
assert [i.external_id for i in items] == ["1", "4", "7"], [i.external_id for i in items]
assert calls == [("pull_to_refresh", None), ("pagination", "A"), ("pagination", "B")], calls
print("scrolls 3 pages, keeps followed captioned recent posts, stops at 'all caught up'")

# 2. Stops once a later page has nothing new.
pages = [
    {"feed_items": [post(10), post(11)], "next_max_id": "A", "more_available": True},
    {"feed_items": [post(12), post(13)], "next_max_id": "B", "more_available": True},
    {"feed_items": [post(14)], "next_max_id": None},
]
items, calls = run(pages, seen={"10", "11", "12", "13"})
assert items == [] and len(calls) == 2, (items, calls)
print("stops at the first page with nothing new")

# 3. Respects the page cap.
pages = [{"feed_items": [post(100 + i)], "next_max_id": f"p{i}", "more_available": True} for i in range(10)]
items, calls = run(pages, conf={"timeline_pages": 3})
assert len(calls) == 3 and len(items) == 3
print("respects timeline_pages")

# 4. Stops when Instagram says there's no more.
items, calls = run([{"feed_items": [post(200)], "next_max_id": "x", "more_available": False}])
assert len(calls) == 1 and len(items) == 1
print("stops when more_available is false")

# 5. A post without relationship info is kept, not dropped as suggested.
untagged = post(300)
del untagged["media_or_ad"]["user"]["friendship_status"]
items, _ = run([{"feed_items": [untagged], "next_max_id": None}])
assert len(items) == 1
print("keeps posts when Instagram omits the follow status")

# 6. The same post on two pages counts once.
pages = [{"feed_items": [post(400)], "next_max_id": "A", "more_available": True},
         {"feed_items": [post(400), post(401)], "next_max_id": None}]
items, _ = run(pages)
assert [i.external_id for i in items] == ["400", "401"]
print("deduplicates across pages")

print("\nALL INSTAGRAM CHECKS PASSED")
