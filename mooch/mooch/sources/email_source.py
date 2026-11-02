"""Club newsletters over IMAP.

Reads one folder (a Gmail label) and tracks the highest UID it has processed,
so each run only pulls genuinely new mail. Keeping club mail in its own label
means the scraper never touches the rest of the inbox.
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.message import Message
from html.parser import HTMLParser

from ..models import RawItem
from .base import Source, clean, utc

log = logging.getLogger("mooch.email")

UID_KEY = "email:last_uid"


class _Stripper(HTMLParser):
    """Minimal HTML -> text. Club newsletters are table soup; this keeps the
    words and throws away the layout."""

    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", "".join(self.parts))


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 - malformed headers are common
        return value


def _body(msg: Message) -> str:
    plain, html = [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        (plain if ctype == "text/plain" else html).append(text)

    if plain:
        return "\n".join(plain)
    if html:
        stripper = _Stripper()
        stripper.feed("\n".join(html))
        return stripper.text()
    return ""


class EmailSource(Source):
    name = "email"

    def __init__(self, conf: dict, password: str | None, store):
        self.conf = conf
        self.password = password
        self.store = store

    def fetch(self, seen: set[str]) -> list[RawItem]:
        user = self.conf.get("user")
        if not user:
            raise ValueError("email.user is not set in config.yaml")
        if not self.password:
            raise ValueError("MOOCH_IMAP_PASSWORD is not set in .env")

        folder = self.conf.get("folder", "INBOX")
        limit = int(self.conf.get("max_messages_per_run", 60))

        conn = imaplib.IMAP4_SSL(self.conf.get("host", "imap.gmail.com"),
                                 int(self.conf.get("port", 993)))
        try:
            conn.login(user, self.password)
            status, _ = conn.select(f'"{folder}"', readonly=True)
            if status != "OK":
                raise ValueError(
                    f"Can't open IMAP folder {folder!r}. In Gmail the label name is the "
                    "folder name; a nested label looks like 'clubs/mooch'."
                )

            last_uid = int(self.store.get_meta(UID_KEY, "0") or 0)
            criterion = f"{last_uid + 1}:*" if last_uid else "1:*"
            status, data = conn.uid("SEARCH", None, "UID", criterion)
            if status != "OK":
                return []

            uids = [int(u) for u in (data[0] or b"").split()]
            uids = [u for u in uids if u > last_uid][-limit:]
            if not uids:
                return []

            items: list[RawItem] = []
            highest = last_uid
            for uid in uids:
                highest = max(highest, uid)
                status, fetched = conn.uid("FETCH", str(uid), "(RFC822)")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue

                msg = email.message_from_bytes(fetched[0][1])
                msg_id = _decode(msg.get("Message-ID")) or f"uid-{uid}"
                if msg_id in seen:
                    continue

                subject = clean(_decode(msg.get("Subject")))
                sender = _decode(msg.get("From"))
                _, addr = email.utils.parseaddr(sender)
                body = clean(_body(msg))
                if not (subject or body):
                    continue

                try:
                    posted = utc(email.utils.parsedate_to_datetime(msg.get("Date")))
                except (TypeError, ValueError):
                    posted = utc(None)

                items.append(
                    RawItem(
                        source=self.name,
                        external_id=msg_id,
                        title=subject or None,
                        author=sender or addr or None,
                        text="\n\n".join(filter(None, [subject, body])),
                        posted_at=posted,
                    )
                )

            self.store.set_meta(UID_KEY, str(highest))
            return items
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
