"""Configuration management for Personal Gmail Analysis Assistant."""

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccountConfig(BaseSettings):
    """Configuration for an individual Gmail account."""
    email: str
    account_type: str  # 'transactions' or 'jobs'


class Settings(BaseSettings):
    """Central application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Groq API Configuration
    groq_api_key: Optional[str] = Field(
        default=None,
        description="Groq API key for LLM calls (never hardcode in code or git)."
    )
    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq LLM model name; configurable to switch when limits or availability change."
    )

    # Storage & Secret Locations
    database_path: Path = Field(
        default=Path("data/email_agent.db"),
        description="Path to the local SQLite database."
    )
    google_credentials_file: Path = Field(
        default=Path("credentials.json"),
        description="Path to the Google Cloud OAuth client secret file."
    )
    tokens_dir: Path = Field(
        default=Path("tokens"),
        description="Directory where per-account OAuth tokens are stored."
    )

    # Gmail Pre-Filter Query Templates
    gmail_transaction_query: str = Field(
        default='(receipt OR transaction OR alert OR charge OR debit OR credit OR payment OR order OR statement)',
        description="Broad keyword pre-filter for credit card transaction alerts."
    )
    gmail_job_query: str = Field(
        default='(interview OR application OR applied OR offer OR assessment OR recruiter OR "status update" OR "next steps" OR rejection)',
        description="Broad keyword pre-filter for job-related communications."
    )

    # Scanning Resiliency
    scan_lookback_overlap_hours: int = Field(
        default=2,
        ge=0,
        description="Number of overlap hours to include when resuming from last checkpoint."
    )

    # Account Specifics
    account_1_email: Optional[str] = Field(default="jainchirag.cj555@gmail.com")
    account_1_type: str = Field(default="jobs")

    account_2_email: Optional[str] = Field(default="chirag.cj555@gmail.com")
    account_2_type: str = Field(default="transactions")

    account_3_email: Optional[str] = Field(default="chirag.work555@gmail.com")
    account_3_type: str = Field(default="jobs")

    def ensure_directories(self) -> None:
        """Create required directories (e.g., data/ and tokens/) safely."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

    def get_configured_accounts(self) -> List[Dict[str, str]]:
        """Return list of configured accounts with their assigned types."""
        return [
            {"account_id": "account_1", "email": self.account_1_email or "account_1@local", "type": self.account_1_type},
            {"account_id": "account_2", "email": self.account_2_email or "account_2@local", "type": self.account_2_type},
            {"account_id": "account_3", "email": self.account_3_email or "account_3@local", "type": self.account_3_type},
        ]

    def sanitized_summary(self) -> Dict[str, str]:
        """Return safe, non-sensitive summary of settings for operational logging."""
        has_key = bool(self.groq_api_key and len(self.groq_api_key.strip()) > 0)
        return {
            "groq_model": self.groq_model,
            "groq_api_key_configured": "Yes (Masked)" if has_key else "No (Not set)",
            "database_path": str(self.database_path),
            "tokens_dir": str(self.tokens_dir),
            "credentials_file": str(self.google_credentials_file),
            "scan_overlap_hours": str(self.scan_lookback_overlap_hours),
            "configured_accounts_count": str(len(self.get_configured_accounts()))
        }


def get_settings() -> Settings:
    """Factory function to instantiate and return settings."""
    settings = Settings()
    settings.ensure_directories()
    return settings
