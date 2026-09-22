import os
import base64
import secrets
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import (
    DISPATCHER_PRESETS,
    LOCAL_MODE,
    is_local_mode,
    get_saved_credentials,
    save_credentials_to_env,
    get_auth_settings,
)
from backend.logging_service import (
    log_info,
    log_warning,
    log_error,
    get_recent_developer_logs,
    get_dispatch_history,
    get_history_summary_stats,
    DEV_LOG_PATH,
    HISTORY_CSV_PATH,
    REPORTS_DIR,
)
from backend.data_ingestion import (
    parse_uploaded_file,
    parse_raw_text,
    validate_and_deduplicate,
    export_status_report
)
from backend.template_service import (
    render_template,
    extract_variables,
    analyze_template_hygiene,
    PERSONALIZATION_GUIDELINES,
    DEFAULT_SUBJECT,
    DEFAULT_BODY_HTML,
    DEFAULT_BODY_TEXT
)
from backend.mail_dispatcher import (
    current_job,
    send_single_test_email,
    start_batch_dispatch_job,
    stop_current_job,
    toggle_pause_job
)

app = FastAPI(title="OmniMail Dispatcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    auth = get_auth_settings()
    if not auth["auth_enabled"]:
        return await call_next(request)

    # Allow CORS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return Response(
            content="Unauthorized Access: Credentials required.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="OmniMail Dispatcher"'}
        )

    try:
        encoded_creds = auth_header.split(" ", 1)[1]
        decoded_bytes = base64.b64decode(encoded_creds)
        decoded_str = decoded_bytes.decode("utf-8")
        username, password = decoded_str.split(":", 1)
    except Exception:
        return Response(
            content="Unauthorized: Invalid Authorization header.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="OmniMail Dispatcher"'}
        )

    correct_user = secrets.compare_digest(username, auth["username"])
    correct_pass = secrets.compare_digest(password, auth["password"])

    if not (correct_user and correct_pass):
        return Response(
            content="Unauthorized: Invalid Username or Password.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="OmniMail Dispatcher"'}
        )

    return await call_next(request)


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Multi-Tenant Session Store (Isolated in-memory workspaces per browser tab)
sessions: Dict[str, Dict[str, Any]] = {}

def get_session(session_id: str) -> Dict[str, Any]:
    clean_id = session_id or "default"
    if clean_id not in sessions:
        sessions[clean_id] = {
            "raw_records": [],
            "columns": [],
            "detected_email_col": "",
            "selected_email_col": "",
            "validation_summary": {},
            "last_subject_template": DEFAULT_SUBJECT,
            "last_body_template": DEFAULT_BODY_HTML,
            "attachments": [],  # List of {"filename": str, "content_bytes": bytes, "size": int}
        }
    return sessions[clean_id]

def extract_session_id(request: Request) -> str:
    return request.headers.get("X-Session-ID") or request.query_params.get("session_id") or "default"


class SaveCredentialsRequest(BaseModel):
    dispatcher_type: str
    sender_email: str
    sender_name: str
    sender_key: str
    custom_smtp_server: Optional[str] = ""
    custom_smtp_port: Optional[int] = 587
    custom_use_tls: Optional[bool] = True

class PasteDataRequest(BaseModel):
    raw_text: str

class ColumnSelectRequest(BaseModel):
    email_column: str

class PreviewRequest(BaseModel):
    subject_template: str
    body_template: str
    recipient_index: int = 0
    sender_name: str = ""
    sender_email: str = ""

class TemplateAnalysisRequest(BaseModel):
    subject: str
    body: str

class TestEmailRequest(BaseModel):
    dispatcher_type: str
    sender_email: str
    sender_name: str
    sender_key: str
    test_recipient_email: str
    subject: str
    body_html: str
    custom_smtp_server: Optional[str] = ""
    custom_smtp_port: Optional[int] = 587
    custom_use_tls: Optional[bool] = True

class StartDispatchRequest(BaseModel):
    dispatcher_type: str
    sender_email: str
    sender_name: str
    sender_key: str
    subject_template: str
    body_template: str
    delay_seconds: float = 3.0
    custom_smtp_server: Optional[str] = ""
    custom_smtp_port: Optional[int] = 587
    custom_use_tls: Optional[bool] = True
    save_settings: bool = False


