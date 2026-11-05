<p align="center"><img src="docs/icon.png" width="112" alt="Mooch's apple mascot"></p>

# Mooch

Finds free food at Tufts. Mooch watches the JumboLife events calendar, club
newsletters and club Instagram accounts, asks Claude which posts are actually
giving food away, and puts the upcoming ones on your phone, days in advance.

```
JumboLife calendar ─┐                                  ┌─→ HTML report
Club newsletters   ─┼─→ engine on your laptop ─→ feed ─┤
Instagram feed     ─┘   (screens posts with Claude)    └─→ Android app
```

## What's in here

| Folder | What it is |
|---|---|
| [`mooch/`](mooch/) | The engine, in Python. Reads the sources, screens each post with Claude Haiku, keeps a SQLite database, and serves the results to the app. Runs on a laptop. |
| [`mooch-android/`](mooch-android/) | The Android app, in Kotlin and Jetpack Compose. A card feed and a month calendar of upcoming free food, with search, saved events, add-to-calendar and notifications. |
| [`START-HERE.md`](START-HERE.md) | Setup from scratch, step by step, for Windows. |

## Getting started

Follow [`START-HERE.md`](START-HERE.md). Getting the JumboLife calendar working
takes about 15 minutes and needs nothing but an Anthropic API key. Newsletters,
Instagram and the phone app are optional stages after that.

The engine's README covers its commands and every config setting:
[`mooch/README.md`](mooch/README.md). The app's covers how it's built:
[`mooch-android/README.md`](mooch-android/README.md).

## Tests

From the `mooch/` folder, with its dependencies installed:

```
python tests/test_jumbolife.py   # calendar feed parsing, using real CampusGroups entries
python tests/test_instagram.py   # Instagram feed scrolling, against a simulated feed
python tests/test_dedupe.py      # merging one event's listings from different sources
python tests/test_dates.py       # "next Monday" and other relative dates
python tests/test_pipeline.py    # database, screening, server and the app's data contract
```

None of them touch the network or call the API.

## Notes

- **Secrets stay out of git.** API keys and passwords go in `mooch/.env`, and
  personal settings in `mooch/config.yaml`. Both are in `.gitignore`; the repo
  only has the `.example` templates.
- **The Instagram source uses an unofficial API** (instagrapi) through a
  separate burner account. That's against Instagram's terms, and the account
  can get banned, which is why it's optional and off by default.
- **Running costs** are a few dollars a month at most in Anthropic API usage,
  and pennies with only the calendar turned on.
