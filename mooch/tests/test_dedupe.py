"""Merging listings of the same event. No network, no API calls.

The case that prompted it: VSC's Coffee Shop showed up three times -- the
JumboLife listing plus two Instagram posts from @tuftsvsc, all Saturday 5pm.

Run:  python tests/test_dedupe.py
"""
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the mooch/ engine folder
sys.path.insert(0, str(ROOT))

from datetime import datetime, timedelta, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from mooch.dedupe import club_keys, merge_duplicates  # noqa: E402
from mooch.models import Hit, RawItem, Verdict  # noqa: E402
from mooch.report import print_table, write_html  # noqa: E402
from mooch.server import hit_to_dict  # noqa: E402

TZ = ZoneInfo("America/New_York")
SAT_5PM = datetime(2026, 11, 7, 17, 0, tzinfo=TZ)


def hit(source, ext, author, title, when, where=None, food=None, conf=0.9, calendar=False):
    """A screened listing. `calendar` means the source itself gave the time, as JumboLife does."""
    utc = when.astimezone(timezone.utc) if when else None
    item = RawItem(source=source, external_id=ext, text=title, author=author, title=title,
                   posted_at=datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc),
                   starts_at=utc if calendar else None, url=f"https://example.com/{ext}")
    return Hit(item, Verdict(True, conf, title, food, utc, where, f"reason {ext}"))


def keys(hits):
    return [h.item.key() for h in hits]


def merged(*hits):
    return merge_duplicates(list(hits), TZ)


# -- club identities ------------------------------------------------------------
assert "vsc" in club_keys("@tuftsvsc")
assert "vsc" in club_keys("Vietnamese Students Club (VIETNAMESE)")
assert "tast" in club_keys("@tasttufts")
assert "tast" in club_keys("Taiwanese Association of Students at Tufts (TAST)")
assert "hillel" in club_keys("Tufts Hillel") and "hillel" in club_keys("@tuftshillel")
assert "vsc" in club_keys("Tufts VSC <vsc@elist.tufts.edu>")
assert not club_keys("@tufts") and not club_keys(None)
print("club names, handles, initials and list addresses line up")

# -- 1. the screenshot ----------------------------------------------------------------
jl = hit("jumbolife", "vsc@campusgroups.com", "Vietnamese Students Club (VIETNAMESE)",
         "Vietnamese Student Club Coffee Shop", SAT_5PM, None, "Vietnamese food (unspecified)",
         conf=0.8, calendar=True)
ig1 = hit("instagram", "p1", "@tuftsvsc", "VSC Mid Autumn Festival Coffee Shop", SAT_5PM,
          "51 Winthrop", "Not yet specified, but food promised", conf=0.85)
ig2 = hit("instagram", "p2", "@tuftsvsc", "VSC Coffee Shop Event", SAT_5PM,
          "51 Winthrop", "Delicious options (unspecified)", conf=0.9)
acm = hit("instagram", "p3", "@tuftsacm", "ACM GBM", SAT_5PM + timedelta(hours=1),
          "Halligan 102", "pizza")

out = merged(ig1, jl, acm, ig2)
assert keys(out) == ["jumbolife:vsc@campusgroups.com", "instagram:p3"], keys(out)
coffee = out[0]
assert sorted(keys(coffee.also)) == ["instagram:p1", "instagram:p2"], keys(coffee.also)
assert coffee.where == "51 Winthrop", "the place comes from the Instagram posts"
assert coffee.when == SAT_5PM and coffee.name == "Vietnamese Student Club Coffee Shop"
assert coffee.item.author == "Vietnamese Students Club (VIETNAMESE)"
assert coffee.verdict.confidence == 0.9, "keeps the surest listing's confidence"
assert coffee.verdict.food == "Vietnamese food (unspecified)"
print("Coffee Shop x3 -> one event led by JumboLife, place from Instagram; ACM GBM untouched")

# The order the listings arrive in doesn't matter.
assert keys(merged(jl, ig2, ig1)) == ["jumbolife:vsc@campusgroups.com"]

# Without the calendar entry, the two posts still collapse into one.
only_ig = merged(ig1, ig2)
assert len(only_ig) == 1 and keys(only_ig[0].also) == ["instagram:p1"], keys(only_ig)
print("two posts of the same event merge without the calendar entry too")

# A named food beats a vague one, wherever it comes from.
named = hit("instagram", "p4", "@tuftsvsc", "VSC Coffee Shop", SAT_5PM, "51 Winthrop", "banh mi")
assert merged(jl, named)[0].verdict.food == "banh mi"
print("a post that names the food fills in the calendar's vague description")

