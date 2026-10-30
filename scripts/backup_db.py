"""Database backup and restoration utility using SQLite online backup API.

Usage:
  python scripts/backup_db.py --backup
  python scripts/backup_db.py --list
  python scripts/backup_db.py --restore data/backups/email_agent_backup_20261030_120000.db
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings


def create_backup(db_path: Path, backup_dir: Path) -> Path:
    """Create a consistent point-in-time online backup of SQLite database."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"email_agent_backup_{timestamp}.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Source database '{db_path}' does not exist.")

    # Use SQLite Online Backup API for lock-safe consistent snapshot
    source_conn = sqlite3.connect(str(db_path))
    dest_conn = sqlite3.connect(str(backup_file))

    try:
        source_conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()
        source_conn.close()

    return backup_file


def list_backups(backup_dir: Path):
    """List all available local database backups."""
    if not backup_dir.exists():
        print("No backups directory found.")
        return []

    backups = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("No backups found in", backup_dir)
        return []

    print(f"\nFound {len(backups)} backup(s) in {backup_dir}:")
    for idx, b in enumerate(backups, 1):
        size_kb = b.stat().st_size / 1024
        mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [{idx}] {b.name} ({size_kb:.1f} KB) - Created: {mtime}")
    return backups


def restore_backup(backup_file: Path, db_path: Path) -> None:
    """Restore database from a chosen backup file."""
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file '{backup_file}' does not exist.")

    # Create safety backup of existing DB before restoring
    if db_path.exists():
        safety_path = db_path.parent / f"{db_path.name}.pre_restore_safety"
        shutil.copy2(db_path, safety_path)
        print(f"Created pre-restore safety copy at: {safety_path}")

    source_conn = sqlite3.connect(str(backup_file))
    dest_conn = sqlite3.connect(str(db_path))

    try:
        source_conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()
        source_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backup and restore Personal Gmail Analysis Assistant SQLite database.")
    parser.add_argument("--backup", action="store_true", help="Create a new timestamped database backup")
    parser.add_argument("--list", action="store_true", help="List all available backups")
    parser.add_argument("--restore", type=str, help="Path to backup file to restore from")
    args = parser.parse_args()

    settings = get_settings()
    db_path = settings.database_path
    backup_dir = db_path.parent / "backups"

    print("=" * 70)
    print("Database Backup & Disaster Recovery Utility")
    print("=" * 70)
    print(f"Active Database : {db_path}")
    print(f"Backup Location : {backup_dir}\n")

    if args.backup or (not args.list and not args.restore):
        print("Creating online backup...")
        try:
            backup_path = create_backup(db_path, backup_dir)
            size_kb = backup_path.stat().st_size / 1024
            print(f"[OK] Backup created successfully: {backup_path} ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"[X] Backup failed: {e}")
            sys.exit(1)

    if args.list:
        list_backups(backup_dir)

    if args.restore:
        target_backup = Path(args.restore)
        print(f"Restoring database from '{target_backup}'...")
        try:
            restore_backup(target_backup, db_path)
            print("[OK] Database restored successfully!")
        except Exception as e:
            print(f"[X] Restore failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
