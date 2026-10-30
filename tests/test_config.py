"""Unit tests for configuration management."""

import os
from pathlib import Path
from src.config import Settings, get_settings


def test_default_settings():
    """Verify default settings load properly without required env vars."""
    settings = Settings()
    assert settings.groq_model == "openai/gpt-oss-120b"
    assert settings.database_path == Path("data/email_agent.db")
    assert settings.scan_lookback_overlap_hours == 2
    assert "receipt" in settings.gmail_transaction_query
    assert "interview" in settings.gmail_job_query


def test_sanitized_summary_hides_secrets():
    """Verify that sanitized summary masks or hides the Groq API key."""
    settings = Settings(groq_api_key="gsk_secret_1234567890abcdef")
    summary = settings.sanitized_summary()
    assert "gsk_secret" not in str(summary)
    assert summary["groq_api_key_configured"] == "Yes (Masked)"


def test_ensure_directories(tmp_path):
    """Verify directory creation logic works cleanly without crashing."""
    db_path = tmp_path / "custom_data" / "test.db"
    tokens_path = tmp_path / "custom_tokens"
    settings = Settings(database_path=db_path, tokens_dir=tokens_path)
    settings.ensure_directories()

    assert db_path.parent.exists()
    assert tokens_path.exists()


def test_model_override():
    """Verify the Groq model name can be customized."""
    settings = Settings(groq_model="llama-3.3-70b-versatile")
    assert settings.groq_model == "llama-3.3-70b-versatile"
