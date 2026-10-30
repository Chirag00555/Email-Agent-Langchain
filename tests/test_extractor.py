"""Unit tests for LangChain & Groq email extraction pipeline using synthetic fixtures."""

from typing import Any, Dict, List, Optional
import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.language_models.chat_models import BaseChatModel

from src.config import Settings
from src.extractor import EmailAnalysisResult, EmailExtractor
from src.models import (
    JobEventExtraction,
    JobEventType,
    MessageClassification,
    TransactionExtraction,
    TransactionType,
)
from tests.fixtures.sample_emails import SAMPLE_EMAILS


from langchain_core.runnables import RunnableLambda


class MockStructuredChatModel(BaseChatModel):
    """Deterministic mock chat model that returns preconfigured EmailAnalysisResults."""

    mock_result: EmailAnalysisResult

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="mocked_content"))]
        )

    @property
    def _llm_type(self) -> str:
        return "mock_structured_chat_model"

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        """Return a RunnableLambda that yields the mock result."""
        return RunnableLambda(lambda _: self.mock_result)



def test_missing_api_key_raises_error():
    """Verify informative error if GROQ_API_KEY is missing and no LLM is injected."""
    settings = Settings(groq_api_key=None)
    with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
        EmailExtractor(settings=settings)


def test_extract_clear_transaction():
    """Verify clear credit card transaction extraction."""
    tx_fixture = SAMPLE_EMAILS[0]  # Trader Joe's $54.30

    expected_output = EmailAnalysisResult(
        classification=MessageClassification.TRANSACTION,
        confidence_score=0.98,
        reasoning="Credit card purchase alert from Chase for Trader Joe's.",
        transaction=TransactionExtraction(
            transaction_date="2026-10-15",
            merchant="Trader Joe's",
            amount=54.30,
            currency="USD",
            card_last_four="8821",
            transaction_type=TransactionType.PURCHASE,
            confidence_score=0.98,
            needs_review=False,
        ),
    )

    mock_llm = MockStructuredChatModel(mock_result=expected_output)
    extractor = EmailExtractor(settings=Settings(), llm=mock_llm)

    result = extractor.analyze_email(
        subject=tx_fixture["subject"],
        sender=tx_fixture["sender"],
        body=tx_fixture["body"],
        date=tx_fixture["date"],
        account_type=tx_fixture["account_type"],
    )

    assert result.classification == MessageClassification.TRANSACTION
    assert result.transaction is not None
    assert result.transaction.merchant == "Trader Joe's"
    assert result.transaction.amount == 54.30
    assert result.transaction.card_last_four == "8821"
    assert result.transaction.needs_review is False


def test_extract_refund_transaction():
    """Verify refund email extraction."""
    refund_fixture = SAMPLE_EMAILS[1]  # Amazon refund $24.99

    expected_output = EmailAnalysisResult(
        classification=MessageClassification.TRANSACTION,
        confidence_score=0.95,
        reasoning="Amazon refund notice to card ending 3341.",
        transaction=TransactionExtraction(
            transaction_date="2026-10-18",
            merchant="Amazon",
            amount=24.99,
            currency="USD",
            card_last_four="3341",
            transaction_type=TransactionType.REFUND,
            confidence_score=0.95,
            needs_review=False,
        ),
    )

    mock_llm = MockStructuredChatModel(mock_result=expected_output)
    extractor = EmailExtractor(settings=Settings(), llm=mock_llm)

    result = extractor.analyze_email(
        subject=refund_fixture["subject"],
        sender=refund_fixture["sender"],
        body=refund_fixture["body"],
        date=refund_fixture["date"],
        account_type=refund_fixture["account_type"],
    )

    assert result.classification == MessageClassification.TRANSACTION
    assert result.transaction is not None
    assert result.transaction.transaction_type == TransactionType.REFUND
    assert result.transaction.amount == 24.99


def test_ambiguous_transaction_flags_review():
    """Verify ambiguous email triggers needs_review and uncertainty notes."""
    ambiguous_fixture = SAMPLE_EMAILS[2]

    expected_output = EmailAnalysisResult(
        classification=MessageClassification.TRANSACTION,
        confidence_score=0.60,
        reasoning="Debit notice with vague merchant and estimated amount.",
        transaction=TransactionExtraction(
            transaction_date="2026-10-20",
            merchant=None,  # Unspecified merchant
            amount=15.00,
            confidence_score=0.60,
            needs_review=True,
            uncertainty_notes="Merchant is unspecified; amount is listed as approximate.",
        ),
    )

    mock_llm = MockStructuredChatModel(mock_result=expected_output)
    extractor = EmailExtractor(settings=Settings(), llm=mock_llm)

    result = extractor.analyze_email(
        subject=ambiguous_fixture["subject"],
        sender=ambiguous_fixture["sender"],
        body=ambiguous_fixture["body"],
        date=ambiguous_fixture["date"],
        account_type=ambiguous_fixture["account_type"],
    )

    assert result.classification == MessageClassification.TRANSACTION
    assert result.transaction is not None
    assert result.transaction.needs_review is True
    assert result.transaction.uncertainty_notes is not None
    assert result.transaction.merchant is None


def test_extract_job_interview():
    """Verify interview invitation extraction with meeting link and date."""
    interview_fixture = SAMPLE_EMAILS[3]

    expected_output = EmailAnalysisResult(
        classification=MessageClassification.JOB,
        confidence_score=0.99,
        reasoning="Technical interview invitation from TechCorp with Google Meet link.",
        job_event=JobEventExtraction(
            company="TechCorp",
            role_title="Senior Python Engineer",
            event_type=JobEventType.INTERVIEW_INVITATION,
            interview_datetime="2026-11-04T14:00:00",
            timezone="EST",
            meeting_link="https://meet.google.com/abc-wxyz-mock",
            next_step="Click Google Meet link at scheduled time",
            confidence_score=0.99,
            needs_review=False,
        ),
    )

    mock_llm = MockStructuredChatModel(mock_result=expected_output)
    extractor = EmailExtractor(settings=Settings(), llm=mock_llm)

    result = extractor.analyze_email(
        subject=interview_fixture["subject"],
        sender=interview_fixture["sender"],
        body=interview_fixture["body"],
        date=interview_fixture["date"],
        account_type=interview_fixture["account_type"],
    )

    assert result.classification == MessageClassification.JOB
    assert result.job_event is not None
    assert result.job_event.company == "TechCorp"
    assert result.job_event.role_title == "Senior Python Engineer"
    assert result.job_event.event_type == JobEventType.INTERVIEW_INVITATION
    assert result.job_event.meeting_link == "https://meet.google.com/abc-wxyz-mock"
    assert result.job_event.timezone == "EST"


def test_extract_ignored_newsletter():
    """Verify promo newsletter is classified as ignored with empty transaction/job."""
    newsletter_fixture = SAMPLE_EMAILS[6]

    expected_output = EmailAnalysisResult(
        classification=MessageClassification.IGNORED,
        confidence_score=0.95,
        reasoning="Promotional newsletter and tech digest.",
        transaction=None,
        job_event=None,
    )

    mock_llm = MockStructuredChatModel(mock_result=expected_output)
    extractor = EmailExtractor(settings=Settings(), llm=mock_llm)

    result = extractor.analyze_email(
        subject=newsletter_fixture["subject"],
        sender=newsletter_fixture["sender"],
        body=newsletter_fixture["body"],
        date=newsletter_fixture["date"],
        account_type=newsletter_fixture["account_type"],
    )

    assert result.classification == MessageClassification.IGNORED
    assert result.transaction is None
    assert result.job_event is None
