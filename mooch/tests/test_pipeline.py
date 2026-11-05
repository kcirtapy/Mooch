"""End-to-end: store -> classifier -> server feed -> Android contract."""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the mooch/ engine folder
sys.path.insert(0, str(ROOT))
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo


from mooch import config as C  # noqa: E402
from mooch.classify import TOOL, Classifier  # noqa: E402
from mooch.db import Store  # noqa: E402
from mooch.models import RawItem, Verdict  # noqa: E402
from mooch.pipeline import events_to_show  # noqa: E402
from mooch.report import print_table, write_html  # noqa: E402
from mooch.server import Server, build_feed, export_feed  # noqa: E402

TZ = ZoneInfo("America/New_York")
now = datetime.now(timezone.utc)
SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="mooch-test-"))   # throwaway data dir

# -- config ----------------------------------------------------------------
cfg_path = SCRATCH / "config.yaml"
cfg_path.write_text(
    (pathlib.Path(ROOT) / "config.example.yaml")
    .read_text()
    .replace("data_dir: ~/.mooch", f"data_dir: {SCRATCH}")
    .replace('token: ""', 'token: "testtoken123"')
)
cfg = C.load(cfg_path)
print(f"config: tz={cfg.timezone} interval={cfg.section('server')['interval_minutes']}min "
      f"jumbolife_enabled={cfg.enabled('jumbolife')}")
assert cfg.enabled("jumbolife"), "jumbolife should be on by default now"
assert cfg.section("server")["interval_minutes"] == 180
assert cfg.section("jumbolife")["feeds"][0].endswith("ical_tufts.ics")

db = SCRATCH / "mooch.db"
if db.exists():
    db.unlink()
store = Store(db)

# -- items, shaped like what the real sources produce ----------------------
items = [
    RawItem(source="jumbolife", external_id="cbe7b53e@campusgroups.com",
            title="Night Market — Dean's Lawn",
            author="Taiwanese Association of Students at Tufts (TAST)",
            text="Night Market — Dean's Lawn\n\nFree boba and popcorn chicken for everyone!",
            posted_at=now - timedelta(days=2), starts_at=now + timedelta(days=3, hours=2),
            location="Mayer Campus Center",
            url="https://tufts.campusgroups.com/rsvp?id=400001"),
    RawItem(source="email", external_id="<m1@tufts>", author="Tufts Hillel",
            title="Shabbat dinner this Friday",
            text="Join us for a free catered Shabbat dinner, Friday at 7pm, Granoff.",
            posted_at=now - timedelta(days=1)),
    RawItem(source="instagram", external_id="ig1", author="@tuftsacm",
            text="FREE PIZZA at our GBM tonight 6pm in Halligan 102!",
            posted_at=now - timedelta(hours=2),
            url="https://www.instagram.com/p/abc/"),
    RawItem(source="instagram", external_id="ig2", author="@tuftsbakeclub",
            text="Bake sale Thursday, cookies $2 each, proceeds to charity",
            posted_at=now - timedelta(hours=5)),
    RawItem(source="jumbolife", external_id="undated-1@campusgroups.com",
            title="Weekly coffee hour", author="Physics Society",
            text="Weekly coffee hour. Snacks usually appear.",
            posted_at=now - timedelta(hours=8)),
]
assert store.add_items(items) == 5
assert store.add_items(items) == 0, "re-adding identical items must be a no-op"

# An edited event must be re-queued for classification.
edited = RawItem(**{**items[0].__dict__, "location": "Tisch Library Roof"})
assert store.add_items([edited]) == 1, "changed content should re-enter the queue"
print("dedup + change detection ok")

# -- classifier, with the API mocked ---------------------------------------
json.dumps(TOOL)  # schema must be serializable
verdicts = {
    "cbe7b53e@campusgroups.com": Verdict(True, 0.94, "Night Market", "boba and popcorn chicken",
                                         now + timedelta(days=3, hours=2), "Tisch Library Roof",
                                         "Explicitly free."),
    "<m1@tufts>": Verdict(True, 0.92, "Shabbat Dinner", "catered dinner",
                          now + timedelta(days=2, hours=3), "Granoff", "Free catered dinner."),
    "ig1": Verdict(True, 0.96, "ACM GBM", "pizza", now + timedelta(hours=4),
                   "Halligan 102", "Explicit free pizza."),
    "ig2": Verdict(False, 0.93, None, None, None, None, "Food is sold, not given away."),
    "undated-1@campusgroups.com": Verdict(True, 0.45, "Coffee hour", "snacks", None, None,
                                          "Recurring, no specific date."),
}
pending = store.unclassified()
assert len(pending) == 5, len(pending)
for item_id, item in pending:
    store.save_verdict(item_id, verdicts[item.external_id], "test-model")

# Timezone round-trip through the real classifier code path.
block = MagicMock()
block.type = "tool_use"
block.input = {"has_free_food": True, "confidence": 0.9, "event_title": "T",
               "food": "pizza", "starts_at": "2026-09-25T18:00", "location": "X",
               "reason": "y"}
msg = MagicMock()
msg.content = [block]
with patch("anthropic.Anthropic") as A:
    A.return_value.messages.create.return_value = msg
    v = Classifier("k", "m", TZ).classify(items[2])
assert v.starts_at == datetime(2026, 9, 25, 22, 0, tzinfo=timezone.utc), v.starts_at
print("classifier local->UTC conversion ok (6pm EDT -> 22:00Z)")