def _resolve_smtp_settings(
    dispatcher_type: str,
    sender_email: str,
    sender_name: str,
    sender_key: str,
    custom_smtp_server: str = "",
    custom_smtp_port: int = 587,
    custom_use_tls: bool = True,
) -> Dict[str, Any]:
    """In local mode, fill missing fields from the on-disk .env file."""
    if not LOCAL_MODE:
        return {
            "dispatcher_type": dispatcher_type,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "sender_key": sender_key,
            "custom_smtp_server": custom_smtp_server or "",
            "custom_smtp_port": custom_smtp_port or 587,
            "custom_use_tls": custom_use_tls if custom_use_tls is not None else True,
        }
    saved = get_saved_credentials()
    return {
        "dispatcher_type": dispatcher_type or saved["dispatcher_type"],
        "sender_email": sender_email or saved["sender_email"],
        "sender_name": sender_name or saved["sender_name"],
        "sender_key": sender_key or saved["sender_key"],
        "custom_smtp_server": custom_smtp_server or saved["custom_smtp_server"],
        "custom_smtp_port": custom_smtp_port or saved["custom_smtp_port"],
        "custom_use_tls": (
            custom_use_tls
            if custom_use_tls is not None
            else saved["custom_use_tls"]
        ),
    }


def _maybe_persist_local_credentials(
    dispatcher_type: str,
    sender_email: str,
    sender_name: str,
    sender_key: str,
    custom_smtp_server: str,
    custom_smtp_port: int,
    custom_use_tls: bool,
    save_settings: bool,
) -> None:
    if not is_local_mode() or not save_settings:
        return
    if not sender_email or not sender_key:
        return
    save_credentials_to_env(
        dispatcher_type=dispatcher_type,
        sender_email=sender_email,
        sender_name=sender_name,
        password_or_key=sender_key,
        smtp_server=custom_smtp_server or "",
        smtp_port=custom_smtp_port or 587,
        use_tls=custom_use_tls if custom_use_tls is not None else True,
    )


# API Routes
@app.get("/api/config")
def get_config():
    local_active = is_local_mode()
    saved = get_saved_credentials()
    if not local_active:
        saved["sender_key"] = ""
    return {
        "presets": DISPATCHER_PRESETS,
        "saved": saved,
        "local_mode": local_active,
        "default_subject": DEFAULT_SUBJECT,
        "default_body_html": DEFAULT_BODY_HTML,
        "default_body_text": DEFAULT_BODY_TEXT,
        "guidelines": PERSONALIZATION_GUIDELINES,
    }

@app.post("/api/save-credentials")
def save_credentials(payload: SaveCredentialsRequest):
    if not is_local_mode():
        raise HTTPException(
            status_code=403,
            detail="Saving credentials to .env is only available in local deployment mode.",
        )
    save_credentials_to_env(
        dispatcher_type=payload.dispatcher_type,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
        password_or_key=payload.sender_key,
        smtp_server=payload.custom_smtp_server or "",
        smtp_port=payload.custom_smtp_port or 587,
        use_tls=payload.custom_use_tls if payload.custom_use_tls is not None else True,
    )
    log_info(f"Credentials saved to .env for provider [{payload.dispatcher_type}], sender: {payload.sender_email}")
    return {
        "success": True,
        "message": "Settings saved to local .env file. Your credentials will be pre-filled automatically on the next restart."
    }


@app.post("/api/upload")
async def upload_dataset(request: Request, file: UploadFile = File(...)):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    try:
        content = await file.read()
        records, columns, email_col = parse_uploaded_file(content, file.filename)
        
        if not records:
            raise HTTPException(status_code=400, detail="The uploaded file contains no data rows.")
            
        selected_col = email_col or (columns[0] if columns else "")
        summary = validate_and_deduplicate(records, selected_col) if selected_col else {}

        session_data["raw_records"] = records
        session_data["columns"] = columns
        session_data["detected_email_col"] = email_col
        session_data["selected_email_col"] = selected_col
        session_data["validation_summary"] = summary

        log_info(
            f"[DATA INGESTION] Uploaded '{file.filename}': {len(records)} rows, "
            f"detected email column: '{email_col}', valid: {summary.get('valid_count', 0)}"
        )

        return {
            "filename": file.filename,
            "total_rows": len(records),
            "columns": columns,
            "detected_email_col": email_col,
            "selected_email_col": selected_col,
            "validation_summary": summary,
            "sample_rows": records[:5]
        }
    except Exception as e:
        log_error(f"[DATA INGESTION] Failed to process upload '{file.filename}': {e}")
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

