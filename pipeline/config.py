import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3305")),
    "user": os.getenv("DB_USERNAME", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "fishbowl_demo"),
    "charset": "utf8mb4",
}

OPTION_SKU_BASE = os.getenv("OPTION_SKU_BASE", "3D-9100")

DATA_DIR = ROOT / "data"
TRAINING_DIR = DATA_DIR / "training"
OUTPUT_DIR = DATA_DIR / "output"
SCHEMA_REPORT_DIR = DATA_DIR / "schema_report"
LOG_DIR = DATA_DIR / "logs"

for _dir in (TRAINING_DIR, OUTPUT_DIR, SCHEMA_REPORT_DIR, LOG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

MAIL_HOST = os.getenv("MAIL_HOST", "")
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_IMAP_PORT = int(os.getenv("MAIL_IMAP_PORT", "993"))
MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465"))
MAIL_FOLDER = os.getenv("MAIL_FOLDER", "INBOX")
MAIL_PROCESSED_FOLDER = os.getenv("MAIL_PROCESSED_FOLDER", "Processed")
ORDER_NOTIFY_TO = os.getenv("ORDER_NOTIFY_TO", MAIL_USERNAME)


def inbox_hold_until() -> datetime | None:
    raw = (os.getenv("MAIL_HOLD_INBOX_UNTIL") or "").strip()
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until


def inbox_hold_active() -> bool:
    until = inbox_hold_until()
    return until is not None and datetime.now(timezone.utc) < until