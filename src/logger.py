"""Sanitized operational logging configuration for background scanning.

STRICT PRIVACY POLICY:
- Never log email bodies.
- Never log OAuth tokens or API keys.
- Only log timestamps, operational events, candidate counts, and error categories.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.config import Settings, get_settings


def setup_logger(
    name: str = "email_agent",
    log_dir: Optional[Path] = None,
    log_level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a sanitized, rotating file logger."""
    settings = get_settings()
    target_dir = log_dir or (settings.database_path.parent.parent / "logs")
    target_dir.mkdir(parents=True, exist_ok=True)

    log_file = target_dir / "scanner.log"

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if re-initialized
    if logger.handlers:
        return logger

    # Rotating file handler: 5MB per file, keeping up to 3 backups
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)

    # Console handler for interactive runs
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
