"""Unit tests for Gmail privacy scoping and email classification."""
import tempfile
from web.backend.db import AppDatabase
from web.backend.gmail_service import GmailService


def test_gmail_privacy_query_scope():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = AppDatabase(db_path=tmp.name)
        # Add tracker entries
        db.add_tracker_entry(
            job_id="1", company="Stripe", title="Frontend Engineer", location="Bangalore", apply_url="https://stripe.com"
        )
        db.add_tracker_entry(
            job_id="2", company="Canonical", title="Cloud Engineer", location="Remote", apply_url="https://canonical.com"
        )

        query = GmailService.build_privacy_query(db)
        # Privacy guarantee: query must ONLY search for canonical and stripe, never arbitrary/all senders
        assert "from:*canonical*" in query
        assert "from:*stripe*" in query
        assert "OR" in query


def test_classify_email_categories():
    r1 = GmailService.classify_email("Interview with Stripe", "We would love to invite you to an interview with our engineering team.")
    assert r1["category"] == "interview_invite"
    assert r1["suggested_status"] == "interview"

    r2 = GmailService.classify_email("Update on your application", "Unfortunately, after careful consideration, we have decided to move forward with other candidates.")
    assert r2["category"] == "rejection"
    assert r2["suggested_status"] == "rejected"
