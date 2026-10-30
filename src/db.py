"""Database management and persistence layer using SQLite."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple, Union

from src.models import (
    AccountRecord,
    JobEventExtraction,
    JobEventRecord,
    JobEventType,
    MessageClassification,
    ProcessedMessageRecord,
    ReviewStatus,
    TransactionExtraction,
    TransactionRecord,
    TransactionType,
)

DEFAULT_SPENDING_CATEGORIES = [
    "uncategorized",
    "groceries",
    "dining & food",
    "textbooks & education",
    "utilities & bills",
    "shopping",
    "entertainment",
    "travel & transport",
    "subscriptions",
]


def current_iso_timestamp() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """Encapsulates SQLite connection management and CRUD operations."""

    def __init__(self, db_path: Union[str, Path] = "data/email_agent.db") -> None:
        self.db_path = Path(db_path)
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual database connection with foreign keys and WAL mode."""
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            if self.db_path != Path(":memory:"):
                conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create tables, indexes, and seed default spending categories."""
        schema_sql = """
        -- Authorized Gmail accounts and per-account checkpoints
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            account_type TEXT NOT NULL,
            last_history_id TEXT,
            last_scan_timestamp TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- Ingested Gmail messages (strict composite primary key prevents duplicate processing)
        -- Raw email bodies are intentionally NOT stored in accordance with privacy rules.
        CREATE TABLE IF NOT EXISTS processed_messages (
            account_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            thread_id TEXT,
            received_at TEXT,
            subject TEXT,
            sender TEXT,
            classification TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (account_id, message_id),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );

        -- Extracted credit card transactions
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            transaction_date TEXT,
            merchant TEXT,
            amount REAL,
            currency TEXT NOT NULL DEFAULT 'USD',
            card_last_four TEXT,
            transaction_type TEXT NOT NULL DEFAULT 'purchase',
            category_hint TEXT NOT NULL DEFAULT 'uncategorized',
            review_status TEXT NOT NULL DEFAULT 'needs_review',
            confidence_score REAL,
            uncertainty_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (account_id, message_id),
            FOREIGN KEY (account_id, message_id) REFERENCES processed_messages(account_id, message_id) ON DELETE CASCADE
        );

        -- Extracted job applications and interview events
        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            company TEXT,
            role_title TEXT,
            event_type TEXT NOT NULL DEFAULT 'unknown',
            interview_datetime TEXT,
            timezone TEXT,
            meeting_link TEXT,
            next_step TEXT,
            review_status TEXT NOT NULL DEFAULT 'needs_review',
            confidence_score REAL,
            uncertainty_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (account_id, message_id),
            FOREIGN KEY (account_id, message_id) REFERENCES processed_messages(account_id, message_id) ON DELETE CASCADE
        );

        -- Predefined and user-customized spending categories
        CREATE TABLE IF NOT EXISTS spending_categories (
            name TEXT PRIMARY KEY,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        -- Helpful indexes for lookup and reporting
        CREATE INDEX IF NOT EXISTS idx_trans_account ON transactions(account_id);
        CREATE INDEX IF NOT EXISTS idx_trans_category ON transactions(category_hint);
        CREATE INDEX IF NOT EXISTS idx_trans_date ON transactions(transaction_date);
        CREATE INDEX IF NOT EXISTS idx_job_account ON job_events(account_id);
        CREATE INDEX IF NOT EXISTS idx_job_event_type ON job_events(event_type);
        """
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            now = current_iso_timestamp()
            for cat in DEFAULT_SPENDING_CATEGORIES:
                conn.execute(
                    "INSERT OR IGNORE INTO spending_categories (name, is_default, created_at) VALUES (?, 1, ?)",
                    (cat, now),
                )

    # ==========================================================================
    # Accounts & Scan Checkpoint Operations
    # ==========================================================================

    def upsert_account(self, account_id: str, email: str, account_type: str) -> AccountRecord:
        """Register or update an authorized Gmail account."""
        now = current_iso_timestamp()
        sql = """
        INSERT INTO accounts (account_id, email, account_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            email = excluded.email,
            account_type = excluded.account_type,
            updated_at = excluded.updated_at
        """
        with self.get_connection() as conn:
            conn.execute(sql, (account_id, email, account_type, now, now))
        record = self.get_account(account_id)
        if not record:
            raise RuntimeError(f"Failed to upsert account {account_id}")
        return record

    def get_account(self, account_id: str) -> Optional[AccountRecord]:
        """Fetch account record by its unique account_id."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            if row:
                return AccountRecord(**dict(row))
        return None

    def list_accounts(self) -> List[AccountRecord]:
        """Retrieve all registered accounts."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM accounts ORDER BY account_id")
            return [AccountRecord(**dict(row)) for row in cursor.fetchall()]

    def update_checkpoint(
        self,
        account_id: str,
        last_scan_timestamp: str,
        last_history_id: Optional[str] = None
    ) -> None:
        """Advance an account's checkpoint after a successful scan."""
        now = current_iso_timestamp()
        sql = """
        UPDATE accounts
        SET last_scan_timestamp = ?,
            last_history_id = COALESCE(?, last_history_id),
            updated_at = ?
        WHERE account_id = ?
        """
        with self.get_connection() as conn:
            conn.execute(sql, (last_scan_timestamp, last_history_id, now, account_id))

    # ==========================================================================
    # Processed Messages & Deduplication Operations
    # ==========================================================================

    def is_message_processed(self, account_id: str, message_id: str) -> bool:
        """Check if an email from a specific account has already been processed."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_messages WHERE account_id = ? AND message_id = ?",
                (account_id, message_id),
            )
            return cursor.fetchone() is not None

    def record_processed_message(
        self,
        account_id: str,
        message_id: str,
        thread_id: Optional[str],
        received_at: Optional[str],
        subject: Optional[str],
        sender: Optional[str],
        classification: MessageClassification,
    ) -> ProcessedMessageRecord:
        """Record an ingested message header to enforce deduplication."""
        now = current_iso_timestamp()
        sql = """
        INSERT INTO processed_messages (
            account_id, message_id, thread_id, received_at,
            subject, sender, classification, processed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        classification_val = (
            classification.value if hasattr(classification, "value") else str(classification)
        )
        with self.get_connection() as conn:
            conn.execute(
                sql,
                (
                    account_id,
                    message_id,
                    thread_id,
                    received_at,
                    subject,
                    sender,
                    classification_val,
                    now,
                ),
            )
        enum_class = (
            classification
            if isinstance(classification, MessageClassification)
            else MessageClassification(classification_val)
        )
        return ProcessedMessageRecord(
            account_id=account_id,
            message_id=message_id,
            thread_id=thread_id,
            received_at=received_at,
            subject=subject,
            sender=sender,
            classification=enum_class,
            processed_at=now,
        )

    def save_extracted_message(
        self,
        account_id: str,
        message_id: str,
        thread_id: Optional[str],
        received_at: Optional[str],
        subject: Optional[str],
        sender: Optional[str],
        classification: MessageClassification,
        transaction: Optional[TransactionExtraction] = None,
        job_event: Optional[JobEventExtraction] = None,
        category_hint: str = "uncategorized",
    ) -> None:
        """Atomically persist a message header and its extracted child record.

        If either insert fails, the transaction is completely rolled back, preventing
        orphan records or premature deduplication markers.
        """
        now = current_iso_timestamp()
        classification_val = (
            classification.value if hasattr(classification, "value") else str(classification)
        )

        with self.get_connection() as conn:
            # 1. Insert header
            conn.execute(
                """
                INSERT INTO processed_messages (
                    account_id, message_id, thread_id, received_at,
                    subject, sender, classification, processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    message_id,
                    thread_id,
                    received_at,
                    subject,
                    sender,
                    classification_val,
                    now,
                ),
            )

            # 2. Insert transaction child record if applicable
            if classification == MessageClassification.TRANSACTION and transaction:
                effective_review = (
                    ReviewStatus.NEEDS_REVIEW
                    if transaction.needs_review or transaction.confidence_score < 0.8
                    else ReviewStatus.NEEDS_REVIEW
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        account_id, message_id, transaction_date, merchant,
                        amount, currency, card_last_four, transaction_type,
                        category_hint, review_status, confidence_score,
                        uncertainty_notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        message_id,
                        transaction.transaction_date,
                        transaction.merchant,
                        transaction.amount,
                        transaction.currency or "USD",
                        transaction.card_last_four,
                        transaction.transaction_type.value,
                        category_hint,
                        effective_review.value,
                        transaction.confidence_score,
                        transaction.uncertainty_notes,
                        now,
                        now,
                    ),
                )

            # 3. Insert job event child record if applicable
            elif classification == MessageClassification.JOB and job_event:
                effective_review = (
                    ReviewStatus.NEEDS_REVIEW
                    if job_event.needs_review or job_event.confidence_score < 0.8
                    else ReviewStatus.NEEDS_REVIEW
                )
                conn.execute(
                    """
                    INSERT INTO job_events (
                        account_id, message_id, company, role_title,
                        event_type, interview_datetime, timezone,
                        meeting_link, next_step, review_status,
                        confidence_score, uncertainty_notes,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        message_id,
                        job_event.company,
                        job_event.role_title,
                        job_event.event_type.value,
                        job_event.interview_datetime,
                        job_event.timezone,
                        job_event.meeting_link,
                        job_event.next_step,
                        effective_review.value,
                        job_event.confidence_score,
                        job_event.uncertainty_notes,
                        now,
                        now,
                    ),
                )

    # ==========================================================================
    # Transactions Operations
    # ==========================================================================

    def create_transaction(
        self,
        account_id: str,
        message_id: str,
        extraction: TransactionExtraction,
        category_hint: str = "uncategorized",
        review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW,
    ) -> int:
        """Persist an extracted transaction linked to a processed message."""
        now = current_iso_timestamp()
        # Default review status flags if confidence is low or needs_review requested
        effective_review = (
            ReviewStatus.NEEDS_REVIEW
            if extraction.needs_review or extraction.confidence_score < 0.8
            else review_status
        )

        sql = """
        INSERT INTO transactions (
            account_id, message_id, transaction_date, merchant,
            amount, currency, card_last_four, transaction_type,
            category_hint, review_status, confidence_score,
            uncertainty_notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    account_id,
                    message_id,
                    extraction.transaction_date,
                    extraction.merchant,
                    extraction.amount,
                    extraction.currency or "USD",
                    extraction.card_last_four,
                    extraction.transaction_type.value,
                    category_hint,
                    effective_review.value,
                    extraction.confidence_score,
                    extraction.uncertainty_notes,
                    now,
                    now,
                ),
            )
            return cursor.lastrowid or 0

    def update_transaction_category(
        self,
        transaction_id: int,
        category_hint: str,
        mark_reviewed: bool = True
    ) -> bool:
        """Update the user-editable spending category hint."""
        now = current_iso_timestamp()
        with self.get_connection() as conn:
            if mark_reviewed:
                cursor = conn.execute(
                    """
                    UPDATE transactions
                    SET category_hint = ?,
                        review_status = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (category_hint, ReviewStatus.REVIEWED.value, now, transaction_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE transactions SET category_hint = ?, updated_at = ? WHERE id = ?",
                    (category_hint, now, transaction_id),
                )
            return cursor.rowcount > 0

    def update_transaction_review_status(
        self,
        transaction_id: int,
        review_status: ReviewStatus
    ) -> bool:
        """Update review status of a transaction."""
        now = current_iso_timestamp()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE transactions SET review_status = ?, updated_at = ? WHERE id = ?",
                (review_status.value, now, transaction_id),
            )
            return cursor.rowcount > 0

    def get_transaction_by_id(self, transaction_id: int) -> Optional[TransactionRecord]:
        """Fetch a single transaction by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            row = cursor.fetchone()
            if row:
                return TransactionRecord(**dict(row))
        return None

    def list_transactions(
        self,
        account_id: Optional[str] = None,
        review_status: Optional[ReviewStatus] = None,
        category_hint: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[TransactionRecord]:
        """List transactions with optional filtering."""
        query = "SELECT * FROM transactions WHERE 1=1"
        params: List[Union[str, int]] = []

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status.value)
        if category_hint:
            query += " AND category_hint = ?"
            params.append(category_hint)

        query += " ORDER BY transaction_date DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [TransactionRecord(**dict(row)) for row in cursor.fetchall()]

    # ==========================================================================
    # Job Events Operations
    # ==========================================================================

    def create_job_event(
        self,
        account_id: str,
        message_id: str,
        extraction: JobEventExtraction,
        review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW,
    ) -> int:
        """Persist an extracted job/interview event linked to a processed message."""
        now = current_iso_timestamp()
        effective_review = (
            ReviewStatus.NEEDS_REVIEW
            if extraction.needs_review or extraction.confidence_score < 0.8
            else review_status
        )

        sql = """
        INSERT INTO job_events (
            account_id, message_id, company, role_title,
            event_type, interview_datetime, timezone,
            meeting_link, next_step, review_status,
            confidence_score, uncertainty_notes,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    account_id,
                    message_id,
                    extraction.company,
                    extraction.role_title,
                    extraction.event_type.value,
                    extraction.interview_datetime,
                    extraction.timezone,
                    extraction.meeting_link,
                    extraction.next_step,
                    effective_review.value,
                    extraction.confidence_score,
                    extraction.uncertainty_notes,
                    now,
                    now,
                ),
            )
            return cursor.lastrowid or 0

    def update_job_event_review_status(
        self,
        job_event_id: int,
        review_status: ReviewStatus
    ) -> bool:
        """Update the review status of a job event."""
        now = current_iso_timestamp()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE job_events SET review_status = ?, updated_at = ? WHERE id = ?",
                (review_status.value, now, job_event_id),
            )
            return cursor.rowcount > 0

    def get_job_event_by_id(self, job_event_id: int) -> Optional[JobEventRecord]:
        """Fetch a single job event by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM job_events WHERE id = ?", (job_event_id,))
            row = cursor.fetchone()
            if row:
                return JobEventRecord(**dict(row))
        return None

    def list_job_events(
        self,
        account_id: Optional[str] = None,
        event_type: Optional[JobEventType] = None,
        review_status: Optional[ReviewStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[JobEventRecord]:
        """List job events with optional filtering."""
        query = "SELECT * FROM job_events WHERE 1=1"
        params: List[Union[str, int]] = []

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status.value)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [JobEventRecord(**dict(row)) for row in cursor.fetchall()]

    # ==========================================================================
    # Spending Categories Operations
    # ==========================================================================

    def list_categories(self) -> List[str]:
        """Return list of all available spending categories."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM spending_categories ORDER BY is_default DESC, name ASC")
            return [row["name"] for row in cursor.fetchall()]

    def add_category(self, name: str) -> bool:
        """Add a custom user-defined spending category."""
        clean_name = name.strip().lower()
        if not clean_name:
            return False
        now = current_iso_timestamp()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO spending_categories (name, is_default, created_at) VALUES (?, 0, ?)",
                (clean_name, now),
            )
            return cursor.rowcount > 0

    # ==========================================================================
    # Aggregated Spending Report Summaries
    # ==========================================================================

    def get_spending_summaries(self, account_id: Optional[str] = None) -> Dict[str, List[Dict[str, Union[str, float, int]]]]:
        """Compute aggregated spending summaries (by category, by merchant, by month)."""
        where_clause = "WHERE 1=1"
        params: List[Union[str, int]] = []
        if account_id:
            where_clause += " AND account_id = ?"
            params.append(account_id)

        with self.get_connection() as conn:
            # By category
            cat_cursor = conn.execute(
                f"""
                SELECT category_hint, COUNT(*) as count, SUM(amount) as total_amount
                FROM transactions
                {where_clause}
                GROUP BY category_hint
                ORDER BY total_amount DESC
                """,
                params,
            )
            by_category = [dict(r) for r in cat_cursor.fetchall()]

            # By merchant
            merch_cursor = conn.execute(
                f"""
                SELECT COALESCE(merchant, 'Unknown') as merchant, COUNT(*) as count, SUM(amount) as total_amount
                FROM transactions
                {where_clause}
                GROUP BY merchant
                ORDER BY total_amount DESC
                LIMIT 20
                """,
                params,
            )
            by_merchant = [dict(r) for r in merch_cursor.fetchall()]

            # By month (YYYY-MM from transaction_date)
            month_cursor = conn.execute(
                f"""
                SELECT substr(COALESCE(transaction_date, created_at), 1, 7) as month,
                       COUNT(*) as count, SUM(amount) as total_amount
                FROM transactions
                {where_clause}
                GROUP BY month
                ORDER BY month DESC
                """,
                params,
            )
            by_month = [dict(r) for r in month_cursor.fetchall()]

            return {
                "by_category": by_category,
                "by_merchant": by_merchant,
                "by_month": by_month,
            }
