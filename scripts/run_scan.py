"""CLI script to run email ingestion scans across one or all configured Gmail accounts.

Usage:
  python scripts/run_scan.py --all [--limit 10] [--dry-run]
  python scripts/run_scan.py --account account_2 [--limit 10] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.scanner import AccountScanner, scan_all_accounts


def print_stats(stats: dict):
    print(f"\nScan Results for [{stats['account_id']}]:")
    print(f"  Filter Query Used         : {stats['query_used']}")
    print(f"  Candidates Found          : {stats['candidates_found']}")
    print(f"  Already Processed (Skipped): {stats['already_processed_skipped']}")
    print(f"  Newly Processed           : {stats['newly_processed']}")
    print(f"  Transactions Created      : {stats['transactions_created']}")
    print(f"  Job Events Created        : {stats['job_events_created']}")
    print(f"  Ignored Messages          : {stats['ignored_count']}")
    print(f"  Errors Encountered        : {stats['errors']}")


def main():
    parser = argparse.ArgumentParser(description="Run an ingestion scan for one or all Gmail accounts.")
    parser.add_argument(
        "--account",
        default="account_2",
        help="Account identifier to scan (e.g. account_1, account_2, account_3)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan all configured Gmail accounts sequentially",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum candidate messages per account (default: 10)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Custom search query override for single account scan (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate scan: fetch candidates without calling Groq or modifying database",
    )
    args = parser.parse_args()

    settings = get_settings()

    print("=" * 70)
    print("Gmail Analysis Assistant - Ingestion Scanner")
    print("=" * 70)
    print(f"Groq Model      : {settings.groq_model}")
    print(f"Dry Run Mode    : {args.dry_run}")
    print(f"Limit / Account : {args.limit}")

    if args.all:
        print("\nMode: Scanning ALL configured accounts...")
        results = scan_all_accounts(
            settings=settings,
            max_messages_per_account=args.limit,
            dry_run=args.dry_run,
        )
        print("\n" + "=" * 70)
        print("Consolidated Multi-Account Scan Summary")
        print("=" * 70)
        for stats in results:
            print_stats(stats)
        print("\n[OK] All account scans finished.")
        return

    # Single account scan
    print(f"\nMode: Scanning single account [{args.account}]...")
    try:
        scanner = AccountScanner(
            account_id=args.account,
            settings=settings,
        )
        print(f"Account Type    : {scanner.account_type}")
        print(f"Account Email   : {scanner.email_address}")
        effective_query = scanner.build_query(args.query)
        print(f"Effective Filter: {effective_query}\n")

        stats = scanner.scan(query=args.query, max_messages=args.limit, dry_run=args.dry_run)
        print_stats(stats)
        print("\n[OK] Scan completed successfully.")

    except Exception as e:
        print(f"\n[X] Scan failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
