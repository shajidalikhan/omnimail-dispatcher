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
    get_saved_credentials,
    save_credentials_to_env,
    get_auth_settings
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

# API Routes
@app.get("/api/config")
def get_config():
    saved = get_saved_credentials()
    # ZERO-RETENTION GUARANTEE: Never broadcast key over network
    saved["sender_key"] = ""
    return {
        "presets": DISPATCHER_PRESETS,
        "saved": saved,
        "default_subject": DEFAULT_SUBJECT,
        "default_body_html": DEFAULT_BODY_HTML,
        "default_body_text": DEFAULT_BODY_TEXT,
        "guidelines": PERSONALIZATION_GUIDELINES
    }

@app.post("/api/save-credentials")
def save_credentials(payload: SaveCredentialsRequest):
    # Zero-Retention: In multi-user deployment, credentials are kept client-side only
    return {"success": True, "message": "Zero-Retention active: Key will be held securely in client session memory only."}

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

        return {
            "total_rows": len(records),
            "columns": columns,
            "detected_email_col": email_col,
            "selected_email_col": selected_col,
            "validation_summary": summary,
            "sample_rows": records[:5]
        }
    except Exception as e:
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

    # Directly executes single test over SMTP without writing key to disk
    res = send_single_test_email(
        dispatcher_type=payload.dispatcher_type,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
        sender_key=payload.sender_key,
        test_recipient_email=payload.test_recipient_email,
        subject=payload.subject,
        body_html=payload.body_html,
        custom_server=payload.custom_smtp_server or "",
        custom_port=payload.custom_smtp_port or 587,
        use_tls=payload.custom_use_tls if payload.custom_use_tls is not None else True,
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

    # ZERO-RETENTION: We never write payload.sender_key to disk or .env!
    # The key is passed directly to the ephemeral worker thread and wiped upon job finish.
    start_batch_dispatch_job(
        recipients=valid_recipients,
        email_column=email_col,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        dispatcher_type=payload.dispatcher_type,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
        sender_key=payload.sender_key,
        custom_server=payload.custom_smtp_server or "",
        custom_port=payload.custom_smtp_port or 587,
        use_tls=payload.custom_use_tls if payload.custom_use_tls is not None else True,
        delay_seconds=payload.delay_seconds,
        session_id=session_id,
        attachments=atts
    )
    return {"success": True, "message": f"Dispatch job started for {len(valid_recipients)} recipients with Zero-Retention security."}

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
    start_batch_dispatch_job(
        recipients=failed_recs,
        email_column=email_col,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        dispatcher_type=payload.dispatcher_type,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
        sender_key=payload.sender_key,
        custom_server=payload.custom_smtp_server or "",
        custom_port=payload.custom_smtp_port or 587,
        use_tls=payload.custom_use_tls if payload.custom_use_tls is not None else True,
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


# Mount frontend directory
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