# -- 2. things that must stay apart ----------------------------------------------------
apart = {
    "same title, same time, different clubs and places": (
        hit("instagram", "h1", "@tuftsjsa", "Halloween Party", SAT_5PM, "Campus Center"),
        hit("instagram", "h2", "@tuftsksa", "Halloween Party", SAT_5PM, "Hill Hall"),
    ),
    "different clubs in the same big building": (
        hit("instagram", "c1", "@tuftsjsa", "Onigiri Social", SAT_5PM, "Mayer Campus Center"),
        hit("email", "c2", "Tufts Hillel <hillel@tufts.edu>", "Shabbat Dinner", SAT_5PM,
            "Mayer Campus Center"),
    ),
    "same club, an hour apart, different events": (
        hit("instagram", "g1", "@tuftsvsc", "Pho Night", SAT_5PM - timedelta(hours=1), "Dewick"),
        ig2,
    ),
    "same club and title, a week apart": (
        ig2,
        hit("instagram", "w2", "@tuftsvsc", "VSC Coffee Shop Event", SAT_5PM + timedelta(days=7),
            "51 Winthrop"),
    ),
    "two JumboLife entries": (
        hit("jumbolife", "a@cg", "Vietnamese Students Club (VSC)", "Coffee Shop", SAT_5PM,
            calendar=True),
        hit("jumbolife", "b@cg", "Vietnamese Students Club (VSC)", "Coffee Shop", SAT_5PM,
            calendar=True),
    ),
    "a real calendar noon and an evening event": (
        hit("jumbolife", "lunch@cg", "Vietnamese Students Club (VSC)", "Lunar New Year Lunch",
            SAT_5PM.replace(hour=12), calendar=True),
        hit("instagram", "gala", "@tuftsvsc", "Lunar New Year Gala", SAT_5PM.replace(hour=19)),
    ),
    "same club and title, 40 minutes apart, different places": (
        hit("instagram", "m1", "@tuftsvsc", "Coffee Shop", SAT_5PM, "51 Winthrop"),
        hit("instagram", "m2", "@tuftsvsc", "Coffee Shop", SAT_5PM + timedelta(minutes=40),
            "Curtis Hall"),
    ),
}
for why, pair in apart.items():
    assert len(merged(*pair)) == 2, why
print(f"{len(apart)} look-alike pairs correctly kept apart")

# -- 3. things that should merge -----------------------------------------------------
together = {
    "co-hosted, same room, same time": (
        hit("instagram", "k1", "@tuftsjsa", "Japan Night", SAT_5PM, "Cabot 206"),
        hit("instagram", "k2", "@tuftsksa", "JSA x KSA Culture Night", SAT_5PM,
            "Cabot Center 206"),
    ),
    "same club, 30 minutes apart, similar titles": (
        hit("jumbolife", "night@cg", "Taiwanese Association of Students at Tufts (TAST)",
            "Night Market", SAT_5PM, "Dewick Lawn", calendar=True),
        hit("instagram", "t2", "@tasttufts", "TAST Night Market", SAT_5PM + timedelta(minutes=30),
            "Dewick Lawn"),
    ),
    "a post with a date but no time (noon stand-in)": (
        jl,
        hit("instagram", "n1", "@tuftsvsc", "VSC Coffee Shop", SAT_5PM.replace(hour=12)),
    ),
    "a newsletter and an Instagram post": (
        hit("email", "e1", "Tufts VSC <vsc@elist.tufts.edu>", "Coffee Shop this Saturday",
            SAT_5PM),
        ig2,
    ),
}
for why, pair in together.items():
    out = merged(*pair)
    assert len(out) == 1, why
print(f"{len(together)} genuine duplicates merged")

# The calendar's time wins over a post's, and over the noon stand-in.
assert merged(*together["same club, 30 minutes apart, similar titles"])[0].when == SAT_5PM
assert merged(*together["a post with a date but no time (noon stand-in)"])[0].when == SAT_5PM
# Between two posts, a real time beats the stand-in even when the stand-in leads.
noon = hit("instagram", "n2", "@tuftsvsc", "VSC Coffee Shop", SAT_5PM.replace(hour=12), conf=0.99)
assert merged(noon, ig2)[0].when == SAT_5PM
print("the most reliable start time is kept")

# A fuller spelling of the same place wins: the room number is worth keeping.
room = merged(hit("jumbolife", "r@cg", "Vietnamese Students Club (VSC)", "Coffee Shop", SAT_5PM,
                  "Mayer Campus Center", calendar=True),
              hit("instagram", "r2", "@tuftsvsc", "Coffee Shop", SAT_5PM, "Mayer Campus Center 012"))
assert room[0].where == "Mayer Campus Center 012", room[0].where

# -- 4. no chains: A matches B and B matches C, but A and C differ ----------------
a = hit("instagram", "a", "@tuftsvsc", "Coffee Shop", SAT_5PM, "51 Winthrop")
b = hit("instagram", "b", "@tuftsvsc", "Coffee Shop", SAT_5PM, "Curtis Hall 104")
c = hit("instagram", "c", "@tuftsjsa", "Movie Night", SAT_5PM, "Curtis Hall 104")
assert len(merged(a, b, c)) == 2
print("a chain of partial matches doesn't merge unrelated events")

# -- 5. undated listings are left alone, at the end ------------------------------
loose = hit("instagram", "u1", "@tuftsvsc", "VSC Coffee Shop", None)
out = merged(loose, ig1, ig2)
assert keys(out) == ["instagram:p2", "instagram:u1"], keys(out)
print("undated posts pass through untouched")

# -- 6. what the app and the report get ---------------------------------------------
d = hit_to_dict(coffee)
assert sorted(x["id"] for x in d["also"]) == ["instagram:p1", "instagram:p2"]
assert d["location"] == "51 Winthrop" and d["id"] == "jumbolife:vsc@campusgroups.com"
assert hit_to_dict(acm)["also"] == []

kt = (ROOT.parent / "mooch-android/app/src/main/java/com/mooch/data/Models.kt").read_text()
block = re.search(r"data class AlsoPosted\((.*?)\n\)", kt, re.S)
assert block, "the app has no AlsoPosted class"
kt_also = set(re.findall(r"va[lr] (\w+)\s*:", block.group(1)))
assert set(d["also"][0]) == kt_also, (set(d["also"][0]), kt_also)
print("feed 'also' entries match the app's AlsoPosted fields")

out_all = merged(ig1, jl, acm, ig2)
report = pathlib.Path(tempfile.mkdtemp(prefix="mooch-test-")) / "report.html"
page = write_html(out_all, TZ, report).read_text()
assert "https://example.com/p1" in page and "@tuftsvsc (Instagram)" in page
print_table(out_all, TZ)
print("report and terminal table show the merged listings")

print("\nALL DEDUPE CHECKS PASSED")
