"""Interactive tool to authorize a Gmail account and verify read-only access.

Usage:
  python scripts/auth_and_test_gmail.py [--account account_1]
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.gmail_client import GMAIL_READONLY_SCOPE, GmailClient


def main():
    parser = argparse.ArgumentParser(description="Authorize Gmail account with read-only scope.")
    parser.add_argument(
        "--account",
        default="account_1",
        help="Account identifier to authorize (e.g. account_1, account_2, account_3)",
    )
    args = parser.parse_args()

    settings = get_settings()

    print("=" * 70)
    print(f"Gmail Read-Only Authorization Tool - Target: [{args.account}]")
    print("=" * 70)
    print(f"Requested Scope: {GMAIL_READONLY_SCOPE[0]}")
    print("NOTE: This scope grants READ-ONLY access. The application cannot")
    print("send, delete, modify, or label any emails.")
    print("=" * 70)

    if not settings.google_credentials_file.exists():
        print(f"\n[X] Error: Credentials file '{settings.google_credentials_file}' not found.")
        print("\nPlease follow these steps to download credentials.json:")
        print("  1. Go to Google Cloud Console (https://console.cloud.google.com)")
        print("  2. Create or select a project and enable 'Gmail API'")
        print("  3. Go to 'OAuth consent screen' -> User Type: External -> Add Test Users")
        print("  4. Go to 'Credentials' -> 'Create Credentials' -> 'OAuth client ID' -> 'Desktop app'")
        print("  5. Download the JSON and save it in the project root as 'credentials.json'")
        print(f"  Expected path: {settings.google_credentials_file.resolve()}\n")
        sys.exit(1)

    client = GmailClient(account_id=args.account, settings=settings)

    print(f"\nInitiating OAuth flow for '{args.account}'...")
    print("A browser window will open shortly to log into your Google Account.")
    print("After approving access, return to this terminal.\n")

    try:
        # Prompt interactive authorization
        client.get_credentials(interactive=True)
        print(f"[OK] Authorization successful! Token saved to: {client.token_path}\n")

        print("Testing read-only connectivity...")
        profile = client.test_connection()
        print(f"  Connected Email : {profile['email_address']}")
        print(f"  Total Messages  : {profile['messages_total']}")
        print(f"  History ID      : {profile['history_id']}\n")

        print("Performing test retrieval of up to 3 recent message headers...")
        listing = client.list_messages(max_results=3)
        messages = listing.get("messages", [])

        if not messages:
            print("  No messages found in inbox.")
        else:
            for idx, m in enumerate(messages, 1):
                msg_detail = client.get_message_detail(m["id"])
                print(f"  [{idx}] Subject : {msg_detail['subject']}")
                print(f"      From    : {msg_detail['sender']}")
                print(f"      Date    : {msg_detail['date']}")
                print(f"      ID      : {msg_detail['message_id']}")

        print("\n[OK] Gmail Read-Only connection verified successfully!")

    except Exception as e:
        print(f"\n[X] Authorization or connection test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
