"""Pydantic data models for email analysis, extraction, and persistence."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ReviewStatus(str, Enum):
    """Review status for extracted records."""
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    AUTO_CONFIRMED = "auto_confirmed"


class TransactionType(str, Enum):
    """Categorization of transaction types."""
    PURCHASE = "purchase"
    REFUND = "refund"
    PAYMENT = "payment"
    FEE = "fee"
    OTHER = "other"
    UNKNOWN = "unknown"


class JobEventType(str, Enum):
    """Categorization of job-related email events."""
    APPLICATION_CONFIRMATION = "application_confirmation"
    INTERVIEW_INVITATION = "interview_invitation"
    UPDATE = "update"
    REJECTION = "rejection"
    OFFER = "offer"
    OTHER = "other"
    UNKNOWN = "unknown"


class MessageClassification(str, Enum):
    """High-level classification of an ingested email."""
    TRANSACTION = "transaction"
    JOB = "job"
    IGNORED = "ignored"
    UNCERTAIN = "uncertain"


# ==============================================================================
# Extraction Models (Used by LLM & Validation Layer)
# ==============================================================================

class TransactionExtraction(BaseModel):
    """Structured extraction schema for credit-card transaction alerts."""
    transaction_date: Optional[str] = Field(
        default=None,
        description="Date of the transaction (ISO format YYYY-MM-DD preferred if identifiable, else raw string)."
    )
    merchant: Optional[str] = Field(
        default=None,
        description="Merchant, payee, or institution name. Set None if unknown."
    )
    amount: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Transaction amount as a positive number."
    )
    currency: Optional[str] = Field(
        default="USD",
        description="Three-letter currency code (e.g. USD, EUR, INR, CAD)."
    )
    card_last_four: Optional[str] = Field(
        default=None,
        description="Last four digits of the credit/debit card (e.g., '1234')."
    )
    transaction_type: TransactionType = Field(
        default=TransactionType.PURCHASE,
        description="Type of transaction (purchase, refund, payment, fee, etc.)."
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0."
    )
    uncertainty_notes: Optional[str] = Field(
        default=None,
        description="Explanation of missing, ambiguous, or questionable details."
    )
    needs_review: bool = Field(
        default=False,
        description="Flag set to True if any key fields are missing or ambiguous."
    )

    @field_validator("card_last_four")
    @classmethod
    def validate_card_last_four(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        # Clean any whitespace or formatting
        digits = "".join(filter(str.isdigit, str(v)))
        if len(digits) == 4:
            return digits
        if len(digits) > 4:
            return digits[-4:]
        # If fewer than 4 digits or non-digit, return cleaned or None
        return digits if digits else None


class JobEventExtraction(BaseModel):
    """Structured extraction schema for job applications and interview emails."""
    company: Optional[str] = Field(
        default=None,
        description="Hiring company or organization name."
    )
    role_title: Optional[str] = Field(
        default=None,
        description="Job position or title (e.g., 'Software Engineer')."
    )
    event_type: JobEventType = Field(
        default=JobEventType.UNKNOWN,
        description="Event classification (application_confirmation, interview_invitation, update, rejection, offer)."
    )
    interview_datetime: Optional[str] = Field(
        default=None,
        description="Scheduled interview date/time string, or None if not an interview."
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Timezone of interview if specified (e.g., 'EST', 'PST', 'UTC', 'Asia/Kolkata')."
    )
    meeting_link: Optional[str] = Field(
        default=None,
        description="Link to video call (Zoom, Google Meet, Teams) or location if present."
    )
    next_step: Optional[str] = Field(
        default=None,
        description="Action item or next step indicated in the email."
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0."
    )
    uncertainty_notes: Optional[str] = Field(
        default=None,
        description="Explanation of any missing or ambiguous details."
    )
    needs_review: bool = Field(
        default=False,
        description="Flag set to True if critical details are uncertain."
    )


# ==============================================================================
# Database Record Models (Representing Stored Entities)
# ==============================================================================

class AccountRecord(BaseModel):
    """Database entity representing an authorized Gmail account."""
    account_id: str
    email: str
    account_type: str  # 'transactions' or 'jobs'
    last_history_id: Optional[str] = None
    last_scan_timestamp: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProcessedMessageRecord(BaseModel):
    """Database entity representing a processed email header (no body stored)."""
    account_id: str
    message_id: str
    thread_id: Optional[str] = None
    received_at: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    classification: MessageClassification
    processed_at: Optional[str] = None


class TransactionRecord(BaseModel):
    """Database entity representing a stored transaction record."""
    id: Optional[int] = None
    account_id: str
    message_id: str
    transaction_date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "USD"
    card_last_four: Optional[str] = None
    transaction_type: TransactionType = TransactionType.PURCHASE
    category_hint: str = "uncategorized"
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    confidence_score: Optional[float] = 1.0
    uncertainty_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobEventRecord(BaseModel):
    """Database entity representing a stored job application or interview record."""
    id: Optional[int] = None
    account_id: str
    message_id: str
    company: Optional[str] = None
    role_title: Optional[str] = None
    event_type: JobEventType = JobEventType.UNKNOWN
    interview_datetime: Optional[str] = None
    timezone: Optional[str] = None
    meeting_link: Optional[str] = None
    next_step: Optional[str] = None
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    confidence_score: Optional[float] = 1.0
    uncertainty_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
