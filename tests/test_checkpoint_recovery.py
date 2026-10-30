"""Tests for incremental checkpoints, overlap safety, missed-run catchup, and failure recovery."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from src.config import Settings
from src.db import DatabaseManager
from src.extractor import EmailAnalysisResult, EmailExtractor
from src.gmail_client import GmailClient
from src.models import (
    MessageClassification,
    TransactionExtraction,
    TransactionType,
)
from src.scanner import AccountScanner


@pytest.fixture
def recovery_env(tmp_path):
    """Set up an isolated database and mock scanner environment."""
    db_file = tmp_path / "recovery_test.db"
    db = DatabaseManager(db_path=db_file)
    settings = Settings(database_path=db_file, scan_lookback_overlap_hours=2)

    mock_gmail = MagicMock(spec=GmailClient)
    mock_extractor = MagicMock(spec=EmailExtractor)

    scanner = AccountScanner(
        account_id="account_2",
        account_type="transactions",
        email_address="user2.bank@example.com",
        settings=settings,
        db=db,
        gmail_client=mock_gmail,
        extractor=mock_extractor,
    )
    return scanner, db, settings, mock_gmail, mock_extractor


def test_first_run_query_without_checkpoint(recovery_env):
    """First run on an account has no 'after:' clause to capture initial candidates."""
    scanner, db, settings, mock_gmail, mock_extractor = recovery_env

    # Checkpoint is None
    account = db.get_account("account_2")
    assert account.last_scan_timestamp is None

    query = scanner.build_query()
    assert "after:" not in query
    assert "receipt" in query


def test_query_includes_overlap_window(recovery_env):
    """Query subtracts scan_lookback_overlap_hours (2h) from last_scan_timestamp."""
    scanner, db, settings, mock_gmail, mock_extractor = recovery_env

    # Set checkpoint to 2026-10-30 14:00:00 UTC
    checkpoint_time = "2026-10-30T14:00:00+00:00"
    db.update_checkpoint("account_2", checkpoint_time)

    # 2 hours before 14:00:00 is 12:00:00 UTC
    expected_overlap_dt = datetime.fromisoformat("2026-10-30T12:00:00+00:00")
    expected_epoch = int(expected_overlap_dt.timestamp())

    query = scanner.build_query()
    assert f"after:{expected_epoch}" in query


def test_missed_run_catches_up_from_old_checkpoint(recovery_env):
    """If computer was off for 5 days, scanner resumes from 5 days ago, not fixed 24h."""
    scanner, db, settings, mock_gmail, mock_extractor = recovery_env

    # Set checkpoint from 5 days ago: 2026-10-25 10:00:00 UTC
    old_checkpoint = "2026-10-25T10:00:00+00:00"
    db.update_checkpoint("account_2", old_checkpoint)

    query = scanner.build_query()

    # 2 hours before 2026-10-25 10:00 is 2026-10-25 08:00
    expected_dt = datetime.fromisoformat("2026-10-25T08:00:00+00:00")
    expected_epoch = int(expected_dt.timestamp())

    assert f"after:{expected_epoch}" in query


def test_scan_failure_does_not_advance_checkpoint(recovery_env):
    """If any message fails processing, the account checkpoint is NOT advanced."""
    scanner, db, settings, mock_gmail, mock_extractor = recovery_env

    initial_checkpoint = "2026-10-29T10:00:00+00:00"
    db.update_checkpoint("account_2", initial_checkpoint)

    mock_gmail.list_messages.return_value = {"messages": [{"id": "msg_err"}]}
    # Simulate API error during message retrieval
    mock_gmail.get_message_detail.side_effect = Exception("Network connection lost")

    stats = scanner.scan()

    assert stats["errors"] == 1
    # Checkpoint must remain unchanged
    account = db.get_account("account_2")
    assert account.last_scan_timestamp == initial_checkpoint


def test_overlap_deduplication_preserves_groq_quota(recovery_env):
    """Candidates refetched due to overlap are discarded before invoking LLM."""
    scanner, db, settings, mock_gmail, mock_extractor = recovery_env

    # Pre-seed a message in DB
    db.record_processed_message(
        account_id="account_2",
        message_id="msg_refetched_due_to_overlap",
        thread_id=None,
        received_at="2026-10-30T13:30:00Z",
        subject="Charge",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )

    # Gmail returns the message again during overlapping search
    mock_gmail.list_messages.return_value = {
        "messages": [{"id": "msg_refetched_due_to_overlap"}]
    }

    stats = scanner.scan()

    assert stats["candidates_found"] == 1
    assert stats["already_processed_skipped"] == 1
    assert stats["newly_processed"] == 0

    # Ensure zero detail calls and zero LLM calls
    mock_gmail.get_message_detail.assert_not_called()
    mock_extractor.analyze_email.assert_not_called()