# -- hits ------------------------------------------------------------------
since = now - timedelta(hours=3)
until = now + timedelta(days=cfg.lookahead_days)
hits = store.hits(cfg.confidence_threshold, since, until)
print(f"hits above {cfg.confidence_threshold}: {[h.name for h in hits]}")
assert len(hits) == 3, f"bake sale and the 0.45 coffee hour should both be out: {len(hits)}"
assert hits[0].item.external_id == "ig1", "soonest first"
assert hits[0].where == "Halligan 102"
# The edited location must win over the stale one.
night = next(h for h in hits if h.item.source == "jumbolife")
assert night.where == "Tisch Library Roof", night.where
print("confidence floor + ordering + edited-field precedence ok")

# Lower the floor and the undated one reappears, last.
loose = store.hits(0.4, since, until)
assert len(loose) == 4 and loose[-1].when is None
print("undated hits sort last when the floor allows them")

print_table(hits, cfg.timezone)
html = write_html(hits, cfg.timezone, cfg.report_path, store.counts())
body = html.read_text()
assert "Tisch Library Roof" in body, "edited location should render"
assert "boba and popcorn chicken" in body
# The club name arrives with an apostrophe-free but non-ASCII-safe name elsewhere;
# confirm nothing is double-escaped into visible entities.
assert "&amp;#" not in body, "double-escaped HTML entity in the report"
assert "<script>" in body and "data-ts" in body, "live countdown script missing"
print(f"report written: {html.name}, {html.stat().st_size} bytes")

# -- server feed + Android contract ----------------------------------------
feed = build_feed(cfg, store)
ev = feed["events"][0]
print("\nfeed sample:", json.dumps(ev, indent=2)[:320])

kt = (ROOT.parent / "mooch-android/app/src/main/java/com/mooch/data/Models.kt").read_text()
import re  # noqa: E402


def kt_fields(name):
    m = re.search(r"data class %s\((.*?)\n\)" % name, kt, re.S)
    return {s or v for s, v in re.findall(
        r'(?:@SerialName\("(\w+)"\)\s*)?va[lr] (\w+)\s*:', m.group(1))}


kt_event, kt_feed = kt_fields("MoochEvent"), kt_fields("Feed")
py_event, py_feed = set(ev), set(feed)
assert not (py_event - kt_event), f"Kotlin would drop: {py_event - kt_event}"
assert not (kt_event - py_event), f"Kotlin expects unsent: {kt_event - py_event}"
assert not (kt_feed - py_feed), f"Feed missing: {kt_feed - py_feed}"
for key in ("startsAt", "postedAt", "generatedAt"):
    val = ev.get(key) if key in ev else feed.get(key)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", val), f"{key}={val}"
print(f"contract ok: {len(kt_event)} event fields match, all timestamps ISO_INSTANT+Z")

exported = export_feed(cfg, store)
assert json.loads(exported.read_text())["events"], "export should have content"
print(f"export ok: {exported}")

# -- HTTP ------------------------------------------------------------------
srv = Server(cfg, "127.0.0.1", 8801, "testtoken123", 180)
threading.Thread(target=srv.httpd.serve_forever, daemon=True).start()
time.sleep(0.4)


def get(path, bearer=None):
    req = urllib.request.Request(f"http://127.0.0.1:8801{path}")
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


assert get("/health")[0] == 200
assert get("/api/events.json")[0] == 401
assert get("/api/events.json", "wrong")[0] == 401
code, payload = get("/api/events.json", "testtoken123")
assert code == 200 and len(payload["events"]) == 3, (code, payload)
assert get("/api/events.json?token=testtoken123")[0] == 200
assert get("/nope")[0] == 404
import concurrent.futures  # noqa: E402

with concurrent.futures.ThreadPoolExecutor(8) as p:
    codes = list(p.map(lambda _: get("/api/events.json", "testtoken123")[0], range(16)))
assert set(codes) == {200}, codes
srv.httpd.shutdown()
print("server: auth, both token styles, 404, 16 concurrent reads ok")

# -- past events: in the app's feed, not in the report -----------------------
assert cfg.history_days == 30
store.add_items([
    RawItem(source="instagram", external_id="past-2d", author="@tuftsvsc",
            text="Pho night Tuesday, free pho!", posted_at=now - timedelta(days=5)),
    RawItem(source="instagram", external_id="past-45d", author="@tuftsvsc",
            text="Free cider at the fall fest", posted_at=now - timedelta(days=50)),
])
for item_id, item in store.unclassified():
    days = 2 if item.external_id == "past-2d" else 45
    store.save_verdict(item_id, Verdict(True, 0.9, "Old event", "pho", now - timedelta(days=days),
                                        "Dewick", "Free."), "test-model")
feed_ids = [e["id"] for e in build_feed(cfg, store)["events"]]
assert "instagram:past-2d" in feed_ids, "a recent past event belongs in the app's feed"
assert "instagram:past-45d" not in feed_ids, "older than history_days stays out"
assert feed_ids.index("instagram:past-2d") == 0, "the feed runs oldest first"
shown = [h.item.external_id for h in events_to_show(cfg, store)]
assert "past-2d" not in shown and len(shown) == 3, "the report and `mooch list` stay upcoming-only"
print("past events: last 30 days in the app's feed, kept out of the report")

print("\nALL PIPELINE CHECKS PASSED")
