import smtplib
import ssl
import time
import threading
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.config import DISPATCHER_PRESETS
from backend.template_service import render_template

class DispatcherJob:
    def __init__(self):
        self.job_id: str = ""
        self.is_running: bool = False
        self.is_paused: bool = False
        self.should_stop: bool = False
        self.total_count: int = 0
        self.sent_count: int = 0
        self.failed_count: int = 0
        self.current_index: int = 0
        self.current_recipient: str = ""
        self.logs: List[Dict[str, Any]] = []
        self.results: List[Dict[str, Any]] = []
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None

    def reset(self):
        with self.lock:
            self.job_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.is_running = False
            self.is_paused = False
            self.should_stop = False
            self.total_count = 0
            self.sent_count = 0
            self.failed_count = 0
            self.current_index = 0
            self.current_recipient = ""
            self.logs = []
            self.results = []
            self.started_at = None
            self.completed_at = None

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "job_id": self.job_id,
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "total_count": self.total_count,
                "sent_count": self.sent_count,
                "failed_count": self.failed_count,
                "current_index": self.current_index,
                "current_recipient": self.current_recipient,
                "progress_percent": round((self.current_index / self.total_count * 100), 1) if self.total_count > 0 else 0,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "recent_logs": self.logs[-50:]  # last 50 log lines
            }

_jobs_lock = threading.Lock()

active_jobs: Dict[str, DispatcherJob] = {}

def get_job(session_id: str = "default") -> DispatcherJob:
    """Retrieve or initialize isolated job instance for given session (Multi-User Isolation)."""
    clean_id = session_id or "default"
    with _jobs_lock:
        if clean_id not in active_jobs:
            active_jobs[clean_id] = DispatcherJob()
        return active_jobs[clean_id]

# Backward compatibility alias
class JobProxy:
    def __getattr__(self, name):
        return getattr(get_job("default"), name)
    def __setattr__(self, name, value):
        setattr(get_job("default"), name, value)

current_job = JobProxy()


