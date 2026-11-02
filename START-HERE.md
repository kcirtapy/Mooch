# Mooch — setup, start to finish

Written for **Windows**, with Android Studio installed.

The commands below assume the project lives in your Documents folder:

```
%USERPROFILE%\Documents\Mooch
```

If you cloned it from GitHub somewhere else, adjust the `cd` paths to match. There are two folders inside it:

| Folder | What it is |
|---|---|
| `mooch` | The engine. Reads the sources, asks Claude what has free food, keeps a database, serves the results. Runs on your laptop. |
| `mooch-android` | The phone app. Reads what the engine produces. |

Work through the stages in order. **Stage 1 alone gives you a working tool** — JumboLife needs no configuration at all now, so you can stop after it and still have something useful. Each later stage adds a source or a convenience.

| Stage | What you get | Roughly |
|---|---|---|
| 1 | Working free-food list from every Tufts club calendar | 15 min |
| 2 | Club newsletters added | 10 min |
| 3 | Instagram added | 10 min + a week of waiting |
| 4 | Runs by itself | 5 min |
| 5 | The Android app on your phone | 30 min |

---

## Stage 1 — the engine

### 1.1 Python

You need Python 3.11 or newer. In a terminal (press <kbd>Win</kbd>, type `powershell`, Enter):

```powershell
python --version
```

