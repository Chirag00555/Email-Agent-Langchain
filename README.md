# Personal Gmail Analysis Assistant

A private, controlled personal email intelligence system built with **Python**, **LangChain**, **Groq**, **SQLite**, and **Streamlit** to scan three personal Gmail accounts:
- **Account 2** (`chirag.cj555@gmail.com`): Dedicated to credit-card transaction alerts and purchase notices.
- **Account 1** (`jainchirag.cj555@gmail.com`) & **Account 3** (`chirag.work555@gmail.com`): Dedicated to job hunting, application confirmations, and interview scheduling.

---

## Core Architecture & Privacy Principles

1. **Strictly Read-Only**: Utilizes `https://www.googleapis.com/auth/gmail.readonly`. The application has zero permissions to send, modify, label, archive, or delete any email.
2. **Zero Body Storage**: Raw email bodies exist transiently in memory during extraction and are discarded—**never** stored in SQLite or written to logs.
3. **Controlled LangChain Pipeline**: Deterministic Prompt Template $\rightarrow$ Groq LLM (`openai/gpt-oss-120b` or configurable model) $\rightarrow$ Pydantic structured output. No autonomous or unconstrained agent actions.
4. **Idempotent Ingestion & Deduplication**: SQLite composite primary key `(account_id, message_id)` guarantees that candidate emails are checked before invoking Groq. Overlapping scans produce zero duplicate API calls and zero duplicate rows.
5. **Resilient Incremental Checkpointing**: Maintains a separate checkpoint timestamp for each account with a 2-hour safety overlap. If the computer is powered off or sleeping during the scheduled run, the next scan automatically catches up from the last successful checkpoint.
6. **Decoupled Architecture**: Ingestion runs headlessly via Windows Task Scheduler; the Streamlit UI runs independently for viewing, reporting, and category curation.

---

## Directory Layout

```text
Email Agent/
├── app.py                            # Streamlit interactive local dashboard
├── credentials.json                  # Google Cloud Desktop OAuth Client secret (Git-ignored)
├── .env                              # Local secrets & API keys (Git-ignored)
├── .env.example                      # Environment variable template
├── .gitignore                        # Git exclusion rules for keys, tokens, and data
├── requirements.txt                  # Pinned dependencies
├── README.md                         # Project documentation
├── scripts/
│   ├── auth_and_test_gmail.py        # Interactive CLI to authorize Gmail accounts
│   ├── backup_db.py                  # Database online backup & disaster recovery
│   ├── demo_sample_processor.py      # Synthetic test email processor
│   ├── remove_windows_scheduler.ps1  # Script to unregister scheduled scan task
│   ├── revoke_access.py              # Server-side & local OAuth token revocation
│   ├── run_scan.py                   # On-demand scanner CLI (supports --all & --dry-run)
│   ├── scheduled_scan.py             # Headless runner for Windows Task Scheduler
│   └── setup_windows_scheduler.ps1   # PowerShell automation for nightly 10:00 PM scan
├── src/
│   ├── __init__.py
│   ├── config.py                     # Centralized Pydantic settings & secrets hygiene
│   ├── db.py                         # SQLite schema, atomic persistence, & CRUD layer
│   ├── extractor.py                  # LangChain + Groq structured extraction pipeline
│   ├── gmail_client.py               # Read-only Gmail API client & MIME parser
│   ├── logger.py                     # Sanitized operational logging to logs/scanner.log
│   ├── models.py                     # Pydantic schemas (Transactions, Jobs, Enums)
│   └── scanner.py                    # Orchestrates ingestion, overlap & DB storage
├── tests/
│   ├── fixtures/sample_emails.py     # Synthetic test email fixtures
│   ├── test_backup_and_revoke.py     # Backup & revocation tests
│   ├── test_checkpoint_recovery.py   # Overlap, catchup & retry tests
│   ├── test_config.py                # Configuration & secret masking tests
│   ├── test_db.py                    # SQLite schema, deduplication & CRUD tests
│   ├── test_extractor.py             # LangChain extraction & validation tests
│   ├── test_gmail.py                 # Read-only scope & MIME parser tests
│   ├── test_logger.py                # Sanitized operational logging tests
│   ├── test_multi_account.py         # Multi-account separation & isolation tests
│   ├── test_scanner.py               # Integration & retry tests
│   └── test_ui.py                    # Streamlit formatting & category tests
├── tokens/                           # Per-account OAuth tokens (Git-ignored)
├── logs/                             # Rotating operational logs (Git-ignored)
└── data/                             # Local SQLite database (Git-ignored)
```

---

## Setup & Operation Runbook

### 1. Environment & Setup

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials

1. Copy `.env.example` to `.env` and set your `GROQ_API_KEY`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Download your Google Cloud Desktop OAuth Client JSON as `credentials.json` in the root folder.
3. Authorize each account:
   ```powershell
   python scripts\auth_and_test_gmail.py --account account_1
   python scripts\auth_and_test_gmail.py --account account_2
   python scripts\auth_and_test_gmail.py --account account_3
   ```

---

### 3. Running Scans

```powershell
# Dry run across all 3 accounts (fetches candidates without calling LLM or writing to DB)
python scripts\run_scan.py --all --limit 5 --dry-run

# Live scan on transaction account (account_2)
python scripts\run_scan.py --account account_2 --limit 10

# Live scan across all 3 accounts
python scripts\run_scan.py --all --limit 10
```

---

### 4. Interactive Streamlit Dashboard

Launch the local browser interface:
```powershell
streamlit run app.py
```
- **💳 Transactions View**: Inspect extracted merchant, amount, card last-4; edit spending hints/categories inline with instant DB updates; link directly to Gmail messages.
- **📊 Spending Reports View**: Real-time monthly spend, category distribution charts, and top merchants.
- **💼 Jobs & Interviews View**: Track applications, upcoming interview dates/times with timezones, and one-click video meeting links (Zoom / Google Meet).
- **⚙️ Accounts & Status**: Review connected accounts, last scan checkpoints, and model settings.

---

### 5. Nightly 10:00 PM Windows Task Scheduler

Register the automated nightly scan:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows_scheduler.ps1
```
- Runs every night at **10:00 PM local time**.
- **Missed-Run Catch-Up**: Configured with `StartWhenAvailable=$true` (if your laptop is asleep or powered off at 10:00 PM, Windows automatically runs the scan as soon as the machine boots or wakes up).
- **Unregister anytime**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\remove_windows_scheduler.ps1
  ```

---

### 6. Database Backup & Disaster Recovery

```powershell
# Create an online point-in-time backup (safe while Streamlit is open)
python scripts\backup_db.py --backup

# List existing backups
python scripts\backup_db.py --list

# Restore from a backup file
python scripts\backup_db.py --restore data\backups\email_agent_backup_YYYYMMDD_HHMMSS.db
```

---

### 7. Revoking Access & Decommissioning

To revoke Google OAuth access both server-side and delete local tokens:
```powershell
# Revoke a single account
python scripts\revoke_access.py --account account_1

# Revoke all accounts
python scripts\revoke_access.py --all
```
You can also audit or revoke access at any time from your Google Account settings:
👉 [Google Account Third-Party Permissions](https://myaccount.google.com/permissions)

---

### 8. Running the Complete Automated Test Suite

```powershell
pytest
```
*46 comprehensive unit and integration tests covering configuration, database, extraction, OAuth, multi-account isolation, failure recovery, logging, and UI.*
