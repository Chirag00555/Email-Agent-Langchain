"""Controlled LangChain extraction pipeline using Groq and Pydantic."""

from typing import Any, Dict, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.config import Settings, get_settings
from src.models import (
    JobEventExtraction,
    JobEventType,
    MessageClassification,
    ReviewStatus,
    TransactionExtraction,
    TransactionType,
)


class EmailAnalysisResult(BaseModel):
    """Unified classification and extraction payload from LLM."""

    classification: MessageClassification = Field(
        description="High-level category: 'transaction', 'job', 'ignored' (newsletters/spam), or 'uncertain'."
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this classification and extraction between 0.0 and 1.0."
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Short, non-sensitive summary of why this classification was made."
    )
    transaction: Optional[TransactionExtraction] = Field(
        default=None,
        description="Populated ONLY if classification is 'transaction'."
    )
    job_event: Optional[JobEventExtraction] = Field(
        default=None,
        description="Populated ONLY if classification is 'job'."
    )


EXTRACTION_SYSTEM_PROMPT = """You are a precise, deterministic personal email analyzer.
Your task is to classify an incoming email and extract structured data without hallucination.

RULES:
1. STRICT FACTUAL ACCURACY: NEVER invent, hallucinate, or extrapolate dates, numbers, company names, or URLs.
2. MISSING DETAILS: If an expected field is not explicitly present in the email, leave it as null/None. Never guess.
3. UNCERTAINTY FLAGGING: If an email is ambiguous, unclear, or lacks crucial information (such as an unidentified merchant or unclear interview time), set needs_review to True and provide a concise explanation in uncertainty_notes.
4. CLASSIFICATION CRITERIA:
   - "transaction": Real financial transaction alerts, bank purchase notices, credit/debit charges, refunds, or payment confirmations.
   - "job": Job applications, interview invitations, recruitment recruiter outreach, status updates, rejections, or job offers.
   - "ignored": Promotional marketing, spam, generic newsletters, social media digests, or general unrelated communications.
   - "uncertain": Ambiguous emails that may be relevant but cannot be reliably determined.
5. If classified as "transaction", populate the transaction object.
6. If classified as "job", populate the job_event object.
7. If classified as "ignored", leave transaction and job_event null.
"""

EXTRACTION_USER_PROMPT = """Analyze this email:
Source Account Context: {account_type}
Email Subject: {subject}
Sender: {sender}
Received Date: {date}

Email Body:
\"\"\"
{body}
\"\"\"
"""


class EmailExtractor:
    """Orchestrates LangChain classification and extraction via Groq."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm: Optional[BaseChatModel] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or self._build_default_llm()
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("user", EXTRACTION_USER_PROMPT),
        ])
        # LangChain structured output binding
        self.structured_chain = self.prompt | self.llm.with_structured_output(EmailAnalysisResult)

    def _build_default_llm(self) -> BaseChatModel:
        """Instantiate ChatGroq using configured model and API key."""
        if not self.settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured. Set GROQ_API_KEY in your .env file "
                "or pass a custom LLM instance for testing."
            )
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=self.settings.groq_model,
            groq_api_key=self.settings.groq_api_key,
            temperature=0.0,
            max_retries=2,
        )

    def analyze_email(
        self,
        subject: str,
        sender: str,
        body: str,
        date: str = "",
        account_type: str = "general",
    ) -> EmailAnalysisResult:
        """Run classification and extraction over an email text with safe token bounds."""
        # Cap body to ~3500 characters (~800 tokens) to strictly prevent Groq 8,000 TPM limits.
        # Financial alerts and interview invitations always present essential facts at the top.
        clean_body = (body or "").strip()
        if len(clean_body) > 3500:
            clean_body = clean_body[:3500] + "\n\n...[Remaining email body truncated for length]..."

        result: EmailAnalysisResult = self.structured_chain.invoke({
            "account_type": account_type,
            "subject": (subject or "")[:250],
            "sender": (sender or "")[:200],
            "date": date or "",
            "body": clean_body,
        })

        # Post-validation sanity checks to ensure integrity
        if result.classification == MessageClassification.TRANSACTION:
            if result.transaction is None:
                result.transaction = TransactionExtraction(
                    needs_review=True,
                    uncertainty_notes="LLM classified as transaction but returned empty transaction payload.",
                )
            # Inherit overall confidence if not set on child
            if result.confidence_score < 0.8:
                result.transaction.needs_review = True

        elif result.classification == MessageClassification.JOB:
            if result.job_event is None:
                result.job_event = JobEventExtraction(
                    needs_review=True,
                    uncertainty_notes="LLM classified as job but returned empty job payload.",
                )
            if result.confidence_score < 0.8:
                result.job_event.needs_review = True

        return result
