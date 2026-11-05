"""Folds several listings of one event into a single entry.

The same event often turns up more than once: on the JumboLife calendar, in
the club's Instagram post, and again in a reminder post a few days later. Each
listing is screened on its own, so without this step each becomes its own card.

Two listings count as the same event when they start on the same day, close
together, and something else ties them:

- the same club. An Instagram handle like @tuftsvsc matches "Vietnamese
  Students Club" through its initials, and @tasttufts matches "(TAST)".
- the same specific place, one with a number in it ("51 Winthrop", "Halligan
  102"), at the same start time.
- the same general place ("Mayer Campus Center") at the same time, with
  clearly similar titles.

When in doubt, listings stay separate: a duplicate card is a nuisance, but a
wrong merge hides an event. Two JumboLife entries are never merged with each
other, since the calendar already lists each event once.

The merged entry keeps the most authoritative listing's id, title, link and
time (JumboLife, then newsletters, then Instagram), takes the place or the food
from another listing when that one says more, and lists the rest under `also`.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from functools import lru_cache

from .models import Hit

# Listings this many minutes apart or less start "at the same time".
SAME_TIME_MIN = 15
# The same club's listings with similar titles may disagree by this much,
# like "doors at 5:30" against a 5:00 calendar entry.
NEAR_TIME_MIN = 90
# Share of the shorter title's words the other must also use to be "similar".
SIMILAR_TITLES = 0.5

# Most authoritative first: JumboLife has structured times and official titles.
SOURCE_RANK = {"jumbolife": 0, "email": 1, "instagram": 2}

_TITLE_STOP = {
    "a", "an", "and", "the", "of", "at", "for", "with", "in", "on", "to", "by",
    "from", "our", "your", "event", "events", "tufts", "club", "university",
    "presents", "annual", "night", "day", "meeting",
}
_ORG_STOP = {"a", "an", "and", "the", "of", "at", "for", "in", "on"}
# Words that say nothing about which club it is.
_NOT_A_CLUB = {
    "tufts", "tuftsuniversity", "university", "jumbolife", "campusgroups",
    "instagram", "newsletter", "club", "clubs", "student", "students",
    "association", "society", "council", "union", "community", "office",
}
_PLACE_STOP = {
    "the", "room", "rm", "st", "street", "ave", "avenue", "rd", "road", "tufts",
    "university", "building", "bldg", "floor", "fl", "at", "in", "of", "and",
}
# The screener sometimes says this instead of leaving the food blank.
_VAGUE_FOOD = re.compile(
    r"\b(unspecified|not (?:yet )?(?:specified|stated|mentioned|listed)|unknown|unclear|"
    r"tbd|tba|tbc|promised)\b",
    re.IGNORECASE,
)


def merge_duplicates(hits: list[Hit], tz) -> list[Hit]:
    """`hits` with duplicate listings folded together, soonest first.

    Undated hits pass through untouched, at the end: with no date there is
    nothing safe to match them on.
    """
    dated = sorted((h for h in hits if h.when is not None), key=lambda h: h.when)
    undated = [h for h in hits if h.when is None]

    linked: set[tuple[int, int]] = set()
    for i, a in enumerate(dated):
        for j in range(i + 1, len(dated)):
            b = dated[j]
            if (b.when - a.when).total_seconds() > 24 * 3600:
                break
            if same_event(a, b, tz):
                linked.add((i, j))

    # Group, requiring every listing in a group to match every other one, so a
    # chain of loose resemblances can't drag unrelated events together.
    owner = list(range(len(dated)))
    groups = {i: [i] for i in range(len(dated))}
    for i, j in sorted(linked):
        gi, gj = owner[i], owner[j]
        if gi == gj:
            continue
        if all((min(x, y), max(x, y)) in linked for x in groups[gi] for y in groups[gj]):
            for x in groups[gj]:
                owner[x] = gi
            groups[gi].extend(groups.pop(gj))

    merged = [_combine([dated[k] for k in sorted(members)], tz) for members in groups.values()]
    merged.sort(key=lambda h: h.when)
    return merged + undated


def same_event(a: Hit, b: Hit, tz) -> bool:
    """Whether two screened listings describe one event. See the module docstring."""
    if a.item.source == "jumbolife" and b.item.source == "jumbolife":
        return False
    if a.when is None or b.when is None:
        return False
    la, lb = a.when.astimezone(tz), b.when.astimezone(tz)
    if la.date() != lb.date():
        return False

    gap = abs((a.when - b.when).total_seconds()) / 60
    club = same_club(a.item.author, b.item.author)
    place = _place_match(a.where, b.where)
    similar = _title_similarity(a.name, b.name) >= SIMILAR_TITLES

    if gap <= SAME_TIME_MIN:
        return club or place == "specific" or (place == "general" and similar)

    # Further apart, or one listing's time is only the screener's noon stand-in
    # for "a date but no time": only the same club with a similar title, in a
    # place that doesn't contradict the other, will do.
    if gap <= NEAR_TIME_MIN or _noon_guess(a, la) or _noon_guess(b, lb):
        conflict = place is None and bool(_place_tokens(a.where)) and bool(_place_tokens(b.where))
        return club and similar and not conflict
    return False


def same_club(a: str | None, b: str | None) -> bool:
    ka, kb = club_keys(a), club_keys(b)
    if ka & kb:
        return True
    # A handle that spells out part of a name: @tuftsvietnamese and
    # "Vietnamese Students Club".
    return any(len(x) >= 5 and len(y) >= 5 and (x in y or y in x) for x in ka for y in kb)


@lru_cache(maxsize=2048)
def club_keys(author: str | None) -> frozenset[str]:
    """Spellings of a club's identity that two listings can share.

    "@tuftsvsc" gives {"tuftsvsc", "vsc"}, and "Vietnamese Students Club"
    gives its initials "vsc" along with the run-together name.
    """
    if not author:
        return frozenset()
    text = author.strip().lower()
    keys: set[str] = set()

    # Newsletters: "Tufts VSC <vsc@elist.tufts.edu>".
    for local in re.findall(r"([a-z0-9._+-]+)@[a-z0-9-]+(?:\.[a-z0-9-]+)+", text):
        _add_handle(keys, local)
    text = re.sub(r"\S+@\S+\.\S+", " ", text).strip()

    if text.startswith("@") or (text and " " not in text):
        _add_handle(keys, text)
    elif text:
        for inner in re.findall(r"\(([^)]*)\)", text):
            _add(keys, inner)
        words = re.findall(r"[a-z0-9]+", re.sub(r"\([^)]*\)", " ", text))
        content = [w for w in words if w not in _ORG_STOP]
        for ws in (content, [w for w in content if w not in ("tufts", "university")]):
            _add(keys, "".join(ws))
            _add(keys, "".join(w[0] for w in ws))
    return frozenset(keys)


def _add(keys: set[str], raw: str) -> None:
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if len(key) >= 3 and key not in _NOT_A_CLUB:
        keys.add(key)


def _add_handle(keys: set[str], handle: str) -> None:
    key = re.sub(r"[^a-z0-9]", "", handle.lower())
    _add(keys, key)
    _add(keys, re.sub(r"^tufts|tufts$", "", key))  # @tuftsvsc -> vsc, @tasttufts -> tast


def _title_tokens(title: str | None) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", (title or "").lower()):
        if len(w) < 2 or w in _TITLE_STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def _title_similarity(a: str | None, b: str | None) -> float:
    """Share of the shorter title's words that the other title also has."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _place_tokens(place: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (place or "").lower()) if w not in _PLACE_STOP}


