"""
Gmail integration: OAuth2 connection and inbox reading.

Requires:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""
from __future__ import annotations

import base64
import re
import secrets
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from config import BASE_DIR, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI
from database import EmailDB

# Read-only is all we need for now. Expand later (e.g. gmail.send) for send features.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_PATH = BASE_DIR / "data" / "gmail_token.json"
VERIFIER_PATH = BASE_DIR / "data" / ".gmail_code_verifier"


class GmailService:
    def __init__(self):
        self.creds: Optional[Credentials] = None
        self._load_credentials()

    def _load_credentials(self) -> None:
        if TOKEN_PATH.exists():
            try:
                self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            except Exception as e:
                print(f"Gmail: failed to load saved token: {e}")
                self.creds = None

        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_credentials()
            except Exception as e:
                print(f"Gmail: failed to refresh token: {e}")
                self.creds = None

    def _save_credentials(self) -> None:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(self.creds.to_json())

    def is_connected(self) -> bool:
        return bool(self.creds and self.creds.valid)

    def _flow(self, code_verifier: Optional[str] = None) -> Flow:
        client_config = {
            "web": {
                "client_id": GMAIL_CLIENT_ID,
                "client_secret": GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GMAIL_REDIRECT_URI],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=GMAIL_REDIRECT_URI)
        if code_verifier:
            flow.code_verifier = code_verifier
        return flow

    def get_auth_url(self) -> str:
        flow = self._flow()
        # Google now requires PKCE for newer OAuth clients. Generate a verifier
        # here and persist it so the callback (a separate request/Flow object)
        # can use it when exchanging the code for tokens.
        flow.code_verifier = secrets.token_urlsafe(64)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        self._save_code_verifier(flow.code_verifier)
        return auth_url

    def exchange_code(self, code: str) -> bool:
        code_verifier = self._load_code_verifier()
        flow = self._flow(code_verifier=code_verifier)
        flow.fetch_token(code=code)
        self.creds = flow.credentials
        self._save_credentials()
        self._clear_code_verifier()
        return True

    def _save_code_verifier(self, verifier: str) -> None:
        VERIFIER_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERIFIER_PATH.write_text(verifier)

    def _load_code_verifier(self) -> Optional[str]:
        if VERIFIER_PATH.exists():
            return VERIFIER_PATH.read_text().strip()
        return None

    def _clear_code_verifier(self) -> None:
        if VERIFIER_PATH.exists():
            VERIFIER_PATH.unlink()

    def disconnect(self) -> None:
        self.creds = None
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()

    def _client(self):
        if not self.is_connected():
            raise RuntimeError("Gmail is not connected")
        return build("gmail", "v1", credentials=self.creds)

    def fetch_recent_messages(self, max_results: int = 20, query: str = "") -> List[Dict[str, Any]]:
        """Fetch and parse recent messages. `query` uses normal Gmail search syntax,
        e.g. 'is:unread', 'in:inbox newer_than:2d'."""
        service = self._client()
        resp = service.users().messages().list(
            userId="me", maxResults=max_results, q=query
        ).execute()

        messages = []
        for m in resp.get("messages", []):
            detail = self._get_message_detail(service, m["id"])
            if detail:
                messages.append(detail)
        return messages

    def _get_message_detail(self, service, message_id: str) -> Optional[Dict[str, Any]]:
        try:
            msg = service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        except HttpError as e:
            print(f"Gmail: failed to fetch message {message_id}: {e}")
            return None

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        body = self._extract_body(msg["payload"])

        received_at = None
        if "date" in headers:
            try:
                received_at = parsedate_to_datetime(headers["date"])
                if received_at.tzinfo is not None:
                    received_at = received_at.astimezone(tz=None).replace(tzinfo=None)
            except Exception:
                pass

        return {
            "gmail_id": msg["id"],
            "thread_id": msg.get("threadId"),
            "subject": headers.get("subject", "(no subject)"),
            "sender": headers.get("from", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
            "received_at": received_at,
            "is_unread": "UNREAD" in msg.get("labelIds", []),
            "labels": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Walk MIME parts and return the best available plain-text body."""
        mime = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime == "text/plain" and body_data:
            return self._decode(body_data)
        if mime == "text/html" and body_data:
            return self._strip_html(self._decode(body_data))

        text_part = None
        html_part = None
        for part in payload.get("parts", []) or []:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain" and part.get("body", {}).get("data"):
                text_part = part
            elif part_mime == "text/html" and part.get("body", {}).get("data"):
                html_part = part
            elif "parts" in part:
                nested = self._extract_body(part)
                if nested:
                    return nested

        if text_part:
            return self._decode(text_part["body"]["data"])
        if html_part:
            return self._strip_html(self._decode(html_part["body"]["data"]))
        return ""

    @staticmethod
    def _decode(data: str) -> str:
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def sync_inbox(self, db: Session, max_results: int = 20, query: str = "in:inbox") -> List[EmailDB]:
        """Pull recent messages and upsert into EmailDB. Returns newly-added emails."""
        messages = self.fetch_recent_messages(max_results=max_results, query=query)
        new_emails: List[EmailDB] = []

        for m in messages:
            existing = db.query(EmailDB).filter(EmailDB.gmail_id == m["gmail_id"]).first()
            if existing:
                if existing.is_unread != m["is_unread"]:
                    existing.is_unread = m["is_unread"]
                    db.commit()
                continue

            email = EmailDB(
                gmail_id=m["gmail_id"],
                thread_id=m["thread_id"],
                subject=m["subject"],
                sender=m["sender"],
                snippet=m["snippet"],
                body=m["body"][:10000],
                received_at=m["received_at"] or datetime.utcnow(),
                is_unread=m["is_unread"],
                processed=False,
            )
            db.add(email)
            new_emails.append(email)

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


gmail_service = GmailService()