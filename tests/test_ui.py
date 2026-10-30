"""Unit tests for Streamlit UI utilities and formatting functions."""

from app import make_gmail_url
from src.db import DatabaseManager
from src.models import MessageClassification, ReviewStatus, TransactionExtraction


def test_make_gmail_url():
    """Verify Gmail direct message URL builder."""
    msg_id = "18a12345678abcdef"
    url = make_gmail_url(msg_id)
    assert url == f"https://mail.google.com/mail/u/0/#all/{msg_id}"


def test_category_update_flow(tmp_path):
    """Verify category hint updating and review status transition."""
    db = DatabaseManager(db_path=tmp_path / "ui_test.db")
    db.upsert_account("account_1", "test@gmail.com", "transactions")

    db.record_processed_message(
        account_id="account_1",
        message_id="msg_ui_1",
        thread_id=None,
        received_at="2026-10-30T10:00:00Z",
        subject="Charge Alert",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )

    tx_id = db.create_transaction(
        account_id="account_1",
        message_id="msg_ui_1",
        extraction=TransactionExtraction(merchant="Lyft", amount=22.40),
        category_hint="uncategorized",
    )

    # Initially uncategorized & needs_review
    tx = db.get_transaction_by_id(tx_id)
    assert tx.category_hint == "uncategorized"
    assert tx.review_status == ReviewStatus.NEEDS_REVIEW

    # User selects "travel & transport"
    db.update_transaction_category(tx_id, "travel & transport", mark_reviewed=True)
    updated_tx = db.get_transaction_by_id(tx_id)
    assert updated_tx.category_hint == "travel & transport"
    assert updated_tx.review_status == ReviewStatus.REVIEWED

    # Spending report immediately reflects updated category
    summaries = db.get_spending_summaries()
    cat_hints = [c["category_hint"] for c in summaries["by_category"]]
    assert "travel & transport" in cat_hints
