"""CLI script to run an email ingestion scan for an account.

Usage:
  python scripts/run_scan.py [--account account_1] [--limit 10] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.scanner import AccountScanner


def main():
    parser = argparse.ArgumentParser(description="Run an ingestion scan for a Gmail account.")
    parser.add_argument(
        "--account",
        default="account_1",
        help="Account identifier to scan (default: account_1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum candidate messages to evaluate (default: 10)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Custom search query override (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate scan: fetch candidates without calling Groq or modifying database",
    )
    args = parser.parse_args()

    settings = get_settings()

    print("=" * 70)
    print(f"Gmail Ingestion Scan: [{args.account}]")
    print("=" * 70)

    # Determine account type from settings
    acct_type = "transactions" if "1" in args.account else "jobs"
    if args.account == "account_1":
        acct_type = settings.account_1_type
    elif args.account == "account_2":
        acct_type = settings.account_2_type
    elif args.account == "account_3":
        acct_type = settings.account_3_type

    print(f"Account Type    : {acct_type}")
    print(f"Message Limit   : {args.limit}")
    print(f"Dry Run Mode    : {args.dry_run}")
    print(f"Groq Model      : {settings.groq_model}")

    try:
        scanner = AccountScanner(
            account_id=args.account,
            account_type=acct_type,
            settings=settings,
        )

        effective_query = scanner.build_query(args.query)
        print(f"Gmail Filter    : {effective_query}\n")
        print("Starting scan...")

        stats = scanner.scan(query=args.query, max_messages=args.limit, dry_run=args.dry_run)

        print("\nScan Results:")
        print(f"  Candidates Found          : {stats['candidates_found']}")
        print(f"  Already Processed (Skipped): {stats['already_processed_skipped']}")
        print(f"  Newly Processed           : {stats['newly_processed']}")
        print(f"  Transactions Created      : {stats['transactions_created']}")
        print(f"  Job Events Created        : {stats['job_events_created']}")
        print(f"  Ignored Messages          : {stats['ignored_count']}")
        print(f"  Errors Encountered        : {stats['errors']}")
        print("\n[OK] Scan completed successfully.")

    except Exception as e:
        print(f"\n[X] Scan failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