@app.post("/api/paste")
def paste_dataset(request: Request, payload: PasteDataRequest):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    try:
        records, columns, email_col = parse_raw_text(payload.raw_text)
        if not records:
            raise HTTPException(status_code=400, detail="No valid data or emails could be parsed.")

        selected_col = email_col or (columns[0] if columns else "")
        summary = validate_and_deduplicate(records, selected_col)

        session_data["raw_records"] = records
        session_data["columns"] = columns
        session_data["detected_email_col"] = email_col
        session_data["selected_email_col"] = selected_col
        session_data["validation_summary"] = summary

        log_info(
            f"[DATA INGESTION] Pasted text processed: {len(records)} rows, "
            f"detected email column: '{email_col}', valid: {summary.get('valid_count', 0)}"
        )

        return {
            "total_rows": len(records),
            "columns": columns,
            "detected_email_col": email_col,
            "selected_email_col": selected_col,
            "validation_summary": summary,
            "sample_rows": records[:5]
        }
    except Exception as e:
        log_error(f"[DATA INGESTION] Failed to parse pasted data: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/set-email-column")
def set_email_column(request: Request, payload: ColumnSelectRequest):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    col = payload.email_column
    if col not in session_data.get("columns", []):
        raise HTTPException(status_code=400, detail=f"Column '{col}' not found in uploaded dataset.")
        
    session_data["selected_email_col"] = col
    records = session_data.get("raw_records", [])
    summary = validate_and_deduplicate(records, col)
    session_data["validation_summary"] = summary
    return {"selected_email_col": col, "validation_summary": summary}

@app.post("/api/preview")
def preview_recipient(request: Request, payload: PreviewRequest):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    records = session_data.get("raw_records", [])
    if not records:
        sample_context = {
            "Name": "Dr. Sarah Jenkins",
            "University": "Stanford University",
            "Research_Area": "Artificial Intelligence & Distributed Systems",
            "Email": "sarah.jenkins@example.edu",
            "Sender_Name": payload.sender_name or "Academic Outreach",
            "Sender_Email": payload.sender_email or "sender@domain.com"
        }
        total = 1
        current_idx = 0
    else:
        idx = max(0, min(payload.recipient_index, len(records) - 1))
        sample_context = dict(records[idx])
        sample_context["Sender_Name"] = payload.sender_name
        sample_context["Sender_Email"] = payload.sender_email
        total = len(records)
        current_idx = idx

    rendered_subject = render_template(payload.subject_template, sample_context)
    rendered_body = render_template(payload.body_template, sample_context)
    subject_vars = extract_variables(payload.subject_template)
    body_vars = extract_variables(payload.body_template)

    return {
        "current_index": current_idx,
        "total_records": total,
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
        "recipient_context": sample_context,
        "used_variables": sorted(list(set(subject_vars + body_vars)))
    }

@app.post("/api/analyze-template")
def analyze_template(payload: TemplateAnalysisRequest):
    analysis = analyze_template_hygiene(payload.subject, payload.body)
    return analysis

@app.post("/api/upload-attachment")
async def upload_attachment(request: Request, file: UploadFile = File(...)):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    content = await file.read()
    
    # Cap single file at 25MB
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds maximum allowed size (25MB).")

    new_att = {
        "filename": file.filename,
        "content_bytes": content,
        "size": len(content),
        "content_type": file.content_type or "application/octet-stream"
    }
    # Deduplicate by filename
    session_data["attachments"] = [a for a in session_data.get("attachments", []) if a["filename"] != file.filename]
    session_data["attachments"].append(new_att)

    total_size = sum(a["size"] for a in session_data["attachments"])
    return {
        "success": True,
        "total_count": len(session_data["attachments"]),
        "total_size": total_size,
        "attachments": [{"filename": a["filename"], "size": a["size"]} for a in session_data["attachments"]]
    }

@app.get("/api/attachments")
def get_attachments(request: Request):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    atts = session_data.get("attachments", [])
    return {
        "total_count": len(atts),
        "total_size": sum(a["size"] for a in atts),
        "attachments": [{"filename": a["filename"], "size": a["size"]} for a in atts]
    }

