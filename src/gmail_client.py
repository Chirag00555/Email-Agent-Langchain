"""Google OAuth and Gmail API client with strict read-only access."""

import base64
import html
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from src.config import Settings, get_settings

# STRICT READ-ONLY SCOPE: Zero modification, sending, or deletion capabilities
GMAIL_READONLY_SCOPE = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailClient:
    """Manages read-only Gmail API interactions for an individual account."""

    def __init__(
        self,
        account_id: str,
        settings: Optional[Settings] = None,
        service: Optional[Resource] = None,
    ) -> None:
        self.account_id = account_id
        self.settings = settings or get_settings()
        self.token_path: Path = self.settings.tokens_dir / f"{account_id}.json"
        self._service: Optional[Resource] = service

    def get_credentials(self, interactive: bool = False) -> Credentials:
        """Load or refresh credentials for this account; optionally prompt OAuth flow."""
        creds: Optional[Credentials] = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), GMAIL_READONLY_SCOPE
            )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)

        if not creds or not creds.valid:
            if not interactive:
                raise FileNotFoundError(
                    f"No valid token found at '{self.token_path}'. "
                    f"Run the interactive authorization script for '{self.account_id}'."
                )

            if not self.settings.google_credentials_file.exists():
                raise FileNotFoundError(
                    f"Google Cloud credentials file '{self.settings.google_credentials_file}' not found. "
                    "Download your Desktop OAuth client secret JSON from Google Cloud Console "
                    "and place it as 'credentials.json' in the project root."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.settings.google_credentials_file),
                GMAIL_READONLY_SCOPE,
            )
            creds = flow.run_local_server(port=0)
            self._save_credentials(creds)

        return creds

    def _save_credentials(self, creds: Credentials) -> None:
        """Safely persist credentials to tokens directory."""
        self.settings.tokens_dir.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    def get_service(self) -> Resource:
        """Obtain or build Google API service resource."""
        if self._service is None:
            creds = self.get_credentials(interactive=False)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def test_connection(self) -> Dict[str, Any]:
        """Verify API connectivity and return authenticated user's email profile."""
        service = self.get_service()
        profile = service.users().getProfile(userId="me").execute()
        return {
            "account_id": self.account_id,
            "email_address": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
            "history_id": profile.get("historyId"),
        }

    def list_messages(
        self,
        query: str = "",
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch a page of message references matching a query."""
        service = self.get_service()
        kwargs: Dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
        }
        if query:
            kwargs["q"] = query
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        return {
            "messages": response.get("messages", []),
            "next_page_token": response.get("nextPageToken"),
            "result_size_estimate": response.get("resultSizeEstimate", 0),
        }

    def get_message_detail(self, message_id: str) -> Dict[str, Any]:
        """Fetch and parse full message metadata and transient plain-text content."""
        service = self.get_service()
        raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        return self.parse_raw_message(raw)

    @classmethod
    def parse_raw_message(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Extract headers and decode body text from Gmail API message payload."""
        message_id = raw.get("id", "")
        thread_id = raw.get("threadId", "")
        payload = raw.get("payload", {})
        headers_list = payload.get("headers", [])

        headers: Dict[str, str] = {}
        for h in headers_list:
            headers[h.get("name", "").lower()] = h.get("value", "")

        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date = headers.get("date", "")

        body_text = cls._extract_body(payload)

        return {
            "message_id": message_id,
            "thread_id": thread_id,
            "subject": subject,
            "sender": sender,
            "date": date,
            "snippet": raw.get("snippet", ""),
            "body": body_text,
        }

    @classmethod
    def _extract_body(cls, payload: Dict[str, Any]) -> str:
        """Recursively decode body text prioritizing plain text over converted HTML."""
        plain_parts: List[str] = []
        html_parts: List[str] = []

        def _walk_parts(part: Dict[str, Any]) -> None:
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")

            if data:
                try:
                    # Gmail API uses URL-safe base64 encoding
                    decoded = base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8", errors="replace")
                    if mime_type == "text/plain":
                        plain_parts.append(decoded)
                    elif mime_type == "text/html":
                        html_parts.append(decoded)
                except Exception:
                    pass

            for subpart in part.get("parts", []):
                _walk_parts(subpart)

        _walk_parts(payload)

        if plain_parts:
            return "\n\n".join(plain_parts).strip()
        elif html_parts:
            # Fall back to stripped HTML
            return cls._clean_html("\n\n".join(html_parts))

        return ""

    @staticmethod
    def _clean_html(raw_html: str) -> str:
        """Convert HTML tags into clean, normalized plain text, stripping scripts/styles."""
        # Strip script, style, and head blocks including their contents
        text = re.sub(r"<(?:script|style|head)[^>]*>.*?</(?:script|style|head)>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        # Replace line breaks and block tags with newlines
        text = re.sub(r"<(?:br|p|div|tr|h\d)[\s/>]", "\n", text, flags=re.IGNORECASE)
        # Remove remaining tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities (e.g., &amp;, &#39;)
        text = html.unescape(text)
        # Collapse excessive whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()
