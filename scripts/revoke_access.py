"""Gmail OAuth Access Revocation and Local Token Decommissioning Utility.

Usage:
  python scripts/revoke_access.py --account account_1
  python scripts/revoke_access.py --all
"""

import argparse
import json
import sys
from pathlib import Path
import requests

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings


def revoke_token_serverside(token: str) -> bool:
    """Send HTTP POST request to Google OAuth token revocation endpoint."""
    revoke_url = "https://oauth2.googleapis.com/revoke"
    try:
        response = requests.post(
            revoke_url,
            params={"token": token},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        return response.status_code == 200
    except Exception as e:
        print(f"  Warning: Server-side revocation call failed: {e}")
        return False


def revoke_account(account_id: str, tokens_dir: Path) -> None:
    """Revoke credentials for a specific account and delete local token file."""
    token_file = tokens_dir / f"{account_id}.json"

    print(f"\nRevoking access for [{account_id}]...")

    if not token_file.exists():
        print(f"  No token file found at {token_file}. Account is not currently authorized.")
        return

    # Read token for remote revocation
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            refresh_token = data.get("refresh_token") or data.get("token")

        if refresh_token:
            print("  Contacting Google OAuth servers to revoke grant...")
            success = revoke_token_serverside(refresh_token)
            if success:
                print("  [OK] Google OAuth server revoked the authorization grant.")
            else:
                print("  [Notice] Server revocation returned non-200 (token may already be expired or invalid).")

    except Exception as e:
        print(f"  Warning reading token data: {e}")

    # Delete local file
    try:
        token_file.unlink()
        print(f"  [OK] Local token file deleted: {token_file}")
    except Exception as e:
        print(f"  Error deleting local token file: {e}")


def main():
    parser = argparse.ArgumentParser(description="Revoke Gmail OAuth access and remove local tokens.")
    parser.add_argument("--account", type=str, help="Specific account to revoke (e.g. account_1, account_2, account_3)")
    parser.add_argument("--all", action="store_true", help="Revoke access for all accounts")
    args = parser.parse_args()

    settings = get_settings()
    tokens_dir = settings.tokens_dir

    print("=" * 70)
    print("Gmail Access Revocation & Decommissioning Utility")
    print("=" * 70)

    if not args.account and not args.all:
        print("Please specify an account to revoke (--account <id>) or --all.")
        print("Available token files:")
        for t in tokens_dir.glob("*.json"):
            print(f"  - {t.stem}")
        sys.exit(0)

    if args.all:
        for t in tokens_dir.glob("*.json"):
            revoke_account(t.stem, tokens_dir)
    elif args.account:
        revoke_account(args.account, tokens_dir)

    print("\n" + "=" * 70)
    print("Security Reminder:")
    print("You can also view or revoke third-party app permissions directly from Google:")
    print("👉 https://myaccount.google.com/permissions")
    print("=" * 70)


if __name__ == "__main__":
    main()
