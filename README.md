# Personal Gmail Analysis Assistant

A controlled, privacy-focused assistant built with Python, LangChain, Groq, SQLite, and Streamlit to scan and analyze credit-card transaction alerts and job hunting correspondence across personal Gmail accounts.

---

## Architecture Principles

1. **Strictly Read-Only**: Strictly uses `https://www.googleapis.com/auth/gmail.readonly`. The application never writes, sends, modifies, archives, or deletes emails.
2. **Privacy First**: Raw email bodies are processed transiently in memory for classification and extraction; they are **never** stored in the SQLite database or logged.
3. **Controlled LangChain Extraction**: Uses deterministic LangChain chains with Groq (`openai/gpt-oss-120b` or configurable models) and Pydantic validation rather than unconstrained autonomous agents.
4. **Idempotent Ingestion**: Pre-filtering deduplication against SQLite `(account_id, message_id)` composite keys prevents duplicate LLM calls and duplicate insertions.
5. **Decoupled Architecture**: Scanning is executed via independent CLI/scheduler scripts, completely decoupled from the Streamlit UI dashboard.

---

## Directory Structure

```text
Email Agent/
├── app.py                     # Streamlit local dashboard (Transactions, Reports, Jobs)
├── credentials.json           # Google Cloud Desktop OAuth Client secret (Git-ignored)
├── .env                       # Local secrets & API keys (Git-ignored)
├── .env.example               # Environment variable template
├── .gitignore                 # Strict ignore rules for keys, tokens, and data
├── requirements.txt           # Project dependencies
├── README.md                  # Project documentation
├── scripts/
│   ├── auth_and_test_gmail.py # Interactive CLI to authorize Gmail accounts
│   ├── demo_sample_processor.py # Test processor on synthetic fixtures
│   └── run_scan.py            # CLI scanner to ingest and extract emails
├── src/
│   ├── __init__.py
│   ├── config.py              # Centralized configuration & secrets hygiene
│   ├── db.py                  # SQLite schema, deduplication, and CRUD layer
│   ├── extractor.py           # LangChain + Groq structured extraction pipeline
│   ├── gmail_client.py        # Read-only Gmail API client & MIME parser
│   ├── models.py              # Pydantic schemas (Transactions, Jobs, Enums)
│   └── scanner.py             # Orchestrates ingestion, deduplication & DB storage
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── sample_emails.py   # Synthetic test email fixtures
│   ├── test_config.py         # Config & secrets tests
│   ├── test_db.py             # SQLite schema, deduplication & CRUD tests
│   ├── test_extractor.py      # LangChain extraction tests
│   ├── test_gmail.py          # Read-only scope & MIME parser tests
│   ├── test_scanner.py        # End-to-end scanner & retry tests
│   └── test_ui.py             # Dashboard helper & formatting tests
├── tokens/                    # Per-account OAuth tokens (Git-ignored)
└── data/                      # Local SQLite database (Git-ignored)
```

---

## Setup & Usage Instructions

### 1. Environment & Dependencies

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in:
- `GROQ_API_KEY`: Your Groq API key from [Groq Console](https://console.groq.com).
- `GROQ_MODEL`: `openai/gpt-oss-120b` (default).

### 3. Connect Gmail Account

Place `credentials.json` (from Google Cloud Console) in the project root, then run:
```powershell
python scripts/auth_and_test_gmail.py --account account_1
```

### 4. Run an Email Ingestion Scan

```powershell
# Dry run (fetches candidate IDs without calling LLM or writing to DB)
python scripts/run_scan.py --account account_1 --limit 5 --dry-run

# Live ingestion scan
python scripts/run_scan.py --account account_1 --limit 10
```

### 5. Launch the Streamlit Dashboard

```powershell
streamlit run app.py
```
Views available in browser:
- **💳 Transactions**: Inspect transactions, edit spending hints/categories inline, and link directly to Gmail messages.
- **📊 Spending Reports**: Monthly totals, category charts, and top merchants.
- **💼 Jobs & Interviews**: Job applications, interview date/times, and clickable video meeting links.
- **⚙️ Accounts & Status**: Checkpoints and system status.

### 6. Run Complete Test Suite

```powershell
pytest
```
