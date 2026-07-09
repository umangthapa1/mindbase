
"""
Simple email integration via IMAP + app password.

No Google Cloud / OAuth setup required. The user enables 2-step verification
on their email account, generates an app password, and enters their address +
that password. Works with any IMAP provider (Gmail, Outlook, Yahoo, iCloud…).

Uses only the Python standard library (imaplib + email) — no extra deps.
"""
from __future__ import annotations

import email
import imaplib
import json
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import BASE_DIR
from database import EmailDB

CONFIG_PATH = BASE_DIR / "data" / "email_config.json"

# IMAP host auto-detection by email domain. Covers the common providers; users
# on anything else can still connect if their provider uses one of these, and
# we fall back to imap.<domain> for everything else.
IMAP_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "office365.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
}


def _imap_host_for(address: str) -> str:
    domain = address.split("@")[-1].strip().lower()
    return IMAP_HOSTS.get(domain, f"imap.{domain}")


class ImapService:
    def __init__(self):
        self.config: Dict[str, str] = {}
        self._load_config()

    # ── Credential storage ──────────────────────────────────
    def _load_config(self) -> None:
        if CONFIG_PATH.exists():
            try:
                self.config = json.loads(CONFIG_PATH.read_text())
            except Exception as e:
                print(f"Email: failed to load saved config: {e}")
                self.config = {}

    def _save_config(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.config))

    def is_connected(self) -> bool:
        return bool(self.config.get("email") and self.config.get("password"))

    def account_email(self) -> Optional[str]:
        return self.config.get("email")

    # ── Connect / disconnect ────────────────────────────────
    def _open(self) -> imaplib.IMAP4_SSL:
        host = self.config.get("host") or _imap_host_for(self.config["email"])
        client = imaplib.IMAP4_SSL(host)
        client.login(self.config["email"], self.config["password"])
        return client

    def connect(self, address: str, password: str, host: str = "") -> None:
        """Validate the credentials by logging in, then persist them.
        Raises on failure so the route can surface a useful message."""
        address = address.strip()
        password = password.strip()
        host = (host or _imap_host_for(address)).strip()
        # App passwords are often shown with spaces (e.g. "abcd efgh ijkl mnop");
        # the server expects them without spaces.
        password_clean = password.replace(" ", "")

        client = imaplib.IMAP4_SSL(host)
        try:
            client.login(address, password_clean)
        finally:
            try:
                client.logout()
            except Exception:
                pass

        self.config = {"email": address, "password": password_clean, "host": host}
        self._save_config()

    def disconnect(self) -> None:
        self.config = {}
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()

    # ── Fetching ────────────────────────────────────────────
    def fetch_recent_messages(
        self, max_results: int = 20, unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        if not self.is_connected():
            raise RuntimeError("Email is not connected")

        client = self._open()
        try:
            # readonly=True so reading the inbox here never marks mail as seen.
            client.select("INBOX", readonly=True)
            criterion = "UNSEEN" if unread_only else "ALL"
            typ, data = client.search(None, criterion)
            if typ != "OK" or not data or not data[0]:
                return []

            ids = data[0].split()
            ids = ids[-max_results:]  # most recent N
            ids.reverse()  # newest first

            messages: List[Dict[str, Any]] = []
            for num in ids:
                detail = self._fetch_one(client, num)
                if detail:
                    messages.append(detail)
            return messages
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _fetch_one(self, client: imaplib.IMAP4_SSL, num: bytes) -> Optional[Dict[str, Any]]:
        try:
            typ, msg_data = client.fetch(num, "(FLAGS BODY.PEEK[])")
            if typ != "OK" or not msg_data:
                return None

            flags = b""
            raw = None
            for part in msg_data:
                if isinstance(part, tuple):
                    flags += part[0] or b""
                    raw = part[1]
                elif isinstance(part, (bytes, bytearray)):
                    flags += part
            if raw is None:
                return None

            msg = email.message_from_bytes(raw)
            is_unread = b"\\Seen" not in flags

            subject = self._decode_header(msg.get("Subject", "")) or "(no subject)"
            sender = self._decode_header(msg.get("From", ""))
            message_id = (msg.get("Message-ID") or f"{num.decode()}-{subject}").strip()

            received_at = None
            date_hdr = msg.get("Date")
            if date_hdr:
                try:
                    received_at = parsedate_to_datetime(date_hdr)
                    if received_at and received_at.tzinfo is not None:
                        received_at = received_at.astimezone(tz=None).replace(tzinfo=None)
                except Exception:
                    pass

            text_body, html_body = self._extract_body(msg)
            snippet = re.sub(r"\s+", " ", text_body).strip()[:160]

            return {
                "gmail_id": message_id,
                "thread_id": None,
                "subject": subject,
                "sender": sender,
                "snippet": snippet,
                "body": text_body,
                "html_body": html_body,
                "received_at": received_at,
                "is_unread": is_unread,
            }
        except Exception as e:
            print(f"Email: failed to parse message {num!r}: {e}")
            return None

    @staticmethod
    def _decode_header(value: str) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    def _extract_body(self, msg: email.message.Message) -> tuple[str, str]:
        """Return (plain_text, html) for the message.

        plain_text is always populated (used for snippets, search, and the LLM).
        html is the original rich HTML when the message provides it (used for
        rendering); empty when the message is plain-text only.
        """
        text_raw = ""
        html_raw = ""

        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart():
                    continue
                disp = str(part.get("Content-Disposition") or "")
                if "attachment" in disp.lower():
                    continue
                ctype = part.get_content_type()
                if ctype == "text/plain" and not text_raw:
                    text_raw = self._payload_text(part)
                elif ctype == "text/html" and not html_raw:
                    html_raw = self._payload_text(part)
        else:
            payload = self._payload_text(msg)
            if msg.get_content_type() == "text/html":
                html_raw = payload
            else:
                text_raw = payload

        # Derive plain text from HTML if there was no text/plain alternative.
        if not text_raw and html_raw:
            text_raw = self._strip_html(html_raw)

        return text_raw.strip(), html_raw.strip()

    @staticmethod
    def _payload_text(part: email.message.Message) -> str:
        try:
            raw = part.get_payload(decode=True)
            if raw is None:
                return ""
            charset = part.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _strip_html(html_src: str) -> str:
        import html as _html
        text = re.sub(r"<(script|style|head)[^>]*>.*?</\1>", "", html_src, flags=re.S | re.I)
        # Turn block-level boundaries into newlines so structure survives.
        text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</\s*(p|div|li|tr|h[1-6]|table|ul|ol|blockquote)\s*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = _html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # collapse runs of blank lines
        return text.strip()

    # ── Sync into DB ────────────────────────────────────────
    def sync_inbox(
        self, db: Session, max_results: int = 20, unread_only: bool = False, **_ignored
    ) -> List[EmailDB]:
        """Pull recent messages and upsert into EmailDB. Returns newly-added emails."""
        messages = self.fetch_recent_messages(max_results=max_results, unread_only=unread_only)
        new_emails: List[EmailDB] = []

        for m in messages:
            existing = db.query(EmailDB).filter(EmailDB.gmail_id == m["gmail_id"]).first()
            if existing:
                changed = False
                if existing.is_unread != m["is_unread"]:
                    existing.is_unread = m["is_unread"]
                    changed = True
                # Backfill rich content for emails synced before html_body existed.
                if m.get("html_body") and not (existing.html_body or "").strip():
                    existing.html_body = m["html_body"][:200000]
                    existing.body = m["body"][:10000]
                    existing.snippet = m["snippet"]
                    changed = True
                if changed:
                    db.commit()
                continue

            mail = EmailDB(
                gmail_id=m["gmail_id"],
                thread_id=m["thread_id"],
                subject=m["subject"],
                sender=m["sender"],
                snippet=m["snippet"],
                body=m["body"][:10000],
                html_body=(m.get("html_body") or "")[:200000],
                received_at=m["received_at"] or datetime.utcnow(),
                is_unread=m["is_unread"],
                processed=False,
            )
            db.add(mail)
            new_emails.append(mail)

        db.commit()
        for e in new_emails:
            db.refresh(e)
        return new_emails


def serialize_email(e: EmailDB) -> Dict[str, Any]:
    return {
        "id": e.id,
        "gmail_id": e.gmail_id,
        "thread_id": e.thread_id,
        "subject": e.subject,
        "sender": e.sender,
        "snippet": e.snippet,
        "is_unread": bool(e.is_unread),
        "received_at": e.received_at.isoformat() if e.received_at else None,
        "processed": bool(e.processed),
    }


email_service = ImapService()
