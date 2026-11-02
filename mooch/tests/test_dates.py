"""Regression test for relative dates, and the one-time re-screen.

The bug: a post on Saturday Sep 26 saying "next monday" came back as Oct 5,
a week late. The fix gives the model a table of the 14 days after the post,
with the first occurrence of each weekday marked, plus a rule that "next
Monday" means the first Monday after posting. When that prompt changes,
recent items are re-screened exactly once.

Run:  python tests/test_dates.py      (no network, no API calls)
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the mooch/ engine folder
sys.path.insert(0, str(ROOT))

from datetime import datetime, timedelta, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from mooch.classify import PROMPT_VERSION, SYSTEM, _prompt  # noqa: E402
from mooch.db import Store  # noqa: E402
from mooch.models import RawItem, Verdict  # noqa: E402

TZ = ZoneInfo("America/New_York")

# -- the date table -----------------------------------------------------------
saturday_post = RawItem(
    source="instagram",
    external_id="mid-autumn",
    text="Mid Autumn Festival next monday, free mooncakes!",
    posted_at=datetime(2026, 9, 26, 15, 0, tzinfo=TZ).astimezone(timezone.utc),
)
prompt = _prompt(saturday_post, TZ, 4000)

assert "Monday September 28  <- first of this weekday after posting" in prompt, prompt
assert "Monday October 05" in prompt, "the following Monday should be listed too"
assert "Monday October 05  <-" not in prompt, "only the FIRST Monday may be marked"
assert "FIRST Monday after" in SYSTEM, "the next-weekday rule must be in the system prompt"
print("Saturday post: 'next monday' is marked as Monday September 28")

# A post made ON a Monday: the next Monday is a week away, and is the one marked.
monday_post = RawItem(
    source="instagram", external_id="m", text="see you next monday",
    posted_at=datetime(2026, 9, 28, 12, 0, tzinfo=TZ).astimezone(timezone.utc),
)
assert "Monday October 05  <- first" in _prompt(monday_post, TZ, 4000)
print("Monday post: the marked Monday is a week later, October 05")

# -- re-screening under a new prompt --------------------------------------------
db = pathlib.Path(tempfile.mkdtemp(prefix="mooch-test-")) / "dates.db"
store = Store(db)
now = datetime.now(timezone.utc)
store.add_items([
    RawItem("instagram", "recent_future", "t", now - timedelta(days=2), starts_at=now + timedelta(days=5)),
    RawItem("instagram", "recent_undated", "t", now - timedelta(days=1)),
    RawItem("jumbolife", "past_event", "t", now - timedelta(days=3), starts_at=now - timedelta(days=1)),
    RawItem("email", "old_post", "t", now - timedelta(days=40)),
])
for item_id, _ in store.unclassified():
    store.save_verdict(item_id, Verdict(True, 0.9), "claude-haiku-4-5-20251001")   # judged by the old prompt

tag = f"claude-haiku-4-5-20251001|{PROMPT_VERSION}"
again = sorted(item.external_id for _, item in store.unclassified(tag))
assert again == ["recent_future", "recent_undated"], again
print("New prompt re-screens only recent, still-relevant items:", again)

for item_id, _ in store.unclassified(tag):
    store.save_verdict(item_id, Verdict(True, 0.9), tag)
assert store.unclassified(tag) == [], "nothing should be re-screened twice"
print("Second run re-screens nothing")

print("\nALL DATE CHECKS PASSED")
