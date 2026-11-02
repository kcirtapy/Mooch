"""The fetch -> store -> classify cycle, callable from the CLI or the server."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .db import Store
from .models import RawItem

log = logging.getLogger("mooch.pipeline")


def build_sources(cfg, store: Store, only: str | None = None) -> list:
    from .sources.email_source import EmailSource
    from .sources.instagram import InstagramSource
    from .sources.jumbolife import JumboLifeSource

    sources = []
    if cfg.enabled("jumbolife") and only in (None, "jumbolife"):
        sources.append(JumboLifeSource(cfg.section("jumbolife"), cfg.timezone))
    if cfg.enabled("email") and only in (None, "email"):
        sources.append(EmailSource(cfg.section("email"), cfg.imap_password, store))
    if cfg.enabled("instagram") and only in (None, "instagram"):
        sources.append(InstagramSource(cfg.section("instagram"), cfg.ig_password, cfg.timezone))
    return sources


def window(cfg):
    """Event start times we care about: just-started through lookahead_days."""
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=3), now + timedelta(days=cfg.lookahead_days)


def run_once(cfg, store: Store) -> dict:
    """One full cycle. Returns a summary; raises only on unrecoverable config errors."""
    from .classify import Classifier

    sources = build_sources(cfg, store)
    if not sources:
        raise RuntimeError(
            "No sources enabled. Set enabled: true for at least one in config.yaml."
        )

    fetched: list[RawItem] = []
    for source in sources:
        fetched.extend(source.safe_fetch(store.seen_ids(source.name)))

    added = store.add_items(fetched)
    log.info("%d new item(s) stored", added)

    from .classify import PROMPT_VERSION
    acfg_model = cfg.section("anthropic").get("model", "claude-haiku-4-5-20251001")
    tag = f"{acfg_model}|{PROMPT_VERSION}"
    pending = store.unclassified(tag)
    classified = found = 0

    if pending:
        if not cfg.anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env; can't classify.")
        acfg = cfg.section("anthropic")
        model = acfg.get("model", "claude-haiku-4-5-20251001")
        classifier = Classifier(
            api_key=cfg.anthropic_key,
            model=model,
            tz=cfg.timezone,
            max_chars=int(acfg.get("max_chars", 4000)),
        )
        log.info("Classifying %d item(s)...", len(pending))
        results = classifier.classify_many(pending, int(acfg.get("max_concurrency", 4)))
        for item_id, verdict in results:
            store.save_verdict(item_id, verdict, tag)
        classified = len(results)
        found = sum(1 for _, v in results if v.has_free_food)
        log.info("Classified %d, found food in %d", classified, found)
    else:
        log.info("Nothing new to classify")

    return {"fetched": len(fetched), "added": added, "classified": classified, "found": found}
