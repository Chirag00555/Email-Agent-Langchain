# Personal Gmail Analysis Assistant

A controlled, privacy-focused assistant built with Python, LangChain, Groq, and Streamlit to scan and analyze credit-card transaction alerts and job hunting correspondence across three personal Gmail accounts.

---

## Architecture Principles

1. **Read-Only**: Strictly uses `https://www.googleapis.com/auth/gmail.readonly`. The application never writes, sends, modifies, or deletes emails.
2. **Privacy First**: Raw email bodies are processed transiently for classification and extraction; they are **never** stored permanently in the SQLite database or logged.
3. **Controlled Workflow**: Uses deterministic LangChain chains with Pydantic validation rather than unconstrained autonomous agents.
4. **Idempotent Ingestion**: Per-account scan checkpoints and unique database constraints prevent duplicate processing.

---

## Directory Structure

```text
Email Agent/
├── .env.example          # Environment variable template
├── .gitignore             # Strict ignore rules for keys, tokens, and data
├── requirements.txt       # Project dependencies
├── README.md              # Project documentation
├── src/
│   ├── __init__.py
│   └── config.py          # Centralized configuration & secrets hygiene
└── tests/
    ├── __init__.py
    └── test_config.py     # Unit tests for configuration
```

---

## Setup Instructions

### 1. Create and Activate Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Edit `.env` to provide:
- `GROQ_API_KEY`: Your Groq API key from [Groq Console](https://console.groq.com).
- `GROQ_MODEL`: Default is `openai/gpt-oss-120b` (can be switched to `llama-3.3-70b-versatile` or `llama-3.1-8b-instant`).
- `ACCOUNT_*`: Configured Gmail addresses for your transaction and job accounts.

### 4. Run Phase 1 Verification Tests

```powershell
pytest
```
