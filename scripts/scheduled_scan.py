"""Headless nightly runner executed by Windows Task Scheduler (10:00 PM).

Safely executes multi-account scan and logs operational metrics to logs/scanner.log.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.logger import setup_logger
from src.scanner import scan_all_accounts


def main():
    logger = setup_logger()
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("Starting Nightly Scheduled Gmail Analysis Scan")
    logger.info(f"Groq Model in use: {settings.groq_model}")
    logger.info(f"Configured Accounts: {len(settings.get_configured_accounts())}")
    logger.info("=" * 60)

    try:
        results = scan_all_accounts(settings=settings, max_messages_per_account=25, dry_run=False)

        total_new = sum(r.get("newly_processed", 0) for r in results)
        total_tx = sum(r.get("transactions_created", 0) for r in results)
        total_jobs = sum(r.get("job_events_created", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)

        for r in results:
            logger.info(
                f"Account [{r['account_id']}]: Candidates={r['candidates_found']}, "
                f"SkippedDuplicates={r['already_processed_skipped']}, "
                f"Processed={r['newly_processed']}, "
                f"TransactionsCreated={r['transactions_created']}, "
                f"JobEventsCreated={r['job_events_created']}, "
                f"Ignored={r['ignored_count']}, "
                f"Errors={r['errors']}"
            )

        logger.info(
            f"Nightly Scan Completed Successfully: "
            f"NewMessages={total_new}, Transactions={total_tx}, Jobs={total_jobs}, Errors={total_errors}"
        )

        if total_errors > 0:
            logger.warning(f"Scan finished with {total_errors} message processing error(s).")

        sys.exit(0)

    except Exception as e:
        logger.error(f"Catastrophic failure during scheduled scan: {e}", exc_info=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
