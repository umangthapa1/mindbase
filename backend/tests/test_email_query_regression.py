"""Regression coverage for natural-language local email search."""
import pytest

pytest.importorskip("chromadb")

from database import Base, EmailDB
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import _build_email_context, _extract_email_search_terms, _is_email_query


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_plural_topic_search_finds_singular_invoice_in_body():
    db = _db()
    db.add(EmailDB(gmail_id="invoice-1", subject="Invoice test", sender="Umang", body="Here is the invoice for your items."))
    db.commit()
    assert "Invoice test" in _build_email_context(db, "any emails about invoices?")


def test_short_or_followup_remains_an_email_query_and_finds_sender():
    db = _db()
    db.add(EmailDB(gmail_id="google-1", subject="Account notice", sender="Google <noreply-accounts@google.com>", body="Account data notice."))
    db.commit()
    history = [{"role": "user", "content": "any emails about invoices?"}]
    assert _is_email_query("or google?", history)
    assert "Google" in _build_email_context(db, "or google?")


def test_event_time_range_is_not_misclassified_as_an_email_sender():
    message = "Add an event on Monday: Quiz by science and IT club from 8 am to 1 pm."

    assert not _is_email_query(message)


def test_email_from_named_sender_remains_an_email_query():
    assert _is_email_query("Show me emails from Alice")


def test_explain_email_from_sender_uses_that_sender_not_an_unrelated_body_match():
    db = _db()
    db.add_all([
        EmailDB(
            gmail_id="reddit-1", sender="Reddit <noreply@redditmail.com>",
            subject="Reddit thread", body="The Reddit message body.",
        ),
        EmailDB(
            gmail_id="other-1", sender="Other <other@example.com>",
            subject="Unrelated", body="A passing reference to reddit.",
        ),
    ])
    db.commit()

    filters = _extract_email_search_terms("explain the email from reddit.")
    result = _build_email_context(db, "explain the email from reddit.")

    assert filters["sender"] == "reddit"
    assert filters["sender_only"] is True
    assert filters["want_body"] is True
    assert "Reddit thread" in result
    assert "Unrelated" not in result
