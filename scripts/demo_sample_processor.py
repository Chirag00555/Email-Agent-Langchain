"""Demonstration runner for Phase 3: LangChain & Groq Email Extraction.

Processes the synthetic sample email fixtures through the LangChain extractor.
If GROQ_API_KEY is configured in .env, it runs live against the configured Groq model.
Otherwise, it informs the user how to configure GROQ_API_KEY.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.extractor import EmailExtractor
from tests.fixtures.sample_emails import SAMPLE_EMAILS


def main():
    print("=" * 70)
    print("Phase 3 Demo: Synthetic Email Classification & Extraction")
    print("=" * 70)

    settings = get_settings()
    summary = settings.sanitized_summary()
    print(f"Model: {summary['groq_model']}")
    print(f"Groq API Key Configured: {summary['groq_api_key_configured']}\n")

    if not settings.groq_api_key:
        print("[!] GROQ_API_KEY is not set in .env.")
        print("To run live extraction against Groq:")
        print("  1. Copy .env.example to .env (if not already done)")
        print("  2. Add your Groq API key: GROQ_API_KEY=gsk_...")
        print("  3. Run this script again: python scripts/demo_sample_processor.py\n")
        print("Running unit tests with deterministic fixtures instead:")
        print("  pytest tests/test_extractor.py")
        return

    print("Initializing EmailExtractor with live ChatGroq instance...")
    try:
        extractor = EmailExtractor(settings=settings)
    except Exception as e:
        print(f"Failed to initialize ChatGroq: {e}")
        return

    print(f"Processing {len(SAMPLE_EMAILS)} synthetic email fixtures:\n")

    for idx, sample in enumerate(SAMPLE_EMAILS, 1):
        print(f"--- [{idx}/{len(SAMPLE_EMAILS)}] Subject: {sample['subject']} ---")
        try:
            result = extractor.analyze_email(
                subject=sample["subject"],
                sender=sample["sender"],
                body=sample["body"],
                date=sample["date"],
                account_type=sample["account_type"],
            )

            print(f"  Classification   : {result.classification.value.upper()}")
            print(f"  Confidence       : {result.confidence_score:.2f}")
            print(f"  Reasoning        : {result.reasoning}")

            if result.transaction:
                tx = result.transaction
                print(f"  [Transaction Data]")
                print(f"    Merchant       : {tx.merchant}")
                print(f"    Amount         : {tx.currency} {tx.amount}")
                print(f"    Card Last 4    : {tx.card_last_four}")
                print(f"    Type           : {tx.transaction_type.value}")
                print(f"    Needs Review   : {tx.needs_review}")
                if tx.uncertainty_notes:
                    print(f"    Uncertainty    : {tx.uncertainty_notes}")

            if result.job_event:
                jb = result.job_event
                print(f"  [Job Event Data]")
                print(f"    Company        : {jb.company}")
                print(f"    Role           : {jb.role_title}")
                print(f"    Event Type     : {jb.event_type.value}")
                print(f"    Interview Time : {jb.interview_datetime} ({jb.timezone})")
                print(f"    Meeting Link   : {jb.meeting_link}")
                print(f"    Next Step      : {jb.next_step}")
                print(f"    Needs Review   : {jb.needs_review}")
                if jb.uncertainty_notes:
                    print(f"    Uncertainty    : {jb.uncertainty_notes}")

        except Exception as err:
            print(f"  Extraction error: {err}")

        print()


if __name__ == "__main__":
    main()
