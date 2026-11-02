"""Mooch command line.

    mooch run          fetch everything, classify what's new, write the report
    mooch serve        run on a timer and serve the feed to the Android app
    mooch export       write events.json for the sync-a-file transport
    mooch list         show upcoming free food from what's already stored
    mooch report       rewrite the HTML report and open it
    mooch ig-login     one-time Instagram login to create the session file
    mooch test <src>   fetch one source and print what came back, no API calls
    mooch stats        how much is in the database
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from datetime import datetime, timedelta, timezone

from . import config as config_mod
from .db import Store
from .pipeline import build_sources, run_once, window


def _log_setup(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("public_request").setLevel(logging.WARNING)
    logging.getLogger("private_request").setLevel(logging.WARNING)


def cmd_run(cfg, args) -> int:
    log = logging.getLogger("mooch")
    store = Store(cfg.db_path)
    try:
        run_once(cfg, store)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    return _emit(cfg, store, open_browser=args.open)


def cmd_serve(cfg, args) -> int:
    import secrets

    from .server import Server, export_feed

    log = logging.getLogger("mooch")
    scfg = cfg.section("server")

    token = args.token or scfg.get("token") or ""
    if not token:
        token = secrets.token_urlsafe(18)
        log.warning("No server.token in config.yaml; generated one for this session.")

    store = Store(cfg.db_path)
    try:
        export_feed(cfg, store)
    finally:
        store.close()

    server = Server(
        cfg=cfg,
        host=args.host or scfg.get("host", "0.0.0.0"),
        port=args.port or int(scfg.get("port", 8765)),
        token=token,
        interval_minutes=args.interval or int(scfg.get("interval_minutes", 180)),
    )
    server.serve_forever()
    return 0


def cmd_export(cfg, args) -> int:
    from pathlib import Path

    from .server import export_feed

    store = Store(cfg.db_path)
    try:
        path = export_feed(cfg, store, Path(args.out) if args.out else None)
    finally:
        store.close()
    print(f"Wrote {path}")
    return 0


def cmd_explain(cfg, args) -> int:
    """Show what Mooch stored for posts matching some text, and optionally re-check them."""
    from .classify import PROMPT_VERSION, Classifier, _prompt

    store = Store(cfg.db_path)
    like = f"%{args.text}%"
    rows = store.conn.execute(
        "SELECT i.id, i.source, i.external_id, i.author, i.title, i.text, i.posted_at, i.starts_at, "
        "v.has_free_food, v.confidence, v.starts_at AS v_start, v.reason, v.model "
        "FROM items i LEFT JOIN verdicts v ON v.item_id = i.id "
        "WHERE i.text LIKE ? OR i.title LIKE ? OR i.author LIKE ? ORDER BY i.posted_at DESC LIMIT 5",
        (like, like, like),
    ).fetchall()
    if not rows:
        print(f"Nothing stored matches {args.text!r}.")
        return 1

    tz = cfg.timezone
    def local(v):
        from .db import _parse
        dt = _parse(v)
        return dt.astimezone(tz).strftime("%a %b %d %Y, %I:%M %p") if dt else "-"

    acfg = cfg.section("anthropic")
    model = acfg.get("model", "claude-haiku-4-5-20251001")
    for r in rows:
        print("=" * 72)
        print(f"{r['source']} | {r['author'] or ''} | {(r['title'] or r['text'])[:70]!r}")
        print(f"  posted:          {local(r['posted_at'])}")
        print(f"  judged as:       {'FREE FOOD' if r['has_free_food'] else 'not food' if r['has_free_food'] is not None else 'not checked yet'}"
              f"  ({r['confidence'] or 0:.0%})")
        print(f"  event date:      {local(r['v_start'])}")
        print(f"  checked with:    {r['model'] or '-'}  (current: {model}|{PROMPT_VERSION})")
        print(f"  reason:          {r['reason'] or '-'}")
        if args.rescreen:
            if not cfg.anthropic_key:
                print("  (can't re-check: ANTHROPIC_API_KEY is not set)")
                continue
            from .db import _row_to_item
            full = store.conn.execute("SELECT * FROM items WHERE id = ?", (r["id"],)).fetchone()
            it = _row_to_item(full)
            v = Classifier(cfg.anthropic_key, model, tz, int(acfg.get("max_chars", 4000))).classify(it)
            if v is None:
                print("  re-check failed (API error; see above)")
                continue
            store.save_verdict(r["id"], v, f"{model}|{PROMPT_VERSION}")
            print(f"  RE-CHECKED ->    {local(v.starts_at.isoformat() if v.starts_at else None)}  ({v.confidence:.0%}): {v.reason}")
    print("=" * 72)
    if not args.rescreen:
        print("Add --rescreen to check these again now with the current rules.")
    return 0


def cmd_list(cfg, args) -> int:
    store = Store(cfg.db_path)
    return _emit(cfg, store, open_browser=False, html=False)


def cmd_report(cfg, args) -> int:
    store = Store(cfg.db_path)
    return _emit(cfg, store, open_browser=True)


def _emit(cfg, store, open_browser: bool, html: bool = True) -> int:
    from .report import print_table, write_html

    since, until = window(cfg)
    hits = store.hits(cfg.confidence_threshold, since, until)
    print_table(hits, cfg.timezone)

    if html:
        path = write_html(hits, cfg.timezone, cfg.report_path, store.counts())
        print(f"Report: {path}")
        if open_browser:
            webbrowser.open(path.as_uri())
    return 0


def cmd_ig_login(cfg, args) -> int:
    from .sources.instagram import InstagramAuthError, login

    log = logging.getLogger("mooch")
    conf = cfg.section("instagram")
    try:
        login(conf, cfg.ig_password)
    except InstagramAuthError as exc:
        log.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Login failed: %s", exc)
        log.error(
            "If Instagram sent a challenge, open the app on your phone, approve the login, "
            "wait a few minutes, and try again."
        )
        return 1

    print("Session saved. You can clear MOOCH_IG_PASSWORD from .env if you like; "
          "Mooch only needs it again if the session expires.")
    return 0


def cmd_test(cfg, args) -> int:
    store = Store(cfg.db_path)
    sources = build_sources(cfg, store, only=args.source)
    if not sources:
        print(f"Source {args.source!r} is not enabled in config.yaml.")
        return 1

    for source in sources:
        items = source.safe_fetch(set())
        print(f"\n{source.name}: {len(items)} item(s)\n" + "-" * 60)
        for item in items[:10]:
            when = item.starts_at.astimezone(cfg.timezone).strftime("%Y-%m-%d %H:%M") if item.starts_at else "—"
            print(f"[{when}] {item.title or '(no title)'}  <{item.author or item.source}>")
            body = item.text.replace("\n", " ")
            print(f"    {body[:220]}{'...' if len(body) > 220 else ''}\n")
    return 0


def cmd_stats(cfg, args) -> int:
    store = Store(cfg.db_path)
    counts = store.counts()
    print(f"Database: {cfg.db_path}")
    print(f"  items stored     {counts['items']}")
    print(f"  classified       {counts['classified']}")
    print(f"  with free food   {counts['food']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mooch", description="Find free food on campus.")
    parser.add_argument("-c", "--config", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="fetch, classify, report")
    p_run.add_argument("--open", action="store_true", help="open the report when done")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="run on a timer and serve the feed to the app")
    p_serve.add_argument("--host", help="bind address (default 0.0.0.0)")
    p_serve.add_argument("--port", type=int, help="port (default 8765)")
    p_serve.add_argument("--token", help="shared secret the app must send")
    p_serve.add_argument("--interval", type=int, help="minutes between cycles (default 180)")
    p_serve.set_defaults(func=cmd_serve)

    p_export = sub.add_parser("export", help="write events.json")
    p_export.add_argument("-o", "--out", help="output path")
    p_export.set_defaults(func=cmd_export)

    p_explain = sub.add_parser("explain", help="show what Mooch stored for posts matching some text")
    p_explain.add_argument("text", help="words from the post, club or title, e.g. autumn")
    p_explain.add_argument("--rescreen", action="store_true", help="check the matches again now")
    p_explain.set_defaults(func=cmd_explain)

    sub.add_parser("list", help="print upcoming free food").set_defaults(func=cmd_list)
    sub.add_parser("report", help="rewrite and open the HTML report").set_defaults(func=cmd_report)
    sub.add_parser("ig-login", help="create the Instagram session file").set_defaults(func=cmd_ig_login)
    sub.add_parser("stats", help="database summary").set_defaults(func=cmd_stats)

    p_test = sub.add_parser("test", help="fetch one source without classifying")
    p_test.add_argument("source", choices=["jumbolife", "email", "instagram"])
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    _log_setup(args.verbose)

    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as exc:
        print(f"Config problem: {exc}", file=sys.stderr)
        return 1

    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