@app.delete("/api/delete-attachment/{filename}")
def delete_attachment(request: Request, filename: str):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    session_data["attachments"] = [a for a in session_data.get("attachments", []) if a["filename"] != filename]
    atts = session_data["attachments"]
    return {
        "success": True,
        "total_count": len(atts),
        "total_size": sum(a["size"] for a in atts),
        "attachments": [{"filename": a["filename"], "size": a["size"]} for a in atts]
    }

@app.post("/api/clear-attachments")
def clear_attachments(request: Request):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    session_data["attachments"] = []
    return {"success": True, "message": "All attachments removed."}

@app.post("/api/test-email")
def test_email(request: Request, payload: TestEmailRequest):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    atts = session_data.get("attachments", [])

    smtp = _resolve_smtp_settings(
        payload.dispatcher_type,
        payload.sender_email,
        payload.sender_name,
        payload.sender_key,
        payload.custom_smtp_server or "",
        payload.custom_smtp_port or 587,
        payload.custom_use_tls if payload.custom_use_tls is not None else True,
    )
    res = send_single_test_email(
        dispatcher_type=smtp["dispatcher_type"],
        sender_email=smtp["sender_email"],
        sender_name=smtp["sender_name"],
        sender_key=smtp["sender_key"],
        test_recipient_email=payload.test_recipient_email,
        subject=payload.subject,
        body_html=payload.body_html,
        custom_server=smtp["custom_smtp_server"],
        custom_port=smtp["custom_smtp_port"],
        use_tls=smtp["custom_use_tls"],
        attachments=atts
    )
    return res

@app.post("/api/start-dispatch")
def start_dispatch(request: Request, payload: StartDispatchRequest):
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    summary = session_data.get("validation_summary", {})
    valid_recipients = summary.get("valid_records", [])

    if not valid_recipients:
        raise HTTPException(status_code=400, detail="No valid recipients available to send. Please upload or paste data first.")

    email_col = session_data.get("selected_email_col", "")
    atts = session_data.get("attachments", [])

    smtp = _resolve_smtp_settings(
        payload.dispatcher_type,
        payload.sender_email,
        payload.sender_name,
        payload.sender_key,
        payload.custom_smtp_server or "",
        payload.custom_smtp_port or 587,
        payload.custom_use_tls if payload.custom_use_tls is not None else True,
    )
    _maybe_persist_local_credentials(
        smtp["dispatcher_type"],
        smtp["sender_email"],
        smtp["sender_name"],
        smtp["sender_key"],
        smtp["custom_smtp_server"],
        smtp["custom_smtp_port"],
        smtp["custom_use_tls"],
        payload.save_settings,
    )

    start_batch_dispatch_job(
        recipients=valid_recipients,
        email_column=email_col,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        dispatcher_type=smtp["dispatcher_type"],
        sender_email=smtp["sender_email"],
        sender_name=smtp["sender_name"],
        sender_key=smtp["sender_key"],
        custom_server=smtp["custom_smtp_server"],
        custom_port=smtp["custom_smtp_port"],
        use_tls=smtp["custom_use_tls"],
        delay_seconds=payload.delay_seconds,
        session_id=session_id,
        attachments=atts
    )
    mode_note = (
        " Credentials synced to local .env."
        if is_local_mode() and payload.save_settings
        else ""
    )
    return {
        "success": True,
        "message": f"Dispatch job started for {len(valid_recipients)} recipients.{mode_note}",
    }

@app.get("/api/dispatch-status")
def get_dispatch_status(request: Request):
    from backend.mail_dispatcher import get_job
    session_id = extract_session_id(request)
    return get_job(session_id).get_status()