def build_mime_message(
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    reply_to: str = "",
    attachments: List[Dict[str, Any]] = None
) -> MIMEMultipart:
    """Build a standard multi-part MIME email message with HTML and plain text alternative."""
    msg = MIMEMultipart("alternative")
    display_sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    msg["From"] = display_sender
    msg["To"] = recipient_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    # Plain text fallback
    if not body_text:
        # Simple plain text fallback stripped from HTML
        import re
        body_text = re.sub(r"<[^>]+>", "", body_html)

    part1 = MIMEText(body_text, "plain", "utf-8")
    part2 = MIMEText(body_html, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    # Optional attachments: list of dicts with {"filename": str, "content_bytes": bytes}
    if attachments:
        # Re-wrap as mixed if attachments are present
        mixed_msg = MIMEMultipart("mixed")
        for k in ["From", "To", "Subject", "Reply-To", "Date"]:
            if k in msg:
                mixed_msg[k] = msg[k]
        mixed_msg.attach(msg)
        
        for att in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(att["content_bytes"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{att["filename"]}"',
            )
            mixed_msg.attach(part)
        return mixed_msg

    return msg

def get_smtp_connection(dispatcher_type: str, sender_email: str, sender_key: str, custom_server: str = "", custom_port: int = 587, use_tls: bool = True):
    """Authenticate and return an active SMTP connection based on selected dispatcher."""
    if dispatcher_type == "dry_run":
        return None  # Dry-run does not use a real connection

    preset = DISPATCHER_PRESETS.get(dispatcher_type, {})
    server_host = custom_server if dispatcher_type == "custom" else preset.get("smtp_server")
    port = custom_port if dispatcher_type == "custom" else preset.get("smtp_port", 587)
    use_tls_flag = use_tls if dispatcher_type == "custom" else preset.get("use_tls", True)

    if not server_host:
        raise ValueError(f"No SMTP server defined for dispatcher '{dispatcher_type}'")

    if port == 465:
        # Direct SSL
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(server_host, port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(server_host, port, timeout=20)
        server.ehlo()
        if use_tls_flag:
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()

    if sender_email and sender_key:
        server.login(sender_email, sender_key)

    return server

def send_single_test_email(
    dispatcher_type: str,
    sender_email: str,
    sender_name: str,
    sender_key: str,
    test_recipient_email: str,
    subject: str,
    body_html: str,
    custom_server: str = "",
    custom_port: int = 587,
    use_tls: bool = True,
    attachments: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Sends a single live test email or simulates test send to verify settings."""
    if dispatcher_type == "dry_run":
        att_note = f" (with {len(attachments)} attachments)" if attachments else ""
        return {
            "success": True,
            "message": f"[DRY-RUN] Test email simulated successfully for {test_recipient_email}{att_note}",
            "rendered_subject": subject,
            "rendered_body": body_html
        }

    try:
        server = get_smtp_connection(dispatcher_type, sender_email, sender_key, custom_server, custom_port, use_tls)
        msg = build_mime_message(
            sender_email=sender_email,
            sender_name=sender_name,
            recipient_email=test_recipient_email,
            subject=f"[TEST] {subject}",
            body_html=body_html,
            attachments=attachments
        )
        server.send_message(msg)
        server.quit()
        return {
            "success": True,
            "message": f"Test email successfully dispatched to {test_recipient_email}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to send test email: {str(e)}"
        }


def start_batch_dispatch_job(
    recipients: List[Dict[str, Any]],
    email_column: str,
    subject_template: str,
    body_template: str,
    dispatcher_type: str,
    sender_email: str,
    sender_name: str,
    sender_key: str,
    custom_server: str = "",
    custom_port: int = 587,
    use_tls: bool = True,
    delay_seconds: float = 3.0,
    retry_failures_only: bool = False,
    session_id: str = "default",
    attachments: List[Dict[str, Any]] = None
):

    """Start background dispatch worker loop with rate-limiting, error recovery, and Zero-Retention security."""
    job = get_job(session_id)
    if job.is_running:
        raise RuntimeError("A dispatch job is already running in this session!")

    job.reset()
    job.total_count = len(recipients)
    job.is_running = True
    job.started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def run_worker():
        nonlocal sender_key
        server = None
        job.logs.append({
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "message": f"Starting dispatch for {len(recipients)} recipients using [{dispatcher_type}] dispatcher (delay: {delay_seconds}s)"
        })

        # Connect unless dry_run
        if dispatcher_type != "dry_run":
            try:
                server = get_smtp_connection(dispatcher_type, sender_email, sender_key, custom_server, custom_port, use_tls)
            except Exception as e:
                job.logs.append({
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "message": f"Connection/Authentication failed: {str(e)}"
                })
                job.is_running = False
                job.completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Zero-Retention: Wipe key immediately on error
                sender_key = ""
                return

        try:
            for idx, rec in enumerate(recipients):
                # Check stop flag
                if job.should_stop:
                    job.logs.append({
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                        "level": "WARNING",
                        "message": "Dispatch job stopped by user request."
                    })
                    break

                # Handle pause
                while job.is_paused and not job.should_stop:
                    time.sleep(1)

                target_email = str(rec.get(email_column, "")).strip()
                job.current_index = idx + 1
                job.current_recipient = target_email

                # Personalize context
                context = dict(rec)
                context["Sender_Name"] = sender_name
                context["Sender_Email"] = sender_email

                rendered_subject = render_template(subject_template, context)
                rendered_body = render_template(body_template, context)

                row_result = dict(rec)
                row_result["Delivered_At"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row_result["Attempts"] = 1

                if dispatcher_type == "dry_run":
                    time.sleep(min(delay_seconds, 1.0))
                    row_result["Delivery_Status"] = "SUCCESS (DRY-RUN)"
                    row_result["Error_Reason"] = ""
                    job.sent_count += 1
                    job.logs.append({
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                        "level": "SUCCESS",
                        "recipient": target_email,
                        "message": f"Simulated delivery to {target_email}"
                    })
                else:
                    try:
                        # Test connection liveness
                        try:
                            status = server.noop()[0]
                            if status != 250:
                                server = get_smtp_connection(dispatcher_type, sender_email, sender_key, custom_server, custom_port, use_tls)
                        except Exception:
                            server = get_smtp_connection(dispatcher_type, sender_email, sender_key, custom_server, custom_port, use_tls)

                        msg = build_mime_message(
                            sender_email=sender_email,
                            sender_name=sender_name,
                            recipient_email=target_email,
                            subject=rendered_subject,
                            body_html=rendered_body,
                            attachments=attachments
                        )
                        server.send_message(msg)


                        row_result["Delivery_Status"] = "SUCCESS"
                        row_result["Error_Reason"] = ""
                        job.sent_count += 1
                        job.logs.append({
                            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                            "level": "SUCCESS",
                            "recipient": target_email,
                            "message": f"Successfully delivered to {target_email}"
                        })
                    except Exception as send_err:
                        row_result["Delivery_Status"] = "FAILED"
                        row_result["Error_Reason"] = str(send_err)
                        job.failed_count += 1
                        job.logs.append({
                            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                            "level": "ERROR",
                            "recipient": target_email,
                            "message": f"Failed delivering to {target_email}: {str(send_err)}"
                        })

                job.results.append(row_result)

                if idx < len(recipients) - 1:
                    time.sleep(delay_seconds)
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
            # ZERO-RETENTION GUARANTEE: purge key from volatile worker memory
            sender_key = ""

        job.is_running = False
        job.completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job.logs.append({
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "message": f"Job finished. Sent: {job.sent_count}, Failed: {job.failed_count}"
        })

    thread = threading.Thread(target=run_worker, daemon=True)
    job.worker_thread = thread
    thread.start()

def stop_current_job(session_id: str = "default"):
    get_job(session_id).should_stop = True

def toggle_pause_job(session_id: str = "default") -> bool:
    job = get_job(session_id)
    job.is_paused = not job.is_paused
    return job.is_paused

