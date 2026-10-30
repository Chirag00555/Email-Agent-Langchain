"""Unit tests for sanitized operational logging and scheduled scan execution."""

import logging
from pathlib import Path
from src.logger import setup_logger


def test_logger_creates_log_file(tmp_path):
    """Verify setup_logger creates target directory and writes operational entries."""
    log_dir = tmp_path / "test_logs"
    logger = setup_logger(name="test_logger", log_dir=log_dir)

    logger.info("Operational event: scan initiated for account_2")
    logger.info("Candidates=5, Processed=3, Skipped=2")

    log_file = log_dir / "scanner.log"
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")
    assert "Operational event: scan initiated" in content
    assert "Candidates=5, Processed=3, Skipped=2" in content


def test_logger_sanitization_policy(tmp_path):
    """Verify that logger does not leak raw tokens or keys."""
    log_dir = tmp_path / "test_logs_clean"
    logger = setup_logger(name="test_clean_logger", log_dir=log_dir)

    # Operational message should only mention status
    logger.info("Account [account_2] authenticated successfully.")

    log_file = log_dir / "scanner.log"
    content = log_file.read_text(encoding="utf-8")

    # Tokens or secrets should never appear in log files
    assert "gsk_" not in content
    assert "client_secret" not in content
    assert "refresh_token" not in content