@app.post("/api/dispatch-control/{action}")
def control_dispatch(request: Request, action: str):
    session_id = extract_session_id(request)
    if action == "stop":
        stop_current_job(session_id)
        return {"message": "Stop signal sent to job."}
    elif action == "toggle-pause":
        new_state = toggle_pause_job(session_id)
        return {"is_paused": new_state, "message": "Paused" if new_state else "Resumed"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@app.post("/api/retry-failed")
def retry_failed(request: Request, payload: StartDispatchRequest):
    from backend.mail_dispatcher import get_job
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    job = get_job(session_id)
    
    failed_recs = [r for r in job.results if r.get("Delivery_Status") == "FAILED"]
    if not failed_recs:
        raise HTTPException(status_code=400, detail="No failed recipients to retry.")

    email_col = session_data.get("selected_email_col", "")
    atts = session_data.get("attachments", [])
    smtp = _resolve_smtp_settings(
        payload.dispatcher_type,
        payload.sender_email,
        payload.sender_name,
        payload.sender_key,
        payload.custom_smtp_server or "",
        payload.custom_smtp_port or 587,
        payload.custom_use_tls if payload.custom_use_tls is not None else True,
    )
    start_batch_dispatch_job(
        recipients=failed_recs,
        email_column=email_col,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        dispatcher_type=smtp["dispatcher_type"],
        sender_email=smtp["sender_email"],
        sender_name=smtp["sender_name"],
        sender_key=smtp["sender_key"],
        custom_server=smtp["custom_smtp_server"],
        custom_port=smtp["custom_smtp_port"],
        use_tls=smtp["custom_use_tls"],
        delay_seconds=payload.delay_seconds,
        session_id=session_id,
        attachments=atts
    )
    return {"success": True, "message": f"Retrying {len(failed_recs)} failed recipients."}


@app.get("/api/export-results")
def export_results(request: Request, format: str = "xlsx"):
    from backend.mail_dispatcher import get_job
    session_id = extract_session_id(request)
    session_data = get_session(session_id)
    job = get_job(session_id)

    records_to_export = job.results
    if not records_to_export:
        records_to_export = session_data.get("raw_records", [])

    if not records_to_export:
        raise HTTPException(status_code=400, detail="No data available to export.")

    data_bytes = export_status_report(records_to_export, format=format)
    filename = f"dispatch_report_{job.job_id or 'latest'}.{format}"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "text/csv"
    
    return Response(
        content=data_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ── LOGGING & USAGE AUDIT ROUTES ─────────────────────────────────────────────

@app.get("/api/logs/history")
def get_usage_history():
    """Returns JSON list of historical dispatch runs and overall statistics."""
    return {
        "summary": get_history_summary_stats(),
        "records": get_dispatch_history(),
    }


@app.get("/api/logs/history/export")
def export_usage_history_csv():
    """Download the complete dispatch_history.csv file."""
    if not HISTORY_CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="No dispatch history recorded yet.")
    return Response(
        content=HISTORY_CSV_PATH.read_bytes(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dispatch_history.csv"'}
    )


@app.get("/api/logs/history/report/{job_id}")
def download_archived_report(job_id: str):
    """Download an archived XLSX or CSV report file for a past dispatch job."""
    # Sanitize job_id to prevent directory traversal
    clean_id = Path(job_id).name
    target_xlsx = REPORTS_DIR / f"dispatch_report_{clean_id}.xlsx"
    target_csv = REPORTS_DIR / f"dispatch_report_{clean_id}.csv"

    if target_xlsx.exists():
        return Response(
            content=target_xlsx.read_bytes(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{target_xlsx.name}"'}
        )
    elif target_csv.exists():
        return Response(
            content=target_csv.read_bytes(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{target_csv.name}"'}
        )
    else:
        raise HTTPException(status_code=404, detail=f"No archived report found for job '{clean_id}'")


@app.get("/api/logs/developer")
def get_developer_logs_api(download: bool = False):
    """Retrieve recent lines from app_events.log or download the full log file."""
    if not DEV_LOG_PATH.exists():
        if download:
            raise HTTPException(status_code=404, detail="No developer log exists yet.")
        return {"lines": ["[No developer log entries recorded yet]"]}

    if download:
        return Response(
            content=DEV_LOG_PATH.read_bytes(),
            media_type="text/plain",
            headers={"Content-Disposition": 'attachment; filename="app_events.log"'}
        )
    return {"lines": get_recent_developer_logs(max_lines=300)}


@app.post("/api/logs/developer/clear")
def clear_developer_log_api():
    """Clears the developer log file buffer."""
    if DEV_LOG_PATH.exists():
        DEV_LOG_PATH.write_text("", encoding="utf-8")
    log_info("Developer log file cleared via admin command.")
    return {"success": True, "message": "Developer log cleared."}


# Mount frontend directory
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
