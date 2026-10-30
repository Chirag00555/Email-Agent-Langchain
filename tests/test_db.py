"""Unit tests for SQLite schema, models, constraints, and CRUD operations."""

import sqlite3
import pytest
from src.db import DatabaseManager
from src.models import (
    JobEventExtraction,
    JobEventType,
    MessageClassification,
    ReviewStatus,
    TransactionExtraction,
    TransactionType,
)


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite database instance for each test."""
    db_file = tmp_path / "test_email_agent.db"
    return DatabaseManager(db_path=db_file)


# ==============================================================================
# Account & Checkpoint Tests
# ==============================================================================

def test_upsert_and_get_account(db):
    account = db.upsert_account("account_1", "test.bank@gmail.com", "transactions")
    assert account.account_id == "account_1"
    assert account.email == "test.bank@gmail.com"
    assert account.account_type == "transactions"
    assert account.last_scan_timestamp is None

    # Upsert again with new email
    updated = db.upsert_account("account_1", "updated.bank@gmail.com", "transactions")
    assert updated.email == "updated.bank@gmail.com"


def test_update_checkpoint(db):
    db.upsert_account("account_2", "jobs1@gmail.com", "jobs")
    checkpoint_time = "2026-10-30T10:00:00Z"
    db.update_checkpoint("account_2", checkpoint_time, last_history_id="123456")

    account = db.get_account("account_2")
    assert account.last_scan_timestamp == checkpoint_time
    assert account.last_history_id == "123456"


# ==============================================================================
# Deduplication & Composite Key Tests
# ==============================================================================

def test_processed_message_deduplication(db):
    db.upsert_account("account_1", "test1@gmail.com", "transactions")

    assert not db.is_message_processed("account_1", "msg_001")

    db.record_processed_message(
        account_id="account_1",
        message_id="msg_001",
        thread_id="th_001",
        received_at="2026-10-29T12:00:00Z",
        subject="Your Statement",
        sender="alerts@bank.com",
        classification=MessageClassification.TRANSACTION,
    )

    assert db.is_message_processed("account_1", "msg_001")

    # Attempting to insert duplicate (account_id, message_id) must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        db.record_processed_message(
            account_id="account_1",
            message_id="msg_001",
            thread_id="th_001",
            received_at="2026-10-29T12:00:00Z",
            subject="Your Statement",
            sender="alerts@bank.com",
            classification=MessageClassification.TRANSACTION,
        )


def test_same_message_id_different_accounts_permitted(db):
    """The same message ID from two different accounts must not conflict."""
    db.upsert_account("account_1", "user1@gmail.com", "jobs")
    db.upsert_account("account_2", "user2@gmail.com", "jobs")

    # Both receive an email with the same message ID (e.g. forward or external duplicate)
    rec1 = db.record_processed_message(
        account_id="account_1",
        message_id="shared_msg_999",
        thread_id="th_999",
        received_at="2026-10-29T10:00:00Z",
        subject="Job Notification",
        sender="notifications@linkedin.com",
        classification=MessageClassification.JOB,
    )
    rec2 = db.record_processed_message(
        account_id="account_2",
        message_id="shared_msg_999",
        thread_id="th_999",
        received_at="2026-10-29T10:00:00Z",
        subject="Job Notification",
        sender="notifications@linkedin.com",
        classification=MessageClassification.JOB,
    )

    assert rec1.account_id == "account_1"
    assert rec2.account_id == "account_2"
    assert db.is_message_processed("account_1", "shared_msg_999")
    assert db.is_message_processed("account_2", "shared_msg_999")


# ==============================================================================
# Transaction CRUD & Privacy (No Email Body) Tests
# ==============================================================================

def test_transaction_crud_and_category_update(db):
    db.upsert_account("account_1", "bank@gmail.com", "transactions")
    db.record_processed_message(
        account_id="account_1",
        message_id="msg_tx_01",
        thread_id="th_tx_01",
        received_at="2026-10-28T09:00:00Z",
        subject="Debit Alert",
        sender="alerts@bank.com",
        classification=MessageClassification.TRANSACTION,
    )

    extraction = TransactionExtraction(
        transaction_date="2026-10-28",
        merchant="Trader Joe's",
        amount=42.50,
        currency="USD",
        card_last_four="4321",
        transaction_type=TransactionType.PURCHASE,
        confidence_score=0.95,
    )

    tx_id = db.create_transaction("account_1", "msg_tx_01", extraction)
    assert tx_id > 0

    record = db.get_transaction_by_id(tx_id)
    assert record.merchant == "Trader Joe's"
    assert record.amount == 42.50
    assert record.card_last_four == "4321"
    assert record.category_hint == "uncategorized"
    assert record.review_status == ReviewStatus.NEEDS_REVIEW

    # User updates spending category
    updated = db.update_transaction_category(tx_id, "groceries", mark_reviewed=True)
    assert updated is True

    record_after = db.get_transaction_by_id(tx_id)
    assert record_after.category_hint == "groceries"
    assert record_after.review_status == ReviewStatus.REVIEWED


def test_transaction_unique_per_account_message(db):
    """Cannot insert two transactions for the exact same email message."""
    db.upsert_account("account_1", "bank@gmail.com", "transactions")
    db.record_processed_message(
        account_id="account_1",
        message_id="msg_tx_02",
        thread_id="th_tx_02",
        received_at="2026-10-28T10:00:00Z",
        subject="Alert",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )

    extraction = TransactionExtraction(
        transaction_date="2026-10-28",
        merchant="Target",
        amount=19.99,
        card_last_four="1111",
    )
    db.create_transaction("account_1", "msg_tx_02", extraction)

    with pytest.raises(sqlite3.IntegrityError):
        db.create_transaction("account_1", "msg_tx_02", extraction)


# ==============================================================================
# Job Events CRUD Tests
# ==============================================================================

def test_job_event_crud(db):
    db.upsert_account("account_2", "jobs@gmail.com", "jobs")
    db.record_processed_message(
        account_id="account_2",
        message_id="msg_job_01",
        thread_id="th_job_01",
        received_at="2026-10-29T14:30:00Z",
        subject="Invitation to Interview: Software Engineer",
        sender="recruiter@techcorp.com",
        classification=MessageClassification.JOB,
    )

    extraction = JobEventExtraction(
        company="TechCorp",
        role_title="Software Engineer",
        event_type=JobEventType.INTERVIEW_INVITATION,
        interview_datetime="2026-11-05T15:00:00",
        timezone="EST",
        meeting_link="https://meet.google.com/abc-defg-hij",
        next_step="Confirm availability on calendar link",
        confidence_score=0.98,
    )

    event_id = db.create_job_event("account_2", "msg_job_01", extraction)
    assert event_id > 0

    record = db.get_job_event_by_id(event_id)
    assert record.company == "TechCorp"
    assert record.role_title == "Software Engineer"
    assert record.event_type == JobEventType.INTERVIEW_INVITATION
    assert record.meeting_link == "https://meet.google.com/abc-defg-hij"

    # Update review status
    db.update_job_event_review_status(event_id, ReviewStatus.REVIEWED)
    assert db.get_job_event_by_id(event_id).review_status == ReviewStatus.REVIEWED


# ==============================================================================
# Spending Report Aggregations Tests
# ==============================================================================

def test_spending_summaries(db):
    db.upsert_account("account_1", "bank@gmail.com", "transactions")

    # Seed 3 transactions
    tx_data = [
        ("m1", "2026-10-01", "Whole Foods", 100.0, "groceries"),
        ("m2", "2026-10-05", "Trader Joe's", 50.0, "groceries"),
        ("m3", "2026-10-10", "Campus Bookstore", 120.0, "textbooks & education"),
    ]

    for msg_id, date, merch, amt, cat in tx_data:
        db.record_processed_message(
            account_id="account_1",
            message_id=msg_id,
            thread_id=None,
            received_at=f"{date}T12:00:00Z",
            subject="Alert",
            sender="bank@alerts.com",
            classification=MessageClassification.TRANSACTION,
        )
        extraction = TransactionExtraction(
            transaction_date=date,
            merchant=merch,
            amount=amt,
        )
        db.create_transaction("account_1", msg_id, extraction, category_hint=cat)

    summaries = db.get_spending_summaries()

    # Category totals
    cat_totals = {c["category_hint"]: c["total_amount"] for c in summaries["by_category"]}
    assert cat_totals["groceries"] == 150.0
    assert cat_totals["textbooks & education"] == 120.0

    # Merchant totals
    merch_totals = {m["merchant"]: m["total_amount"] for m in summaries["by_merchant"]}
    assert merch_totals["Whole Foods"] == 100.0
    assert merch_totals["Trader Joe's"] == 50.0
    assert merch_totals["Campus Bookstore"] == 120.0

    # Monthly totals
    month_totals = {m["month"]: m["total_amount"] for m in summaries["by_month"]}
    assert month_totals["2026-10"] == 270.0


# ==============================================================================
# Pydantic Extraction Model Validation Tests
# ==============================================================================

def test_pydantic_model_cleaning():
    # Card last four formatting: strips non-digits and takes last 4
    tx = TransactionExtraction(
        card_last_four="ending in ...4829",
        amount=15.99,
        merchant="Coffee Shop",
    )
    assert tx.card_last_four == "4829"

    # Negative amount rejection
    with pytest.raises(Exception):
        TransactionExtraction(amount=-5.0)

    # Job event confidence boundary
    job = JobEventExtraction(
        company="Startup Co",
        confidence_score=0.5,
        needs_review=True,
    )
    assert job.needs_review is True
    assert job.confidence_score == 0.5
