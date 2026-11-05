# Mooch — engine

Watches the Tufts club events calendar, club newsletters, and club Instagram
accounts, and tells you where the free food is.

**Setting this up for the first time? Read [`../START-HERE.md`](../START-HERE.md) instead.** This
file is the reference: architecture, commands, config keys.

```
JumboLife ICS ─┐                              ┌─→ terminal table
Gmail label   ─┼─→ SQLite ─→ Claude ─→ hits ──┼─→ report.html
IG timeline   ─┘                              └─→ /api/events.json → Android app
```

Each source catches its own failures, so one breaking never takes down a run.
Items are deduplicated by source ID and verdicts are cached, so re-running is
free. When an item's content changes, its verdict is dropped and it gets
re-screened.

One event often has several listings: the JumboLife entry, the club's
Instagram post, a reminder post. Before anything is shown, listings of the same
event are merged into one, led by the most authoritative (JumboLife, then
newsletters, then Instagram), with the rest listed under `also`. Two listings
merge when they start on the same day, close together, and come from the same
club (`@tuftsvsc` matches "Vietnamese Students Club") or name the same room.
`mooch/dedupe.py` has the exact rules; they lean towards keeping events apart,
since a wrong merge would hide one.

## Commands

```
mooch run [--open]   fetch, classify, write the report
mooch serve          run on a timer and serve the feed to the phone app
mooch export [-o]    write events.json
mooch list           print upcoming free food from what's stored (no network)
mooch report         rewrite and open the HTML report
mooch test <source>  fetch one source and print it, no API calls
mooch ig-login       create the Instagram session file
mooch stats          database summary
mooch explain <text> show what was stored for matching posts; --rescreen re-checks them
mooch -v <cmd>       verbose
```

`-c path\to\config.yaml` overrides the config location.

## Layout

| File | Job |
|---|---|
| `mooch/cli.py` | Argument parsing and command dispatch |
| `mooch/pipeline.py` | The fetch → store → classify cycle, shared by `run` and `serve` |
| `mooch/config.py` | Merges `config.yaml` and `.env` into one object |
| `mooch/db.py` | SQLite: items, cached verdicts, per-source cursors |
| `mooch/classify.py` | The Claude call and the screening prompt |
| `mooch/dedupe.py` | Merges listings of the same event from different posts and sources |
| `mooch/report.py` | Terminal table and the HTML report |
| `mooch/server.py` | JSON feed, token auth, background scheduler |
| `mooch/sources/jumbolife.py` | CampusGroups iCalendar parsing |
| `mooch/sources/email_source.py` | IMAP over one Gmail label |
| `mooch/sources/instagram.py` | The burner's home timeline via instagrapi |
| `tests/` | Runnable checks, no network or API needed: `python tests/test_pipeline.py` and friends |

## Sources

**JumboLife** reads the public campus-wide iCalendar feed at
`https://tufts.campusgroups.com/ical/tufts/ical_tufts.ics`. No auth, no API
key. It 302s to a CDN, which `requests` follows. The parser absorbs several
CampusGroups quirks: quoted-printable `SUMMARY` values, gated placeholder
locations (`TBD`, `Sign in to download the location`), the `--- Event Details:`
footer appended to every description, and past events, which are dropped before
they reach the classifier. Club names come from `ORGANIZER;CN` combined with
the `club_acronym` category.

Multiple feeds can be listed under `jumbolife.feeds`. A signed-in personal feed
from the Subscribe dialog also carries members-only events for groups you
belong to; the public feed does not.

**Email** reads exactly one IMAP folder (a Gmail label) and tracks the highest
UID it has processed, so each run only pulls new mail. HTML bodies are reduced
to text with a small stdlib parser.

**Instagram** follows the clubs from a burner account and reads that account's
own home timeline — one request per cycle rather than one per club. That
collapses the request count and looks like a person opening the app, instead of
the profile-enumeration pattern Meta's trust scoring watches for. Stories are
deliberately not fetched: they trip rate limits faster, need OCR, and this tool
only cares about dated future events. `instagrapi` is an optional dependency
(`pip install -e ".[instagram]"`) and is imported only when this source runs.

## Config reference

`config.yaml`, copied from `config.example.yaml`:

| Key | Default | Meaning |
|---|---|---|
| `timezone` | `America/New_York` | Used for display and for resolving relative dates |
| `lookahead_days` | `14` | How far ahead the report and feed look |
| `history_days` | `30` | How far back the app's feed goes, for its past events |
| `confidence_threshold` | `0.55` | Verdicts below this are hidden |
| `data_dir` | `~/.mooch` | Database, report, `events.json`, IG session |
| `anthropic.model` | `claude-haiku-4-5-20251001` | Screening model |
| `anthropic.max_concurrency` | `4` | Parallel classification calls |
| `jumbolife.feeds` | campus-wide ICS | List; all are read and deduplicated |
| `email.folder` | `mooch` | The Gmail label to read |
| `instagram.active_hours` | `[8, 23]` | Local hours outside which IG is skipped |
| `instagram.delay_range` | `[3, 9]` | Random pause between IG requests, seconds |
| `instagram.timeline_pages` | `5` | Most feed pages to scroll per run |
| `instagram.max_post_age_days` | `10` | Ignore posts older than this |
| `server.port` | `8765` | Feed port |
| `server.interval_minutes` | `180` | Minutes between `serve` cycles |
| `server.token` | *(empty)* | Shared secret; `serve` generates one if unset |

Secrets live in `.env`: `ANTHROPIC_API_KEY`, `MOOCH_IMAP_PASSWORD`,
`MOOCH_IG_PASSWORD`.

## The feed

`GET /api/events.json` with `Authorization: Bearer <token>` (or `?token=`)
returns:

```json
{
  "version": 1,
  "generatedAt": "2026-09-18T05:26:43Z",
  "timezone": "America/New_York",
  "counts": {"items": 42, "classified": 42, "food": 9},
  "events": [
    {
      "id": "jumbolife:cbe7b53e@campusgroups.com",
      "title": "Night Market",
      "food": "boba and popcorn chicken",
      "startsAt": "2026-09-21T01:20:00Z",
      "location": "Mayer Campus Center",
      "author": "Taiwanese Association of Students at Tufts (TAST)",
      "source": "jumbolife",
      "url": "https://tufts.campusgroups.com/rsvp?id=400001",
      "confidence": 0.94,
      "reason": "Explicitly free.",
      "postedAt": "2026-09-16T05:26:43Z",
      "also": [
        {
          "id": "instagram:3471662083",
          "source": "instagram",
          "author": "@tasttufts",
          "url": "https://www.instagram.com/p/abc123/",
          "title": "TAST Night Market"
        }
      ]
    }
  ]
}
```

`also` lists the other listings of the same event that were merged into this
one; it's empty for most events. The event's own fields come from the lead
listing, except that the place and the food can come from another listing that
gives more detail.

Timestamps are UTC with a `Z` suffix and second precision, which is what
`java.time.Instant.parse` on the Android side accepts directly. `/health` is
open and unauthenticated. The feed also carries events from the last
`history_days`, so the app can show what already happened; events sort by start
time, oldest first, with undated hits last. The HTML report and `mooch list`
show only what's coming up.

The token stops someone else on campus wifi reading your feed; it is not real
security. Don't expose port 8765 to the internet — use Tailscale.
