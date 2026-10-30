"""Unit tests for Gmail client, MIME decoding, and read-only authorization logic."""

import base64
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.config import Settings
from src.gmail_client import GMAIL_READONLY_SCOPE, GmailClient


def test_gmail_scope_is_strictly_readonly():
    """Verify scope is strictly limited to gmail.readonly."""
    assert len(GMAIL_READONLY_SCOPE) == 1
    assert GMAIL_READONLY_SCOPE[0] == "https://www.googleapis.com/auth/gmail.readonly"


def test_missing_token_raises_filenotfound(tmp_path):
    """Attempting non-interactive access without saved token raises FileNotFoundError."""
    settings = Settings(tokens_dir=tmp_path / "tokens")
    client = GmailClient(account_id="account_1", settings=settings)

    with pytest.raises(FileNotFoundError, match="No valid token found"):
        client.get_credentials(interactive=False)


def test_missing_credentials_file_raises_error(tmp_path):
    """Interactive authorization without credentials.json raises FileNotFoundError."""
    settings = Settings(
        tokens_dir=tmp_path / "tokens",
        google_credentials_file=tmp_path / "non_existent_creds.json",
    )
    client = GmailClient(account_id="account_1", settings=settings)

    with pytest.raises(FileNotFoundError, match="Google Cloud credentials file"):
        client.get_credentials(interactive=True)


def test_clean_html_utility():
    """Verify HTML stripping and entity unescaping."""
    raw_html = "<p>Your bill is <b>$25.00</b> &amp; due tomorrow.<br>Click <a href='http://link'>here</a>.</p>"
    cleaned = GmailClient._clean_html(raw_html)
    assert "$25.00" in cleaned
    assert "&" in cleaned
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned


def test_parse_raw_message_plain_text():
    """Verify parsing a single-part plain text email payload."""
    body_content = "Your transaction of $45.00 at Target was approved."
    encoded_body = base64.urlsafe_b64encode(body_content.encode("utf-8")).decode("utf-8")

    raw_payload = {
        "id": "18a12345678",
        "threadId": "18a12345678_th",
        "snippet": "Your transaction of $45.00...",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Transaction Confirmation"},
                {"name": "From", "value": "alerts@bank.com"},
                {"name": "Date", "value": "Thu, 29 Oct 2026 12:00:00 -0400"},
            ],
            "body": {
                "data": encoded_body,
            },
        },
    }

    parsed = GmailClient.parse_raw_message(raw_payload)
    assert parsed["message_id"] == "18a12345678"
    assert parsed["thread_id"] == "18a12345678_th"
    assert parsed["subject"] == "Transaction Confirmation"
    assert parsed["sender"] == "alerts@bank.com"
    assert parsed["date"] == "Thu, 29 Oct 2026 12:00:00 -0400"
    assert parsed["body"] == body_content


def test_parse_raw_message_multipart():
    """Verify parsing a multipart message prioritizing plain text."""
    plain_content = "Plain text interview invitation details."
    html_content = "<html><body><b>HTML</b> interview invitation details.</body></html>"

    encoded_plain = base64.urlsafe_b64encode(plain_content.encode("utf-8")).decode("utf-8")
    encoded_html = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("utf-8")

    raw_payload = {
        "id": "msg_multipart_01",
        "threadId": "th_multipart_01",
        "snippet": "Plain text interview...",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": "Interview Next Steps"},
                {"name": "From", "value": "recruiter@hiring.com"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_plain},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded_html},
                },
            ],
        },
    }

    parsed = GmailClient.parse_raw_message(raw_payload)
    assert parsed["message_id"] == "msg_multipart_01"
    assert parsed["subject"] == "Interview Next Steps"
    assert parsed["body"] == plain_content


def test_client_with_mocked_service():
    """Verify test_connection and list_messages with a mocked Google Resource."""
    mock_service = MagicMock()

    # Mock getProfile
    mock_service.users().getProfile(userId="me").execute.return_value = {
        "emailAddress": "test.user@gmail.com",
        "messagesTotal": 1420,
        "historyId": "998877",
    }

    # Mock messages.list
    mock_service.users().messages().list.return_value.execute.return_value = {
        "messages": [{"id": "m1", "threadId": "t1"}],
        "resultSizeEstimate": 1,
    }

    client = GmailClient(account_id="account_1", service=mock_service)

    # Test profile connection
    profile = client.test_connection()
    assert profile["email_address"] == "test.user@gmail.com"
    assert profile["messages_total"] == 1420

    # Test list messages
    listing = client.list_messages(query="receipt", max_results=5)
    assert len(listing["messages"]) == 1
    assert listing["messages"][0]["id"] == "m1"
