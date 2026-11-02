"""Serves the results to the Android app.

Deliberately small: stdlib HTTP, a shared-secret token, and a background thread
that re-runs the pipeline on a timer. One user, one laptop -- there is no reason
for a web framework here.

Two ways the phone can reach it, both served by the same code:
  - directly, over campus wifi or a Tailscale address
  - indirectly, by syncing the file `mooch export` writes to somewhere hosted
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .db import Store
from .models import Hit
from .pipeline import run_once, window

log = logging.getLogger("mooch.server")

FEED_VERSION = 1


def _iso(dt: datetime | None) -> str | None:
    """ISO-8601 with a Z suffix and second precision.

    java.time.Instant.parse on the Android side wants a trailing Z; it rejects
    "+00:00". The app has a fallback parser, but emitting the form it prefers
    keeps the common path fast.
    """
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hit_to_dict(hit: Hit) -> dict:
    return {
        "id": hit.item.key(),
        "title": hit.name,
        "food": hit.verdict.food,
        "startsAt": _iso(hit.when),
        "location": hit.where,
        "author": hit.item.author,
        "source": hit.item.source,
        "url": hit.item.url,
        "confidence": round(hit.verdict.confidence, 3),
        "reason": hit.verdict.reason,
        "postedAt": _iso(hit.item.posted_at),
    }


def build_feed(cfg, store: Store) -> dict:
    since, until = window(cfg)
    hits = store.hits(cfg.confidence_threshold, since, until)
    return {
        "version": FEED_VERSION,
        "generatedAt": _iso(datetime.now(timezone.utc)),
        "timezone": str(cfg.timezone),
        "counts": store.counts(),
        "events": [hit_to_dict(h) for h in hits],
    }


def export_feed(cfg, store: Store, path: Path | None = None) -> Path:
    """Write the feed to disk, for the sync-a-file transport."""
    path = path or (cfg.data_dir / "events.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_feed(cfg, store), indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    server_version = "Mooch/0.1"
    cfg = None
    token = ""
    db_path = None
    lock = threading.Lock()

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, code: int, payload: dict, extra_headers: dict | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, query: dict) -> bool:
        if not self.token:
            return True
        supplied = ""
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            supplied = header[7:].strip()
        elif "token" in query:
            supplied = query["token"][0]
        return hmac.compare_digest(supplied, self.token)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send(200, {"ok": True, "version": FEED_VERSION})
            return

        if parsed.path not in ("/api/events.json", "/api/events"):
            self._send(404, {"error": "not found"})
            return

        if not self._authorized(query):
            self._send(401, {"error": "bad or missing token"})
            return

        # SQLite connections are per-thread, so open one for this request.
        with self.lock:
            store = Store(self.db_path)
            try:
                feed = build_feed(self.cfg, store)
            finally:
                store.close()

        self._send(200, feed)


class Server:
    def __init__(self, cfg, host: str, port: int, token: str, interval_minutes: int):
        self.cfg = cfg
        self.host = host
        self.port = port
        self.token = token
        self.interval = max(5, int(interval_minutes)) * 60
        self._stop = threading.Event()

        handler = type("BoundHandler", (_Handler,), {
            "cfg": cfg, "token": token, "db_path": cfg.db_path,
        })
        self.httpd = ThreadingHTTPServer((host, port), handler)

    def _scheduler(self) -> None:
        """Runs the pipeline on a timer, in its own thread with its own Store."""
        while not self._stop.is_set():
            store = Store(self.cfg.db_path)
            try:
                summary = run_once(self.cfg, store)
                log.info("Cycle done: %s", summary)
                export_feed(self.cfg, store)
            except Exception as exc:  # noqa: BLE001 - never kill the scheduler
                log.error("Cycle failed: %s", exc)
            finally:
                store.close()
            self._stop.wait(self.interval)

    def serve_forever(self) -> None:
        threading.Thread(target=self._scheduler, daemon=True, name="mooch-scheduler").start()
        shown = self.host if self.host not in ("", "0.0.0.0") else _lan_ip()
        log.info("Serving on http://%s:%d/api/events.json", shown, self.port)
        if self.token:
            log.info("Token required. Put this in the app's Settings: %s", self.token)
        else:
            log.warning("No token set -- anyone on this network can read your feed.")
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Shutting down")
        finally:
            self._stop.set()
            self.httpd.server_close()


def _lan_ip() -> str:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
