"""Unit tests for database backup, disaster recovery, and access revocation."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from scripts.backup_db import create_backup, restore_backup
from scripts.revoke_access import revoke_account
from src.db import DatabaseManager
from src.models import MessageClassification, TransactionExtraction


@pytest.fixture
def populated_db(tmp_path):
    """Provide a database pre-populated with sample data."""
    db_file = tmp_path / "live.db"
    db = DatabaseManager(db_path=db_file)
    db.upsert_account("account_2", "bank@gmail.com", "transactions")

    db.record_processed_message(
        account_id="account_2",
        message_id="msg_b1",
        thread_id=None,
        received_at="2026-10-30T10:00:00Z",
        subject="Charge Alert",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )
    db.create_transaction(
        account_id="account_2",
        message_id="msg_b1",
        extraction=TransactionExtraction(merchant="Best Buy", amount=99.99),
    )
    return db_file, db


def test_create_and_verify_backup(populated_db, tmp_path):
    """Verify online backup creates a valid, identical clone of SQLite data."""
    db_file, db = populated_db
    backup_dir = tmp_path / "backups"

    backup_file = create_backup(db_file, backup_dir)
    assert backup_file.exists()

    # Read from the backup database
    backup_db = DatabaseManager(db_path=backup_file)
    txs = backup_db.list_transactions(account_id="account_2")
    assert len(txs) == 1
    assert txs[0].merchant == "Best Buy"
    assert txs[0].amount == 99.99


def test_restore_database(populated_db, tmp_path):
    """Verify restoration replaces target database and creates pre-restore safety copy."""
    db_file, db = populated_db
    backup_dir = tmp_path / "backups"

    # Make initial backup
    backup_file = create_backup(db_file, backup_dir)

    # Mutate live database by adding another transaction
    db.record_processed_message(
        account_id="account_2",
        message_id="msg_b2",
        thread_id=None,
        received_at="2026-10-30T11:00:00Z",
        subject="Charge 2",
        sender="bank@alerts.com",
        classification=MessageClassification.TRANSACTION,
    )
    db.create_transaction(
        account_id="account_2",
        message_id="msg_b2",
        extraction=TransactionExtraction(merchant="Apple Store", amount=299.00),
    )
    assert len(db.list_transactions(account_id="account_2")) == 2

    # Restore from the first backup
    restore_backup(backup_file, db_file)

    # Re-open and verify only 1 transaction remains
    restored_db = DatabaseManager(db_path=db_file)
    assert len(restored_db.list_transactions(account_id="account_2")) == 1

    # Verify safety copy was generated
    safety_file = db_file.parent / f"{db_file.name}.pre_restore_safety"
    assert safety_file.exists()


def test_revoke_account_removes_token_file(tmp_path):
    """Verify revoke_account deletes local token file and invokes revocation call."""
    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir(parents=True)
    token_file = tokens_dir / "account_test.json"

    with open(token_file, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": "mock_refresh_token_xyz"}, f)

    assert token_file.exists()

    with patch("scripts.revoke_access.revoke_token_serverside", return_value=True) as mock_rev:
        revoke_account("account_test", tokens_dir)
        mock_rev.assert_called_once_with("mock_refresh_token_xyz")

    assert not token_file.exists()