If that reports 3.11+, skip ahead. If it opens the Microsoft Store or errors, install from [python.org/downloads](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"** on the first screen of the installer — it's easy to miss and everything else depends on it. Close and reopen the terminal afterward.

### 1.2 Install Mooch

```powershell
cd $HOME\Documents\Mooch\mooch
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Your prompt should now start with `(.venv)`. That's the virtual environment — a private copy of Python for this project, so Mooch's packages can't collide with anything else on your machine. **You need to run `.venv\Scripts\activate` again every time you open a new terminal.**

If PowerShell refuses to run the activate script ("running scripts is disabled on this system"), run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 1.3 Config files

```powershell
copy config.example.yaml config.yaml
copy .env.example .env
```

`config.yaml` holds settings. `.env` holds secrets and is gitignored. Both are yours to edit; the `.example` versions stay as reference.

### 1.4 Anthropic API key

Go straight to [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys) and click **Create key**. Name it `mooch`, set **Linked account** to yourself (not a service account), then copy the key immediately — it starts with `sk-ant-` and is only shown once.

Ignore anything about **Workload Identity Federation** or **service accounts**. Those are for servers in AWS, GCP or GitHub Actions to authenticate without storing a key. A script on your own laptop uses a plain API key.

Open `.env` in Notepad:

```powershell
notepad .env
```

Set the first line and save:

```
ANTHROPIC_API_KEY=sk-ant-...
```

**Cost:** screening runs on Claude Haiku 4.5, at about a fifth of a cent per item. With JumboLife alone that's pennies a week. With all three sources on it's roughly $2–5 a month, depending mostly on how broad your Gmail filter is. Buy the smallest credit amount the Console offers, leave auto-reload off, and set a monthly limit under **Settings → Limits** as a backstop. Verdicts are cached in SQLite, so re-running never pays twice for the same item.

### 1.5 Check the calendar feed

```powershell
mooch test jumbolife
```

This is the step that changed. You don't need DevTools, a JSON endpoint, or a field mapping — CampusGroups publishes a public iCalendar feed of every group's public events, and it's already in your config:

```
https://tufts.campusgroups.com/ical/tufts/ical_tufts.ics
```

You should see a list of upcoming events with dates, locations and hosting clubs. `test` only fetches and prints — it makes no API calls, so run it as often as you like while you're poking around.

### 1.6 First real run

```powershell
mooch run --open
```

Fetches the calendar, screens everything new through Claude, prints a table, writes an HTML report and opens it in your browser. The report lives at `C:\Users\<you>\.mooch\report.html`.

**Stage 1 is done.** You now have a working free-food list. Everything below is optional improvement.

---

## Stage 2 — newsletters

Worth doing: club listservs say "FREE BOBA" in the subject line where a calendar entry says "General Body Meeting." This is the source with the best signal and it can never break.

**The catch:** club mail arrives at your Tufts address, and Tufts email runs on Microsoft 365, which doesn't allow the simple password login Mooch uses to read mail. So the plan is to forward your Tufts mail to a Gmail account Mooch *can* read, and have Gmail file the club messages under one label.

### 2.1 Make a dedicated Gmail account

Create a new Gmail, something like `yourname.mooch@gmail.com`, rather than using your personal one. Two reasons:

- Tufts forwarding is all-or-nothing, so this account will receive a copy of *everything* sent to your Tufts address. Better that lands in an inbox you never read than doubling up in your personal one.
- The App Password in 2.4 grants mail access to the whole account. On a dedicated account, the worst a leaked one can expose is copies of Tufts mail.

### 2.2 Forward your Tufts mail to it

1. Go to [TuftsTools email forwarding](https://tuftstools.tufts.edu/cgi-bin/forward) and sign in with your Tufts username.
2. Enable forwarding and enter the new Gmail address.
3. Set **Save a copy of forwarded mail on the Tufts server?** to **Yes**.

That last setting matters: it keeps delivering to your normal Tufts inbox as well, so nothing about how you read Tufts mail changes.

### 2.3 A label and a filter in the new Gmail

1. **Settings → See all settings → Labels → Create new label**, name it `mooch`.
2. **Settings → Filters and Blocked Addresses → Create a new filter.**
3. In **Has the words**, paste:
   ```
   list:(elist.tufts.edu) OR from:(campusgroups.com)
   ```
4. **Create filter** → tick **Apply the label** → choose `mooch` → **Create filter**.

This catches Tufts Elist mailing lists (what most clubs use) and JumboLife announcements, without catching mail from your professors. Everything outside the label is ignored, so class and personal mail never gets sent to Claude or costs you anything.

Check it after a day or two. If a club email you know about isn't in the label, open it, click **⋮ → Filter messages like these**, and add whatever it has in common (its `from:` address or list name) to the filter with another `OR`. Some clubs use Google Groups or Mailchimp instead of Elists.

### 2.4 An App Password

Gmail won't accept the account password for this kind of access, so you'll make a separate App Password. Signed in as the new account:

1. Turn on 2-Step Verification: [myaccount.google.com/security](https://myaccount.google.com/security).
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create one, and copy the 16 characters.

In `.env`:

```
MOOCH_IMAP_PASSWORD=abcdefghijklmnop
```

It can be revoked on its own without changing your account password.

### 2.5 Turn it on

In `config.yaml`, find the `email:` block:

```yaml
email:
  enabled: true
  user: "yourname.mooch@gmail.com"
  folder: "mooch"
```

```powershell
mooch test email
```

You should see subject lines. Nothing has arrived yet if you only just set up forwarding, so give it a day. If it says it can't open the folder, check the label name matches exactly.

---

## Stage 3 — Instagram

Read this whole stage before doing any of it; the order matters more than the commands.

### 3.1 Install the extra dependency

```powershell
pip install -e ".[instagram]"
```

This is a separate step because `instagrapi` has a big dependency tree that occasionally wants a C compiler on Windows. Keeping it out of the base install means a failure here can't break Stages 1 and 2.

### 3.2 Make the burner and let it age

Create the account **on your phone**, on cellular or home wifi. Then use it like a person for about a week: browse, like things, follow some large accounts.

This waiting is the part people skip and then wonder why they get banned. A day-old account that immediately follows forty clubs and starts making API calls gets flagged fast. A week-old account doing the same thing mostly doesn't.

### 3.3 Follow the clubs, gradually

Ten or so a day over several days. **The follow list is the source list** — Mooch reads the burner's home timeline, so whatever it follows is what gets watched. There's no list of handles in the config; to add a club later, just follow it from the app.

Search Instagram for "tufts" plus your interests, and check who the big accounts follow. From the JumboLife org list, the groups that reliably feed people: cultural and identity groups, religious groups, and professional societies.

### 3.4 Log in once

In `config.yaml`:

```yaml
instagram:
  enabled: true
  username: "your_burner_handle"
```

Put the password in `.env` as `MOOCH_IG_PASSWORD=...`, then:

```powershell
mooch ig-login
```

That writes a session file to `C:\Users\<you>\.mooch\ig_session.json` and reuses it from then on. Repeated fresh logins are the fastest way to get challenged, so the session file is the normal path — you can delete the password from `.env` after this.

If Instagram throws a challenge, open the app on your phone, approve the login there, wait a few minutes, and run `ig-login` again.

```powershell
mooch test instagram
```

### 3.5 Keeping it alive

The defaults handle most of this: random 3–9 second pauses between requests, nothing outside 8am–11pm, and one timeline read per cycle instead of forty profile fetches. Two things are on you:

- **Run it from this laptop, not a cloud server.** Datacenter IPs are treated very differently from residential ones. Identical code that works here will start failing from a VPS.
- **Don't shorten the poll interval.** It's set to 3 hours, which is plenty for events posted days ahead.

Assume the account dies eventually. When it does: make a new one, warm it up, follow the clubs, delete `ig_session.json`, run `ig-login` again. Nothing else changes.

---

## Stage 4 — make it run by itself

`mooch serve` runs the pipeline on a timer **and** serves the results to the phone app. It replaces any need for a scheduled task.

### 4.1 Set a permanent token

Otherwise `serve` generates a random one at every startup and the phone stops matching.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(18))"
```

Paste it into `config.yaml`:

```yaml
server:
  token: "the-string-it-printed"
```

### 4.2 Start it

Double-click **`serve.bat`** in the `mooch` folder, or:

```powershell
mooch serve
```

It prints the address and token to give the phone:

```
Serving on http://192.168.1.40:8765/api/events.json
Token required. Put this in the app's Settings: xY3k...
```

**Windows Firewall will pop up the first time.** Tick **Private networks** and allow it, or the phone won't be able to connect. If you dismissed it by accident, re-run and it'll ask again, or add the rule manually under Windows Defender Firewall → Allow an app.

Leave the window open and minimised. Closing it stops Mooch.

### 4.3 Start it automatically at login

Press <kbd>Win</kbd>+<kbd>R</kbd>, type `shell:startup`, Enter. That opens your Startup folder. Right-drag `serve.bat` into it and choose **Create shortcuts here**.

Now Mooch starts whenever you log in. To have it start minimised: right-click the shortcut → **Properties** → **Run: Minimized**.

Note that this only runs while the laptop is awake. If it sleeps, the phone shows the last list it received, marked stale. For events days out, that's fine.

---

## Stage 5 — the Android app

### 5.1 Build it

1. Open Android Studio → **File → Open** → select the **`mooch-android`** folder (the one containing `settings.gradle.kts`, not the parent).
2. It will offer to download SDK components and create the Gradle wrapper. Accept everything.
3. Wait for the first Gradle sync. Several minutes, and it downloads a lot.
4. If it complains about plugin versions, take its one-click upgrade suggestion, or edit `gradle/libs.versions.toml` and bump `agp` / `kotlin` to what it recommends.

To put it on your phone: enable developer mode (**Settings → About phone → tap Build number seven times → Developer options → USB debugging**), plug in via USB, pick the device in the toolbar dropdown, press **Run**.

For a sideloadable file instead: **Build → Build Bundle(s)/APK(s) → Build APK(s)**. It lands in `mooch-android\app\build\outputs\apk\debug\`.

### 5.2 Connect it

Open the app → **Settings** (gear, top right) → enter:

- **Server address:** what `serve` printed, e.g. `192.168.1.40:8765`. Just the host and port is fine; the app fills in the rest.
- **Token:** the one from `config.yaml`.

Tap **Save and reconnect**. On success it tells you how many events came through.

If you don't know your laptop's address, run `ipconfig` and look for **IPv4 Address** under your wifi adapter.

### 5.3 Reaching the laptop from off campus

The address field takes anything, so all three of these work with the same build:

| | Address | Works when |
|---|---|---|
| Campus wifi | `192.168.1.40:8765` | Both devices on the same network |
| **Tailscale** | `100.x.y.z:8765` | Anywhere, both signed into your tailnet |
| Hosted file | `https://.../events.json` | Anywhere; laptop pushes `mooch export` output somewhere |

**I'd use Tailscale.** Tufts_Secure and most campus networks isolate clients from each other, so laptop-to-phone over campus wifi may simply not work no matter what you configure. Tailscale is free for personal use, takes five minutes on both devices, and means you expose nothing to the open internet. Install it on both, then use the laptop's tailnet IP as the server address. Nothing else changes.

---

## Day-to-day

```powershell
mooch run          # one-off: fetch, classify, report
mooch serve        # loop on a timer and serve the phone
mooch list         # print what's stored, no network
mooch report       # rewrite and open the HTML report
mooch export       # write events.json
mooch test <src>   # fetch one source and print it, no API calls
mooch stats        # how much is in the database
mooch -v run       # verbose, for when something misbehaves
```

Re-running is always safe: items are deduplicated by source ID and verdicts are cached, so you never pay twice for the same event. If an event's details change, its verdict is dropped and it gets re-screened.

**Tuning.** `confidence_threshold` in `config.yaml` starts at `0.55`, which lets some maybes through. Every uncertain hit shows the model's reasoning, so after a week you'll know whether to raise it (too much noise) or lower it (missing things). The screening prompt is in `mooch\classify.py` — it already knows bake sales aren't free food, food drives are the opposite, and free t-shirts aren't food. If you spot a pattern it keeps getting wrong, add a line to the `SYSTEM` string.

**A better JumboLife feed.** Sign in to JumboLife, go to **Events → Subscribe**, star the groups you care about, and copy **"Your Personal Feed of Events."** That feed also includes members-only events for groups you belong to, which the public feed omits. Add it as a second entry under `jumbolife.feeds:` — Mooch reads every feed listed and deduplicates across them.

---

## When something breaks

**`mooch: command not found`** — the venv isn't active. Run `.venv\Scripts\activate`.

**`No config at ...`** — you skipped 1.3. `copy config.example.yaml config.yaml`.

**JumboLife returns nothing** — check for a redirect to a sign-in page, which means the URL needs a token. Re-copy the public feed URL from the Subscribe dialog. A personal feed's token does expire; the campus-wide one doesn't.

**Email: "Can't open IMAP folder"** — the Gmail label name must match exactly, and a nested label `clubs/mooch` is the folder `clubs/mooch`.

**Instagram: `LoginRequired` / `ChallengeRequired`** — the session went stale. Delete `ig_session.json`, put the password back in `.env`, run `mooch ig-login`. If it keeps happening, the account is burnt; make a new one.

**Instagram returns nothing but no error** — the burner isn't following anyone yet, or the posts it sees are image-only. Mooch skips captionless posts since there's nothing to read without vision.

**Phone: "Can't reach the laptop"** — is `serve.bat` running? Is the laptop awake? Did you allow the firewall prompt on private networks? Campus wifi client isolation is the most common cause; try Tailscale.

**Phone: "Server rejected the token"** — it doesn't match `server.token` in `config.yaml`. If you never set one, `serve` made a random one that changed on restart. See 4.1.

**Phone connects but the list is empty** — the laptop has nothing to show, which isn't a connection problem. Check with `mooch list`.

**No notifications** — check the toggle in the app's Settings, then Android's own: **App info → Notifications**, and **App info → Battery → Unrestricted**. Samsung and Xiaomi battery optimisation will silently kill periodic work. Note the app checks every 3 hours, not instantly — events are registered days ahead, so that's the tradeoff for battery.

**Everything scores as not-food** — run `mooch -v run` and look for API errors. If the calls are succeeding, it's a source problem, not a classifier problem: run `mooch test jumbolife` and see whether the text coming in actually mentions food.
