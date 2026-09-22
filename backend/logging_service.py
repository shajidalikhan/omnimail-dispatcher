"""Logging and Usage Persistence Service for OmniMail Dispatcher.

Provides two tiers of persistence:
1. Developer System Logging: Structured rotating log file (logs/app_events.log).
2. User Dispatch History: Persistent CSV log (logs/dispatch_history.csv) and
   archived batch reports (reports/dispatch_report_{job_id}.xlsx).
"""
import os
import csv
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, List, Optional
import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEV_LOG_PATH = LOGS_DIR / "app_events.log"
HISTORY_CSV_PATH = LOGS_DIR / "dispatch_history.csv"

_history_lock = threading.Lock()

# ── DEVELOPER LOGGER SETUP ───────────────────────────────────────────────────
_dev_logger = logging.getLogger("omnimail")
_dev_logger.setLevel(logging.INFO)

if not _dev_logger.handlers:
    _formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    _file_handler = RotatingFileHandler(
        str(DEV_LOG_PATH),
        maxBytes=2 * 1024 * 1024,  # 2 MB
        backupCount=5,
        encoding="utf-8"
    )
    _file_handler.setFormatter(_formatter)
    _dev_logger.addHandler(_file_handler)


def log_info(message: str) -> None:
    """Log an informational event to developer log."""
    _dev_logger.info(message)


def log_warning(message: str) -> None:
    """Log a warning event to developer log."""
    _dev_logger.warning(message)


def log_error(message: str, exc_info: bool = False) -> None:
    """Log an error event to developer log."""
    _dev_logger.error(message, exc_info=exc_info)


def get_recent_developer_logs(max_lines: int = 300) -> List[str]:
    """Retrieve recent lines from developer log file."""
    if not DEV_LOG_PATH.exists():
        return []
    try:
        with open(DEV_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip() for line in lines[-max_lines:]]
    except Exception as e:
        log_error(f"Failed to read developer log: {e}")
        return [f"[Error reading log file: {e}]"]


# ── USER DISPATCH HISTORY SETUP ──────────────────────────────────────────────
HISTORY_COLUMNS = [
    "Job_ID",
    "Timestamp",
    "Activity_Type",
    "Dispatcher",
    "Sender_Email",
    "Total_Recipients",
    "Sent_Count",
    "Failed_Count",
    "Duration_Seconds",
    "Status",
    "Report_File",
]


def _init_history_csv() -> None:
    if not HISTORY_CSV_PATH.exists():
        with open(HISTORY_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(HISTORY_COLUMNS)


_init_history_csv()


def record_dispatch_event(
    job_id: str,
    activity_type: str,
    dispatcher: str,
    sender_email: str,
    total_recipients: int,
    sent_count: int,
    failed_count: int,
    duration_seconds: float,
    status: str,
    report_file: str = ""
) -> None:
    """Append a completed or interrupted dispatch activity to the persistent history CSV."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        job_id or f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}",
        now_str,
        activity_type,
        dispatcher,
        sender_email,
        total_recipients,
        sent_count,
        failed_count,
        round(duration_seconds, 1),
        status,
        report_file
    ]
    with _history_lock:
        _init_history_csv()
        with open(HISTORY_CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    log_info(
        f"[HISTORY RECORDED] {activity_type} ({job_id}) | Provider: {dispatcher} | "
        f"Sent: {sent_count}/{total_recipients} | Status: {status}"
    )


def get_dispatch_history() -> List[Dict[str, Any]]:
    """Retrieve all logged dispatch events, newest first."""
    if not HISTORY_CSV_PATH.exists():
        return []
    records = []
    with _history_lock:
        try:
            with open(HISTORY_CSV_PATH, "r", newline="", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    records.append(dict(row))
        except Exception as e:
            log_error(f"Failed to read dispatch history: {e}")
            return []
    records.reverse()
    return records


def get_history_summary_stats() -> Dict[str, Any]:
    """Calculate high-level summary metrics from historical dispatches."""
    history = get_dispatch_history()
    total_batches = 0
    total_emails_sent = 0
    total_emails_failed = 0

    for item in history:
        if item.get("Activity_Type") == "Batch Dispatch":
            total_batches += 1
        try:
            total_emails_sent += int(item.get("Sent_Count", 0))
            total_emails_failed += int(item.get("Failed_Count", 0))
        except (ValueError, TypeError):
            pass

    total_attempted = total_emails_sent + total_emails_failed
    success_rate = round((total_emails_sent / total_attempted * 100), 1) if total_attempted > 0 else 100.0

    return {
        "total_records": len(history),
        "total_batches": total_batches,
        "total_emails_sent": total_emails_sent,
        "total_emails_failed": total_emails_failed,
        "success_rate_percent": success_rate,
    }


def archive_dispatch_report(job_id: str, records: List[Dict[str, Any]]) -> str:
    """Save an archived report to reports/ for long-term user download."""
    if not records:
        return ""
    from backend.data_ingestion import export_status_report

    filename = f"dispatch_report_{job_id}.xlsx"
    file_path = REPORTS_DIR / filename
    try:
        data_bytes = export_status_report(records, format="xlsx")
        file_path.write_bytes(data_bytes)
        log_info(f"Archived verification report saved to: {file_path.name}")
        return filename
    except Exception as e:
        log_error(f"Failed to archive Excel report for {job_id}: {e}")
        # Fallback to CSV
        try:
            csv_filename = f"dispatch_report_{job_id}.csv"
            csv_path = REPORTS_DIR / csv_filename
            csv_bytes = export_status_report(records, format="csv")
            csv_path.write_bytes(csv_bytes)
            return csv_filename
        except Exception as e2:
            log_error(f"Failed to archive CSV report fallback: {e2}")
            return ""
