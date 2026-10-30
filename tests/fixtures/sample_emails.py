"""Synthetic test email fixtures for Phase 3 development and validation.

All names, institutions, dates, and amounts are completely fictional.
NO real email data is contained in this file.
"""

from typing import Any, Dict, List

SAMPLE_EMAILS: List[Dict[str, Any]] = [
    {
        "id": "sample_tx_01",
        "subject": "Transaction Alert: You made a purchase of $54.30 at Trader Joe's",
        "sender": "alerts@chase-notifications-mock.com",
        "date": "2026-10-15T14:22:00Z",
        "account_type": "transactions",
        "body": """
Hello Chirag,

A charge of $54.30 was authorized on your Sapphire card ending in 8821 at TRADER JOE'S #542 on October 15, 2026.

Transaction Details:
- Merchant: TRADER JOE'S #542
- Amount: $54.30 USD
- Card: ending in 8821
- Date: 10/15/2026

If you did not authorize this transaction, please contact cardmember services immediately.
""",
        "expected_classification": "transaction",
        "expected_merchant": "Trader Joe's",
        "expected_amount": 54.30,
        "expected_card_last_four": "8821",
        "expected_type": "purchase",
    },
    {
        "id": "sample_tx_refund",
        "subject": "Refund Confirmation - Amazon.com",
        "sender": "refunds@amazon-mock.com",
        "date": "2026-10-18T09:10:00Z",
        "account_type": "transactions",
        "body": """
Hi,

Your refund of $24.99 has been processed to your Visa card ending in 3341 for order #112-9876543-1234567.

Refund Amount: $24.99
Card: Visa ending in 3341
Reason: Return received

Please allow 3-5 business days for this credit to appear on your bank statement.
""",
        "expected_classification": "transaction",
        "expected_merchant": "Amazon",
        "expected_amount": 24.99,
        "expected_card_last_four": "3341",
        "expected_type": "refund",
    },
    {
        "id": "sample_tx_ambiguous",
        "subject": "Debit notice for your account",
        "sender": "alerts@mysterybank-mock.com",
        "date": "2026-10-20T11:00:00Z",
        "account_type": "transactions",
        "body": """
Notice: An unspecified recurring debit was processed today for your checking account.
Amount: approximately $15.
Reference code: POS-TX-9901.
""",
        "expected_classification": "transaction",
        "expected_needs_review": True,
    },
    {
        "id": "sample_job_interview",
        "subject": "Interview Invitation: Senior Python Engineer at TechCorp",
        "sender": "talent@techcorp-mock.com",
        "date": "2026-10-22T16:00:00Z",
        "account_type": "jobs",
        "body": """
Hi Chirag,

Thank you for your interest in the Senior Python Engineer role at TechCorp. We were very impressed by your background and would love to invite you for a 45-minute technical video screen.

Details:
- Date & Time: November 4, 2026 at 2:00 PM EST
- Interviewer: Jane Doe (Engineering Manager)
- Google Meet link: https://meet.google.com/abc-wxyz-mock
- Next steps: Please click the link above at the scheduled time.

Please let us know if you need to reschedule.

Best regards,
TechCorp Talent Team
""",
        "expected_classification": "job",
        "expected_company": "TechCorp",
        "expected_role": "Senior Python Engineer",
        "expected_event_type": "interview_invitation",
        "expected_meeting_link": "https://meet.google.com/abc-wxyz-mock",
    },
    {
        "id": "sample_job_application",
        "subject": "Application Received: Machine Learning Engineer",
        "sender": "no-reply@innovateai-mock.com",
        "date": "2026-10-23T08:30:00Z",
        "account_type": "jobs",
        "body": """
Thank you for applying to InnovateAI for the Machine Learning Engineer position!

We have successfully received your application. Our recruiting team will review your qualifications and reach out if there is a match for next steps.

Position: Machine Learning Engineer
Req ID: #AI-4091
""",
        "expected_classification": "job",
        "expected_company": "InnovateAI",
        "expected_role": "Machine Learning Engineer",
        "expected_event_type": "application_confirmation",
    },
    {
        "id": "sample_job_rejection",
        "subject": "Update on your application with CloudScale Systems",
        "sender": "careers@cloudscale-mock.com",
        "date": "2026-10-24T12:00:00Z",
        "account_type": "jobs",
        "body": """
Dear Chirag,

Thank you for taking the time to speak with our team regarding the Platform Engineer position at CloudScale Systems. While your background is impressive, we have decided to move forward with another candidate whose experience more closely matches our immediate needs.

We wish you all the best in your job search.

Sincerely,
CloudScale Systems Recruiting
""",
        "expected_classification": "job",
        "expected_company": "CloudScale Systems",
        "expected_role": "Platform Engineer",
        "expected_event_type": "rejection",
    },
    {
        "id": "sample_newsletter_promo",
        "subject": "Weekly Tech Digest & Autumn Gear Discounts",
        "sender": "news@dailytechdeals-mock.com",
        "date": "2026-10-25T07:00:00Z",
        "account_type": "jobs",
        "body": """
Check out top trending open source repositories this week! Also enjoy 20% off all mechanical keyboards using code AUTUMN20 at checkout.
Unsubscribe here to stop receiving weekly promotional digests.
""",
        "expected_classification": "ignored",
    },
]
