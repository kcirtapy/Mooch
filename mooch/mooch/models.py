"""Data shapes passed between sources, the classifier, and the report."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawItem:
    """One thing a source found: an email, a post, a calendar entry.

    Every datetime is timezone-aware UTC. `posted_at` matters more than it
    looks -- the classifier uses it to resolve relative dates like "tomorrow"
    or "this Friday" that show up constantly in club posts.
    """

    source: str  # "jumbolife" | "email" | "instagram"
    external_id: str  # stable id within that source
    text: str  # what gets classified
    posted_at: datetime
    author: str | None = None  # club name or IG handle
    title: str | None = None
    url: str | None = None

    # Structured hints, when the source already knows them. JumboLife fills
    # these in; email and Instagram almost never can.
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None

    def key(self) -> str:
        return f"{self.source}:{self.external_id}"

    def content_hash(self) -> str:
        blob = "\n".join(
            filter(None, [self.title, self.author, self.text, self.location])
        )
        return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


@dataclass
class Verdict:
    """What the model concluded about one item."""

    has_free_food: bool
    confidence: float
    event_title: str | None = None
    food: str | None = None
    starts_at: datetime | None = None  # UTC
    location: str | None = None
    reason: str | None = None


@dataclass
class Hit:
    """A classified item that made the cut, ready to display."""

    item: RawItem
    verdict: Verdict

    @property
    def when(self) -> datetime | None:
        return self.verdict.starts_at or self.item.starts_at

    @property
    def where(self) -> str | None:
        return self.verdict.location or self.item.location

    @property
    def name(self) -> str:
        return self.verdict.event_title or self.item.title or "Untitled event"
