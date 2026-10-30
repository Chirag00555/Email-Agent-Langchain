"""Scanner module: orchestrates Gmail retrieval, LangChain extraction, and SQLite persistence."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config import Settings, get_settings
from src.db import DatabaseManager
from src.extractor import EmailExtractor
from src.gmail_client import GmailClient
from src.models import (
    JobEventExtraction,
    MessageClassification,
    ReviewStatus,
    TransactionExtraction,
)

logger = logging.getLogger("email_agent.scanner")


class AccountScanner:
    """Orchestrates message ingestion, deduplication, LLM extraction, and DB storage."""

    def __init__(
        self,
        account_id: str,
        account_type: Optional[str] = None,
        email_address: Optional[str] = None,
        settings: Optional[Settings] = None,
        db: Optional[DatabaseManager] = None,
        gmail_client: Optional[GmailClient] = None,
        extractor: Optional[EmailExtractor] = None,
    ) -> None:
        self.account_id = account_id
        self.settings = settings or get_settings()

        # Infer account type from settings if not explicitly given
        if account_type is None:
            if account_id == "account_1":
                self.account_type = self.settings.account_1_type
            elif account_id == "account_2":
                self.account_type = self.settings.account_2_type
            elif account_id == "account_3":
                self.account_type = self.settings.account_3_type
            else:
                self.account_type = "jobs"
        else:
            self.account_type = account_type

        # Infer email from settings if not explicitly given
        if email_address is None:
            if account_id == "account_1":
                self.email_address = self.settings.account_1_email
            elif account_id == "account_2":
                self.email_address = self.settings.account_2_email
            elif account_id == "account_3":
                self.email_address = self.settings.account_3_email
            else:
                self.email_address = f"{account_id}@local"
        else:
            self.email_address = email_address

        self.db = db or DatabaseManager(db_path=self.settings.database_path)
        self.gmail_client = gmail_client or GmailClient(account_id=account_id, settings=self.settings)
        self.extractor = extractor or EmailExtractor(settings=self.settings)

        # Ensure account is registered in DB with current configuration
        self._ensure_account_registered()

    def _ensure_account_registered(self) -> None:
        """Register or update account in SQLite with correct email and type."""
        email = self.email_address or f"{self.account_id}@local"
        self.db.upsert_account(
            account_id=self.account_id,
            email=email,
            account_type=self.account_type,
        )

    def build_query(self, custom_query: Optional[str] = None) -> str:
        """Construct broad Gmail search query with checkpoint boundary."""
        if custom_query:
            return custom_query

        # Select broad keyword pre-filter based on account type
        if self.account_type == "transactions":
            base_filter = self.settings.gmail_transaction_query
        elif self.account_type == "jobs":
            base_filter = self.settings.gmail_job_query
        else:
            base_filter = ""

        # Checkpoint date filter if previous scan timestamp exists
        account = self.db.get_account(self.account_id)
        date_filter = ""
        if account and account.last_scan_timestamp:
            try:
                # Format: after:YYYY/MM/DD
                dt = datetime.fromisoformat(account.last_scan_timestamp.replace("Z", "+00:00"))
                date_filter = f"after:{dt.strftime('%Y/%m/%d')}"
            except Exception:
                pass

        parts = [p for p in [base_filter, date_filter] if p]
        return " ".join(parts)

    def scan(
        self,
        query: Optional[str] = None,
        max_messages: int = 20,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Perform an ingestion scan for this account.

        Steps:
        1. Query Gmail API for candidate message headers matching pre-filter.
        2. Filter out already-processed messages in SQLite (deduplication BEFORE LLM call).
        3. Fetch transient message body for new messages only.
        4. Classify and extract structured data via LangChain & Groq.
        5. Persist extracted records to SQLite (raw email bodies are discarded).
        6. Advance scan checkpoint only after successful batch completion.
        """
        scan_start_time = datetime.now(timezone.utc).isoformat()
        effective_query = self.build_query(query)

        stats = {
            "account_id": self.account_id,
            "query_used": effective_query,
            "candidates_found": 0,
            "already_processed_skipped": 0,
            "newly_processed": 0,
            "transactions_created": 0,
            "job_events_created": 0,
            "ignored_count": 0,
            "errors": 0,
            "dry_run": dry_run,
        }

        # 1. Fetch candidate messages
        listing = self.gmail_client.list_messages(query=effective_query, max_results=max_messages)
        candidate_refs = listing.get("messages", [])
        stats["candidates_found"] = len(candidate_refs)

        if not candidate_refs:
            # Advance checkpoint even if no candidates found
            if not dry_run:
                self.db.update_checkpoint(self.account_id, last_scan_timestamp=scan_start_time)
            return stats

        for ref in candidate_refs:
            message_id = ref.get("id")
            if not message_id:
                continue

            # 2. Strict Deduplication Check: Check SQLite BEFORE calling Groq
            if self.db.is_message_processed(self.account_id, message_id):
                stats["already_processed_skipped"] += 1
                continue

            try:
                # 3. Retrieve full message for transient in-memory extraction
                msg_data = self.gmail_client.get_message_detail(message_id)
                thread_id = msg_data.get("thread_id")
                subject = msg_data.get("subject", "")
                sender = msg_data.get("sender", "")
                received_date = msg_data.get("date", "")
                body = msg_data.get("body", "")

                if dry_run:
                    stats["newly_processed"] += 1
                    continue

                # 4. Controlled LangChain extraction
                analysis = self.extractor.analyze_email(
                    subject=subject,
                    sender=sender,
                    body=body,
                    date=received_date,
                    account_type=self.account_type,
                )

                # 5. Persist to SQLite
                # Record in processed_messages (header metadata only; NO BODY STORED)
                self.db.record_processed_message(
                    account_id=self.account_id,
                    message_id=message_id,
                    thread_id=thread_id,
                    received_at=received_date,
                    subject=subject,
                    sender=sender,
                    classification=analysis.classification,
                )
                stats["newly_processed"] += 1

                if analysis.classification == MessageClassification.TRANSACTION and analysis.transaction:
                    self.db.create_transaction(
                        account_id=self.account_id,
                        message_id=message_id,
                        extraction=analysis.transaction,
                        category_hint="uncategorized",
                        review_status=ReviewStatus.NEEDS_REVIEW,
                    )
                    stats["transactions_created"] += 1

                elif analysis.classification == MessageClassification.JOB and analysis.job_event:
                    self.db.create_job_event(
                        account_id=self.account_id,
                        message_id=message_id,
                        extraction=analysis.job_event,
                        review_status=ReviewStatus.NEEDS_REVIEW,
                    )
                    stats["job_events_created"] += 1

                else:
                    stats["ignored_count"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error processing message {message_id} on {self.account_id}: {e}")

        # 6. Advance checkpoint only if not a dry-run and no catastrophic abort
        if not dry_run and stats["errors"] == 0:
            self.db.update_checkpoint(self.account_id, last_scan_timestamp=scan_start_time)

        return stats


def scan_all_accounts(
    settings: Optional[Settings] = None,
    max_messages_per_account: int = 15,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Scan all configured Gmail accounts sequentially."""
    active_settings = settings or get_settings()
    accounts = active_settings.get_configured_accounts()
    results = []

    for acct in accounts:
        account_id = acct["account_id"]
        logger.info(f"Starting scan for {account_id} ({acct['type']})...")
        scanner = AccountScanner(
            account_id=account_id,
            account_type=acct["type"],
            email_address=acct["email"],
            settings=active_settings,
        )
        res = scanner.scan(max_messages=max_messages_per_account, dry_run=dry_run)
        results.append(res)

    return results

