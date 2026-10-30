"""Integration tests for scanner orchestration, deduplication, and persistence."""

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
from src.scanner import AccountScanner


@pytest.fixture
def mock_scanner(tmp_path):
    """Construct an AccountScanner with isolated temporary DB and mock dependencies."""
    db_file = tmp_path / "test_scanner.db"
    db = DatabaseManager(db_path=db_file)
    settings = Settings(database_path=db_file)

    mock_gmail = MagicMock(spec=GmailClient)
    mock_extractor = MagicMock(spec=EmailExtractor)

    scanner = AccountScanner(
        account_id="account_1",
        account_type="transactions",
        email_address="test@gmail.com",
        settings=settings,
        db=db,
        gmail_client=mock_gmail,
        extractor=mock_extractor,
    )
    return scanner, db, mock_gmail, mock_extractor


def test_scan_and_persist_transactions(mock_scanner):
    """Verify that candidate emails are fetched, analyzed, and stored in SQLite."""
    scanner, db, mock_gmail, mock_extractor = mock_scanner

    # Mock Gmail messages list
    mock_gmail.list_messages.return_value = {
        "messages": [
            {"id": "msg_01"},
            {"id": "msg_02"},
        ]
    }

    # Mock message details
    mock_gmail.get_message_detail.side_effect = [
        {
            "message_id": "msg_01",
            "thread_id": "th_01",
            "subject": "Charge Alert: Whole Foods",
            "sender": "alerts@bank.com",
            "date": "2026-10-25T10:00:00Z",
            "body": "Your card was charged $35.50 at Whole Foods.",
        },
        {
            "message_id": "msg_02",
            "thread_id": "th_02",
            "subject": "Weekly Newsletter",
            "sender": "newsletter@recipes.com",
            "date": "2026-10-25T11:00:00Z",
            "body": "Here are 5 easy soup recipes.",
        },
    ]

    # Mock LLM analysis
    mock_extractor.analyze_email.side_effect = [
        EmailAnalysisResult(
            classification=MessageClassification.TRANSACTION,
            confidence_score=0.95,
            transaction=TransactionExtraction(
                transaction_date="2026-10-25",
                merchant="Whole Foods",
                amount=35.50,
                currency="USD",
                transaction_type=TransactionType.PURCHASE,
            ),
        ),
        EmailAnalysisResult(
            classification=MessageClassification.IGNORED,
            confidence_score=0.98,
        ),
    ]

    stats = scanner.scan()

    assert stats["candidates_found"] == 2
    assert stats["newly_processed"] == 2
    assert stats["transactions_created"] == 1
    assert stats["ignored_count"] == 1
    assert stats["already_processed_skipped"] == 0

    # Verify DB records
    assert db.is_message_processed("account_1", "msg_01")
    assert db.is_message_processed("account_1", "msg_02")

    txs = db.list_transactions(account_id="account_1")
    assert len(txs) == 1
    assert txs[0].merchant == "Whole Foods"
    assert txs[0].amount == 35.50

    # Verify account checkpoint was advanced
    account = db.get_account("account_1")
    assert account.last_scan_timestamp is not None


def test_scan_deduplication_prevents_duplicate_calls(mock_scanner):
    """Verify that already-processed messages are skipped without calling extractor."""
    scanner, db, mock_gmail, mock_extractor = mock_scanner

    # Seed an already processed message in DB
    db.record_processed_message(
        account_id="account_1",
        message_id="msg_existing",
        thread_id="th_ext",
        received_at="2026-10-20T10:00:00Z",
        subject="Old Alert",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )

    mock_gmail.list_messages.return_value = {
        "messages": [
            {"id": "msg_existing"},  # Already in DB
            {"id": "msg_brand_new"},  # New
        ]
    }

    mock_gmail.get_message_detail.return_value = {
        "message_id": "msg_brand_new",
        "thread_id": "th_new",
        "subject": "Starbucks Alert",
        "sender": "alerts@bank.com",
        "date": "2026-10-26T08:00:00Z",
        "body": "$6.25 spent at Starbucks",
    }

    mock_extractor.analyze_email.return_value = EmailAnalysisResult(
        classification=MessageClassification.TRANSACTION,
        confidence_score=0.99,
        transaction=TransactionExtraction(
            merchant="Starbucks",
            amount=6.25,
            transaction_type=TransactionType.PURCHASE,
        ),
    )

    stats = scanner.scan()

    assert stats["candidates_found"] == 2
    assert stats["already_processed_skipped"] == 1
    assert stats["newly_processed"] == 1
    assert stats["transactions_created"] == 1

    # Ensure get_message_detail and extractor were called only ONCE for the new message
    assert mock_gmail.get_message_detail.call_count == 1
    assert mock_extractor.analyze_email.call_count == 1


def test_scan_error_isolation(mock_scanner):
    """Verify that an error on one message doesn't abort the remaining batch."""
    scanner, db, mock_gmail, mock_extractor = mock_scanner

    mock_gmail.list_messages.return_value = {
        "messages": [
            {"id": "msg_bad"},
            {"id": "msg_good"},
        ]
    }

    # First message fails during get_message_detail
    mock_gmail.get_message_detail.side_effect = [
        Exception("Transient network timeout on msg_bad"),
        {
            "message_id": "msg_good",
            "thread_id": "th_good",
            "subject": "Good Alert",
            "sender": "bank@alerts.com",
            "date": "2026-10-27T08:00:00Z",
            "body": "$12.00 at CVS",
        },
    ]

    mock_extractor.analyze_email.return_value = EmailAnalysisResult(
        classification=MessageClassification.TRANSACTION,
        confidence_score=0.90,
        transaction=TransactionExtraction(merchant="CVS", amount=12.00),
    )

    stats = scanner.scan()

    assert stats["candidates_found"] == 2
    assert stats["errors"] == 1
    assert stats["newly_processed"] == 1
    assert stats["transactions_created"] == 1

    # Good message is saved
    assert db.is_message_processed("account_1", "msg_good")
    # Bad message was not saved and will be retried in next scan
    assert not db.is_message_processed("account_1", "msg_bad")