def _place_match(a: str | None, b: str | None) -> str | None:
    """"specific" or "general" when two places agree, otherwise None."""
    ta, tb = _place_tokens(a), _place_tokens(b)
    if not ta or not tb:
        return None
    if not (ta <= tb or tb <= ta or len(ta & tb) / len(ta | tb) >= 0.6):
        return None
    return "specific" if any(_has_digit(w) for w in ta & tb) else "general"


def _has_digit(text: str | None) -> bool:
    return any(c.isdigit() for c in text or "")


def _noon_guess(hit: Hit, local: datetime) -> bool:
    """The screener puts a post that gives a date but no time at 12:00. A
    calendar entry's noon is real, so only screener-made times count."""
    return hit.item.starts_at is None and local.hour == 12 and local.minute == 0


# -- building the merged entry ----------------------------------------------------


def _authority(hit: Hit):
    return (SOURCE_RANK.get(hit.item.source, 9), -hit.verdict.confidence, hit.item.posted_at)


def _combine(group: list[Hit], tz) -> Hit:
    if len(group) == 1:
        return group[0]
    primary, *rest = sorted(group, key=_authority)
    surest = max(group, key=lambda h: h.verdict.confidence)
    verdict = replace(
        primary.verdict,
        starts_at=_pick_time(primary, rest, tz),
        location=_pick_place(primary, rest),
        food=_pick_food([primary, *rest]),
        confidence=surest.verdict.confidence,
        reason=surest.verdict.reason,
    )
    return Hit(item=primary.item, verdict=verdict, also=rest)


def _pick_time(primary: Hit, rest: list[Hit], tz) -> datetime:
    """The primary's start time, unless it's only the noon stand-in and another
    listing gives a real one."""
    if not _noon_guess(primary, primary.when.astimezone(tz)):
        return primary.when
    for other in rest:
        if not _noon_guess(other, other.when.astimezone(tz)):
            return other.when
    return primary.when


def _pick_place(primary: Hit, rest: list[Hit]) -> str | None:
    """The primary's place, or a fuller spelling of it from another listing
    (one that adds the room number, say). If the primary gives no place, the
    most specific one any other listing gives."""
    place = primary.where
    others = [h.where for h in rest if _place_tokens(h.where)]
    if not _place_tokens(place):
        if not others:
            return place
        return max(others, key=lambda p: (_has_digit(p), len(_place_tokens(p))))
    for other in others:
        if _place_tokens(place) < _place_tokens(other):
            place = other
    return place


def _pick_food(ranked: list[Hit]) -> str | None:
    """The first description that names the food, in authority order, ahead of
    ones like "Delicious options (unspecified)"."""
    foods = [h.verdict.food.strip() for h in ranked if h.verdict.food and h.verdict.food.strip()]
    for food in foods:
        if not _VAGUE_FOOD.search(food):
            return food
    return foods[0] if foods else None
