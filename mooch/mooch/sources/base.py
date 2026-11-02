"""Every source returns a list of RawItem and swallows its own failures.

One broken source must never take down a run -- if Instagram bans the burner,
the newsletters should still come through.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from ..models import RawItem

log = logging.getLogger("mooch.sources")

_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = _WS.sub(" ", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Source:
    name = "base"

    def fetch(self, seen: set[str]) -> list[RawItem]:
        raise NotImplementedError

    def safe_fetch(self, seen: set[str]) -> list[RawItem]:
        try:
            items = self.fetch(seen)
            log.info("%s: %d new item(s)", self.name, len(items))
            return items
        except Exception as exc:  # noqa: BLE001 - deliberate: isolate source failures
            log.error("%s failed: %s", self.name, exc, exc_info=log.isEnabledFor(logging.DEBUG))
            return []
