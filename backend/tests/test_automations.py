import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from automations import email_matches, execute_email_rule
from database import Base, AutomationRuleDB, EmailDB, EmailAttachmentDB, TaskDB, AutomationRunDB, AutomationArtifactDB


def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_email_rule_creates_one_task_and_tags_email():
    db = db_session()
    email = EmailDB(gmail_id="message-1", subject="August invoice", sender="Vendor <vendor@example.com>", body="Invoice attached")
    attachment = EmailAttachmentDB(email_id=email.id, filename="invoice.pdf", stored_name="stored.pdf", content_type="application/pdf", size=42)
    rule = AutomationRuleDB(name="Invoice", trigger="email", condition="invoice", actions=json.dumps(["save", "task", "tag"]), details="tag as finance")
    db.add_all([email, rule]); db.commit()
    attachment.email_id = email.id; db.add(attachment); db.commit()
    assert email_matches(rule, email)
    first = execute_email_rule(db, rule, email)
    second = execute_email_rule(db, rule, email)
    assert first["status"] == "completed"
    assert second["status"] == "already_processed"
    assert db.query(TaskDB).count() == 1
    assert db.query(AutomationRunDB).count() == 1
    assert db.query(AutomationArtifactDB).filter_by(kind="attachment").count() == 1
    assert "finance" in email.tags.split(",")


def test_email_rule_condition_does_not_match_unrelated_email():
    db = db_session()
    email = EmailDB(gmail_id="message-2", subject="Team update", sender="team@example.com", body="Weekly notes")
    rule = AutomationRuleDB(name="Invoice", trigger="email", condition="invoice", actions=json.dumps(["task"]))
    assert not email_matches(rule, email)
