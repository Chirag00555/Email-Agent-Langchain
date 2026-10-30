"""Unit and integration tests for multi-account separation and independent tracking."""

from unittest.mock import MagicMock
import pytest

from src.config import Settings
from src.db import DatabaseManager
from src.extractor import EmailAnalysisResult, EmailExtractor
from src.gmail_client import GmailClient
from src.models import (
    JobEventExtraction,
    JobEventType,
    MessageClassification,
    TransactionExtraction,
    TransactionType,
)
from src.scanner import AccountScanner, scan_all_accounts


@pytest.fixture
def multi_db(tmp_path):
    """Isolated SQLite database for multi-account testing."""
    db_file = tmp_path / "multi_test.db"
    return DatabaseManager(db_path=db_file)


def test_three_accounts_registration(multi_db):
    """Verify that all three accounts are registered with their designated types."""
    multi_db.upsert_account("account_1", "user1.jobs@example.com", "jobs")
    multi_db.upsert_account("account_2", "user2.bank@example.com", "transactions")
    multi_db.upsert_account("account_3", "user3.jobs@example.com", "jobs")

    accounts = multi_db.list_accounts()
    assert len(accounts) == 3

    acct_map = {a.account_id: a for a in accounts}
    assert acct_map["account_1"].account_type == "jobs"
    assert acct_map["account_2"].account_type == "transactions"
    assert acct_map["account_3"].account_type == "jobs"


def test_independent_checkpoint_progression(multi_db):
    """Advancing checkpoint on one account must not modify checkpoints of other accounts."""
    multi_db.upsert_account("account_1", "jobs1@gmail.com", "jobs")
    multi_db.upsert_account("account_2", "bank@gmail.com", "transactions")
    multi_db.upsert_account("account_3", "jobs2@gmail.com", "jobs")

    # Update only Account 2 checkpoint
    multi_db.update_checkpoint("account_2", "2026-10-30T15:00:00Z", last_history_id="11111")

    a1 = multi_db.get_account("account_1")
    a2 = multi_db.get_account("account_2")
    a3 = multi_db.get_account("account_3")

    assert a2.last_scan_timestamp == "2026-10-30T15:00:00Z"
    assert a2.last_history_id == "11111"
    assert a1.last_scan_timestamp is None
    assert a3.last_scan_timestamp is None


def test_cross_account_same_message_id_no_collision(multi_db):
    """The same message ID across different Gmail accounts must be stored distinctly."""
    multi_db.upsert_account("account_1", "user1@gmail.com", "jobs")
    multi_db.upsert_account("account_2", "user2@gmail.com", "transactions")
    multi_db.upsert_account("account_3", "user3@gmail.com", "jobs")

    shared_msg_id = "msg_external_shared_789"

    # Ingest under Account 1
    multi_db.record_processed_message(
        account_id="account_1",
        message_id=shared_msg_id,
        thread_id="th_1",
        received_at="2026-10-30T10:00:00Z",
        subject="Notification",
        sender="notice@platform.com",
        classification=MessageClassification.JOB,
    )
    multi_db.create_job_event(
        account_id="account_1",
        message_id=shared_msg_id,
        extraction=JobEventExtraction(company="Acme Corp", role_title="Developer"),
    )

    # Ingest same ID under Account 2 (transactions account)
    multi_db.record_processed_message(
        account_id="account_2",
        message_id=shared_msg_id,
        thread_id="th_2",
        received_at="2026-10-30T10:05:00Z",
        subject="Fee Alert",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )
    multi_db.create_transaction(
        account_id="account_2",
        message_id=shared_msg_id,
        extraction=TransactionExtraction(merchant="Platform Fee", amount=5.00),
    )

    # Ingest same ID under Account 3
    multi_db.record_processed_message(
        account_id="account_3",
        message_id=shared_msg_id,
        thread_id="th_3",
        received_at="2026-10-30T10:10:00Z",
        subject="Notification",
        sender="notice@platform.com",
        classification=MessageClassification.JOB,
    )

    # Assert all three are recorded distinctly without collisions
    assert multi_db.is_message_processed("account_1", shared_msg_id)
    assert multi_db.is_message_processed("account_2", shared_msg_id)
    assert multi_db.is_message_processed("account_3", shared_msg_id)

    # Assert querying by account yields only that account's record
    txs_a2 = multi_db.list_transactions(account_id="account_2")
    assert len(txs_a2) == 1
    assert txs_a2[0].merchant == "Platform Fee"

    txs_a1 = multi_db.list_transactions(account_id="account_1")
    assert len(txs_a1) == 0

    jobs_a1 = multi_db.list_job_events(account_id="account_1")
    assert len(jobs_a1) == 1
    assert jobs_a1[0].company == "Acme Corp"


def test_scan_all_accounts_orchestration(tmp_path):
    """Verify scan_all_accounts coordinates execution across all 3 accounts."""
    db_file = tmp_path / "scan_all.db"
    db = DatabaseManager(db_path=db_file)

    settings = Settings(
        database_path=db_file,
        account_1_type="jobs",
        account_2_type="transactions",
        account_3_type="jobs",
    )

    # Pre-seed accounts in DB
    db.upsert_account("account_1", "a1@gmail.com", "jobs")
    db.upsert_account("account_2", "a2@gmail.com", "transactions")
    db.upsert_account("account_3", "a3@gmail.com", "jobs")

    results = []
    # Mock scanning for each account
    for acct in settings.get_configured_accounts():
        mock_gmail = MagicMock(spec=GmailClient)
        mock_gmail.list_messages.return_value = {"messages": []}
        mock_extractor = MagicMock(spec=EmailExtractor)

        scanner = AccountScanner(
            account_id=acct["account_id"],
            account_type=acct["type"],
            email_address=acct["email"],
            settings=settings,
            db=db,
            gmail_client=mock_gmail,
            extractor=mock_extractor,
        )
        res = scanner.scan(dry_run=True)
        results.append(res)

    assert len(results) == 3
    assert results[0]["account_id"] == "account_1"
    assert results[1]["account_id"] == "account_2"
    assert results[2]["account_id"] == "account_3"
