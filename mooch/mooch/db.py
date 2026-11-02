"""SQLite store.

Two jobs: remember which items we've already seen so sources can be polled
repeatedly without duplicates, and cache classifier verdicts so we never pay
to classify the same post twice.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Hit, RawItem, Verdict

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    title         TEXT,
    author        TEXT,
    text          TEXT NOT NULL,
    url           TEXT,
    posted_at     TEXT NOT NULL,
    starts_at     TEXT,
    ends_at       TEXT,
    location      TEXT,
    fetched_at    TEXT NOT NULL,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS verdicts (
    item_id       INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    has_free_food INTEGER NOT NULL,
    confidence    REAL NOT NULL,
    event_title   TEXT,
    food          TEXT,
    starts_at     TEXT,
    location      TEXT,
    reason        TEXT,
    model         TEXT,
    classified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
CREATE INDEX IF NOT EXISTS idx_verdicts_food ON verdicts(has_free_food, starts_at);
"""


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- cursors ------------------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def seen_ids(self, source: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT external_id FROM items WHERE source = ?", (source,)
        ).fetchall()
        return {r["external_id"] for r in rows}

    # -- items --------------------------------------------------------------

    def add_items(self, items: list[RawItem]) -> int:
        """Insert new items. Returns how many were actually new.

        An item whose content hash changed (an edited event, a corrected
        time) has its verdict dropped so it gets reclassified.
        """
        now = _iso(datetime.now(timezone.utc))
        added = 0
        for it in items:
            existing = self.conn.execute(
                "SELECT id, content_hash FROM items WHERE source = ? AND external_id = ?",
                (it.source, it.external_id),
            ).fetchone()
            new_hash = it.content_hash()

            if existing:
                if existing["content_hash"] == new_hash:
                    continue
                self.conn.execute(
                    "UPDATE items SET content_hash=?, title=?, author=?, text=?, url=?, "
                    "posted_at=?, starts_at=?, ends_at=?, location=?, fetched_at=? WHERE id=?",
                    (
                        new_hash, it.title, it.author, it.text, it.url,
                        _iso(it.posted_at), _iso(it.starts_at), _iso(it.ends_at),
                        it.location, now, existing["id"],
                    ),
                )
                self.conn.execute("DELETE FROM verdicts WHERE item_id = ?", (existing["id"],))
                added += 1
                continue

            self.conn.execute(
                "INSERT INTO items (source, external_id, content_hash, title, author, text, "
                "url, posted_at, starts_at, ends_at, location, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    it.source, it.external_id, new_hash, it.title, it.author, it.text,
                    it.url, _iso(it.posted_at), _iso(it.starts_at), _iso(it.ends_at),
                    it.location, now,
                ),
            )
            added += 1
        self.conn.commit()
        return added

    def unclassified(self, tag: str | None = None) -> list[tuple[int, RawItem]]:
        """Items needing a verdict: never classified, or -- when `tag` is given --
        judged under an older prompt and still recent enough to matter."""
        if tag is None:
            rows = self.conn.execute(
                "SELECT i.* FROM items i LEFT JOIN verdicts v ON v.item_id = i.id "
                "WHERE v.item_id IS NULL ORDER BY i.posted_at DESC"
            ).fetchall()
        else:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            rows = self.conn.execute(
                "SELECT i.* FROM items i LEFT JOIN verdicts v ON v.item_id = i.id "
                "WHERE v.item_id IS NULL OR (COALESCE(v.model, '') != ? "
                "  AND i.posted_at >= ? AND (i.starts_at IS NULL OR i.starts_at >= ?)) "
                "ORDER BY i.posted_at DESC",
                (tag, _iso(now - timedelta(days=21)), _iso(now)),
            ).fetchall()
        return [(r["id"], _row_to_item(r)) for r in rows]

    # -- verdicts -----------------------------------------------------------

    def save_verdict(self, item_id: int, verdict: Verdict, model: str) -> None:
        self.conn.execute(
            "INSERT INTO verdicts (item_id, has_free_food, confidence, event_title, food, "
            "starts_at, location, reason, model, classified_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(item_id) DO UPDATE SET has_free_food=excluded.has_free_food, "
            "confidence=excluded.confidence, event_title=excluded.event_title, "
            "food=excluded.food, starts_at=excluded.starts_at, location=excluded.location, "
            "reason=excluded.reason, model=excluded.model, classified_at=excluded.classified_at",
            (
                item_id, int(verdict.has_free_food), verdict.confidence, verdict.event_title,
                verdict.food, _iso(verdict.starts_at), verdict.location, verdict.reason,
                model, _iso(datetime.now(timezone.utc)),
            ),
        )
        self.conn.commit()

    def hits(
        self,
        min_confidence: float,
        since: datetime,
        until: datetime,
        undated_max_age_days: int = 7,
    ) -> list[Hit]:
        """Upcoming free-food events, soonest first.

        `since`/`until` bound event start times. Items the model flagged but
        couldn't date are returned too, at the end, as long as they were
        posted recently -- "free bagels in Halligan" with no date is still
        worth seeing, but not a month later.
        """
        from datetime import timedelta

        undated_cutoff = datetime.now(timezone.utc) - timedelta(days=undated_max_age_days)
        rows = self.conn.execute(
            "SELECT i.*, v.has_free_food, v.confidence, v.event_title, v.food, "
            "v.starts_at AS v_starts_at, v.location AS v_location, v.reason "
            "FROM items i JOIN verdicts v ON v.item_id = i.id "
            "WHERE v.has_free_food = 1 AND v.confidence >= ?",
            (min_confidence,),
        ).fetchall()

        dated: list[Hit] = []
        undated: list[Hit] = []
        for r in rows:
            hit = Hit(item=_row_to_item(r), verdict=_row_to_verdict(r))
            when = hit.when
            if when is None:
                if hit.item.posted_at >= undated_cutoff:
                    undated.append(hit)
            elif since <= when <= until:
                dated.append(hit)

        dated.sort(key=lambda h: h.when)  # type: ignore[arg-type,return-value]
        undated.sort(key=lambda h: h.item.posted_at, reverse=True)
        return dated + undated

    def counts(self) -> dict[str, int]:
        total = self.conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
        classified = self.conn.execute("SELECT COUNT(*) c FROM verdicts").fetchone()["c"]
        food = self.conn.execute(
            "SELECT COUNT(*) c FROM verdicts WHERE has_free_food = 1"
        ).fetchone()["c"]
        return {"items": total, "classified": classified, "food": food}


def _row_to_item(r: sqlite3.Row) -> RawItem:
    return RawItem(
        source=r["source"],
        external_id=r["external_id"],
        text=r["text"],
        posted_at=_parse(r["posted_at"]) or datetime.now(timezone.utc),
        author=r["author"],
        title=r["title"],
        url=r["url"],
        starts_at=_parse(r["starts_at"]),
        ends_at=_parse(r["ends_at"]),
        location=r["location"],
    )


def _row_to_verdict(r: sqlite3.Row) -> Verdict:
    return Verdict(
        has_free_food=bool(r["has_free_food"]),
        confidence=r["confidence"],
        event_title=r["event_title"],
        food=r["food"],
        starts_at=_parse(r["v_starts_at"]),
        location=r["v_location"],
        reason=r["reason"],
    )
