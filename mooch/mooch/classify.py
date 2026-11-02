"""Decides whether an item is offering free food, and pulls out the details.

Uses a forced tool call rather than "reply in JSON" so the response shape is
guaranteed by the API instead of by the model's good intentions.
"""

from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import anthropic
from dateutil import parser as dateparser

from .models import RawItem, Verdict

log = logging.getLogger("mooch.classify")

PROMPT_VERSION = "p2-dates"  # bump when the prompt changes; recent items get re-screened

TOOL = {
    "name": "record_verdict",
    "description": "Record whether this item advertises free food at a specific event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "has_free_food": {
                "type": "boolean",
                "description": "True only if food or drink is being given away at no cost to attendees.",
            },
            "confidence": {
                "type": "number",
                "description": "0.0 to 1.0. How sure you are about has_free_food.",
            },
            "event_title": {
                "type": "string",
                "description": "Short name for the event, 8 words max. Empty if unclear.",
            },
            "food": {
                "type": "string",
                "description": "What food is offered, in a few words: 'pizza', 'boba and snacks'. Empty if unstated.",
            },
            "starts_at": {
                "type": "string",
                "description": (
                    "Local start time as YYYY-MM-DDTHH:MM. Resolve relative dates against "
                    "the posted date given in the prompt. Empty string if no date can be "
                    "determined. If a date is given but no time, use T12:00."
                ),
            },
            "location": {
                "type": "string",
                "description": "Where it happens, as written. Empty if unstated.",
            },
            "reason": {
                "type": "string",
                "description": "One short sentence explaining the call.",
            },
        },
        "required": ["has_free_food", "confidence", "reason"],
    },
}

SYSTEM = """\
You screen campus club announcements at Tufts University for one thing: free food \
that a student could show up and eat.

Count as free food:
- Food or drink provided at no cost to people who attend: pizza, boba, bagels, \
catered dinner, snacks, refreshments, coffee, donuts, cultural food nights.
- Phrases like "food provided", "lunch served", "refreshments available", \
"come hungry", "first 50 people get dinner".
- Free food that requires an RSVP, a sign-up, or club membership. Still free.

Do NOT count:
- Food being sold, including fundraisers and bake sales, even cheap ones. \
"$3 samosas" is not free food.
- Food drives, canned-goods donations, volunteering at a food pantry, or \
soup-kitchen service. The student gives food; they don't get it.
- Free things that are not food: t-shirts, tickets, stickers, tote bags.
- Restaurant discounts, coupons, BOGO deals, or promo codes.
- Generic recruiting copy with no event attached ("our meetings usually have \
snacks!"). If there is no identifiable occasion, has_free_food is false.
- Recaps of events that already happened.

On confidence: be well calibrated. An explicit "FREE PIZZA, Thursday 6pm, \
Tisch 304" is 0.95. A general body meeting whose description mentions food in \
passing is 0.6. A maybe is 0.4, and you should still report it with \
has_free_food true so a human can judge. Ambiguity between selling and giving \
away should pull confidence down, not up.

Dates: resolve every relative reference ("tomorrow", "this Friday", "tonight", \
"next week") against the posted date supplied with the item, and read the \
actual date off the "Upcoming days" table in the prompt rather than counting \
days yourself.

- "Monday", "this Monday" and "next Monday" all mean the FIRST Monday after \
the posted date. Never skip ahead to the Monday after that. This is how \
students write: "next Monday" posted on a Saturday means two days later.
- The only exception: if the post went up ON that weekday, "this Monday" \
means the same day and "next Monday" means seven days later.
- "Next week" with no day: leave starts_at empty unless a day is also given.
- Never guess a date that isn't implied by the text.
"""


def _prompt(item: RawItem, tz: ZoneInfo, max_chars: int) -> str:
    posted_local = item.posted_at.astimezone(tz)
    now_local = datetime.now(timezone.utc).astimezone(tz)

    # A ready-made lookup, so the model reads "Monday" off a table instead of
    # doing weekday arithmetic, which is where "next Monday" went wrong.
    days = [(posted_local + timedelta(days=i)).strftime("%A %B %d") for i in range(1, 15)]
    table = "\n".join(f"  {d}" + ("  <- first of this weekday after posting" if i < 7 else "")
                       for i, d in enumerate(days))

    parts = [
        f"Source: {item.source}",
        f"Posted: {posted_local.strftime('%A, %B %d %Y at %I:%M %p')}",
        f"Right now it is: {now_local.strftime('%A, %B %d %Y at %I:%M %p')}",
        f"Upcoming days after the post:\n{table}",
    ]
    if item.author:
        parts.append(f"Posted by: {item.author}")
    if item.title:
        parts.append(f"Title: {item.title}")
    if item.starts_at:
        local = item.starts_at.astimezone(tz)
        parts.append(
            "Event start time from the calendar (trust this over anything in "
            f"the text): {local.strftime('%A, %B %d %Y at %I:%M %p')}"
        )
    if item.location:
        parts.append(f"Location from the calendar: {item.location}")

    text = item.text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...truncated]"

    parts.append(f"\nContent:\n{text}")
    return "\n".join(parts)


def _to_utc(value: str, tz: ZoneInfo) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
    except (ValueError, OverflowError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


class Classifier:
    def __init__(self, api_key: str, model: str, tz: ZoneInfo, max_chars: int = 4000):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.tz = tz
        self.max_chars = max_chars

    def classify(self, item: RawItem) -> Verdict | None:
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                system=SYSTEM,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": "record_verdict"},
                messages=[{"role": "user", "content": _prompt(item, self.tz, self.max_chars)}],
            )
        except anthropic.APIError as exc:
            log.warning("API error on %s: %s", item.key(), exc)
            return None

        block = next((b for b in msg.content if b.type == "tool_use"), None)
        if block is None:
            log.warning("No tool_use block for %s", item.key())
            return None

        data = block.input
        return Verdict(
            has_free_food=bool(data.get("has_free_food")),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            event_title=(data.get("event_title") or "").strip() or None,
            food=(data.get("food") or "").strip() or None,
            starts_at=_to_utc(data.get("starts_at", ""), self.tz) or item.starts_at,
            location=(data.get("location") or "").strip() or item.location,
            reason=(data.get("reason") or "").strip() or None,
        )

    def classify_many(
        self, items: list[tuple[int, RawItem]], concurrency: int = 4
    ) -> list[tuple[int, Verdict]]:
        results: list[tuple[int, Verdict]] = []
        if not items:
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self.classify, item): item_id for item_id, item in items}
            for future in concurrent.futures.as_completed(futures):
                verdict = future.result()
                if verdict is not None:
                    results.append((futures[future], verdict))
        return results
