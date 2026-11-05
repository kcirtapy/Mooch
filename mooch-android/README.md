# Mooch for Android

The phone client. Your laptop does the scraping and screening; this reads what
it produces and puts it on your home screen.

**Setting this up for the first time? Read [`../START-HERE.md`](../START-HERE.md) instead**, which
covers the laptop side too. This file is the reference.

```
laptop:  mooch serve ──→ http://laptop:8765/api/events.json
phone:   Mooch app ──── polls it, caches it, notifies you
```

Nothing sensitive lives on the phone. The Anthropic key, the Instagram session
and your Gmail app password all stay on the laptop — the app only ever sees a
list of events and a shared token.

## Build

Android Studio (Ladybug or newer) → **File → Open** → this folder, the one with
`settings.gradle.kts`. Accept the SDK and Gradle-wrapper prompts, wait for the
first sync, then **Run**. For a sideloadable file: **Build → Build Bundle(s)/APK(s)
→ Build APK(s)**, output in `app\build\outputs\apk\debug\`.

`minSdk` is 26 (Android 8.0), `targetSdk` 35. Kotlin 2.1, Compose BOM 2024.12,
Material 3.

## How it's put together

| File | Job |
|---|---|
| `MainActivity.kt` | Home and Settings tabs, the shared bottom bar, the notification-permission ask |
| `MoochApp.kt` | Creates the notification channel, schedules the sync worker |
| `data/Models.kt` | `@Serializable` mirrors of the feed, plus date formatting and day grouping |
| `data/MoochApi.kt` | OkHttp fetch, offline cache, human-readable error mapping |
| `data/Settings.kt` | DataStore: server URL, token, toggles, saved events, already-notified IDs |
| `ui/BottomBar.kt` | Home tab, the round refresh button, Settings tab; on every screen |
| `ui/CalendarView.kt` | Month grid with a dot on each day that has food; tap a day for its events |
| `ui/EventListScreen.kt` | Search, All/Saved tabs, event cards, filter and detail sheets, bottom bar |
| `ui/SettingsScreen.kt` | Connection, alerts, appearance (light/dark), confidence floor |
| `ui/MainViewModel.kt` | State, refresh, settings mutations |
| `ui/theme/Theme.kt` | Icon-cream canvas, apple-red accent, warm dark mode, type scale |
| `work/SyncWorker.kt` | Periodic fetch and the notification builder |

## Using it

Events are white cards, grouped under day headings, soonest first. Each card
leads with the food on a red-tinted band, the hosting club in a chip, then the
time, a countdown, and the place in bold, since that's where you're going.

- **Search** filters by food, club, place or title as you type.
- **The filter button** in the search bar turns sources (JumboLife, newsletters,
  Instagram) on and off. A red dot means some are hidden.
- **All events / Saved.** Tap the bookmark on any card to save it. Saved events
  are kept on the phone and survive restarts.
- **The calendar button**, at the right of All events / Saved, switches between
  the list and a month grid with a dot on every day that has food. Tap a day to
  see its events. Past days keep their dots, dimmed.
- **Past events** are folded away at the bottom of the list, newest first; tap
  the heading to open them. The laptop sends the last 30 days (`history_days`
  in its config).
- **Tap a card** for the details sheet: full time, place, club, how sure Mooch
  is, and buttons to **add it to your calendar** or open the original post.
  When an event was posted in several places, the laptop merges them into one
  card and the sheet lists the other posts under **Also posted by**.
- **The bottom bar** is on every screen: Home, the round button that checks the
  laptop for new finds, and Settings. Tapping Home while already home jumps back
  to the top of all events. Pulling down on the list also refreshes.

Events Mooch wasn't sure about carry an amber "Maybe" note with the model's
reasoning, so you can judge for yourself.

**Notifications** check every 3 hours. Club events are registered days ahead, so
there's nothing to gain from polling harder, and 3 hours is comfortably above
WorkManager's 15-minute floor — Doze deferring a run by a few minutes doesn't
matter. Opening the app always pulls fresh. Each event notifies only once.

To change the interval, edit `INTERVAL_HOURS` in `work/SyncWorker.kt`, then
toggle notifications off and on in Settings — the scheduler uses `KEEP`, so an
existing schedule isn't replaced just because the app relaunched.

**The confidence slider** hides low-confidence finds on top of whatever
threshold the laptop already applies. Useful for tightening things without
touching `config.yaml` or rebuilding.

When the laptop is asleep or off-network, the app shows the last list it
received, marked stale, rather than going blank.

## Connecting

The address field accepts a bare `host:port`, a full URL, or a URL ending in
`.json`, and fills in the scheme and `/api/events.json` as needed. So campus
wifi, a Tailscale address, and a hosted `events.json` all work with the same
build — change it in Settings, no rebuild.

Tailscale is the one to use: campus networks commonly isolate clients from each
other, which breaks laptop-to-phone traffic no matter how it's configured.

`network_security_config.xml` permits cleartext HTTP, because the laptop serves
plain HTTP and `<domain>` rules match hostnames, not IP ranges — there's no way
to scope it to "my LAN". If you ever put the server behind HTTPS, set
`cleartextTrafficPermitted` to false.

## Troubleshooting

See the last section of [`../START-HERE.md`](../START-HERE.md).
