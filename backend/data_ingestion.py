import re
import io
import json
from typing import Dict, List, Tuple, Any, Optional
import pandas as pd

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def is_valid_email(email: str) -> bool:
    if not isinstance(email, str):
        return False
    email = email.strip()
    return bool(EMAIL_REGEX.match(email))

def detect_email_column(columns: List[str], sample_records: List[Dict[str, Any]]) -> Optional[str]:
    """Heuristic to auto-detect which column holds recipient email addresses."""
    # 1. Look for explicit column names
    common_names = ["email", "mail", "e-mail", "email_id", "email id", "recipient", "recipient_email", "mail_id"]
    for col in columns:
        if col.strip().lower() in common_names:
            return col
            
    # 2. Match column name containing "email" or "mail"
    for col in columns:
        clean = col.strip().lower()
        if "email" in clean or "mail" in clean:
            return col

    # 3. Sample values check
    for col in columns:
        valid_count = 0
        total_non_empty = 0
        for row in sample_records[:10]:
            val = str(row.get(col, "")).strip()
            if val:
                total_non_empty += 1
                if is_valid_email(val):
                    valid_count += 1
        if total_non_empty > 0 and (valid_count / total_non_empty) >= 0.5:
            return col
            
    return None

def parse_uploaded_file(file_bytes: bytes, filename: str) -> Tuple[List[Dict[str, Any]], List[str], Optional[str]]:
    """Parse Excel, CSV, TSV, or JSON bytes into list of row dicts and column list."""
    filename_lower = filename.lower()
    
    if filename_lower.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    elif filename_lower.endswith('.csv'):
        # Try utf-8 first, fallback to latin-1
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, encoding='latin-1')
    elif filename_lower.endswith('.tsv') or filename_lower.endswith('.txt'):
        df = pd.read_csv(io.BytesIO(file_bytes), sep='\t', dtype=str)
    elif filename_lower.endswith('.json'):
        data = json.loads(file_bytes.decode('utf-8'))
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Check if dict of lists or list is in a key
            for key, val in data.items():
                if isinstance(val, list):
                    df = pd.DataFrame(val)
                    break
            else:
                df = pd.DataFrame([data])
        else:
            raise ValueError("Unsupported JSON structure: expected list of objects")
    else:
        raise ValueError(f"Unsupported file format: {filename}. Please use .xlsx, .csv, .tsv, or .json")

    # Clean DataFrame: strip whitespace from headers and fill NaN with empty string
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")
    
    records = df.to_dict(orient="records")
    columns = list(df.columns)
    
    email_col = detect_email_column(columns, records)
    return records, columns, email_col

def parse_raw_text(raw_text: str) -> Tuple[List[Dict[str, Any]], List[str], Optional[str]]:
    """Parse comma/newline separated emails or tabular pasted text."""
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines:
        return [], [], None

    # Check if first line looks like header
    first_line = lines[0]
    if "," in first_line or "\t" in first_line:
        sep = "," if "," in first_line else "\t"
        df = pd.read_csv(io.StringIO(raw_text), sep=sep, dtype=str).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        records = df.to_dict(orient="records")
        columns = list(df.columns)
        email_col = detect_email_column(columns, records)
        return records, columns, email_col

    # Otherwise treat as list of emails
    emails = []
    for line in lines:
        parts = re.split(r"[,; ]+", line)
        for part in parts:
            if part.strip():
                emails.append({"Email": part.strip(), "Name": part.split("@")[0]})
                
    columns = ["Email", "Name"]
    return emails, columns, "Email"

def validate_and_deduplicate(records: List[Dict[str, Any]], email_col: str) -> Dict[str, Any]:
    """Validate each record's email, check duplicates, and format status."""
    seen_emails = set()
    valid_records = []
    invalid_records = []
    duplicate_records = []

    for idx, row in enumerate(records):
        email_val = str(row.get(email_col, "")).strip()
        row_copy = dict(row)
        row_copy["_row_id"] = idx + 1
        row_copy["_target_email"] = email_val

        if not email_val or not is_valid_email(email_val):
            row_copy["_validation_status"] = "INVALID_EMAIL"
            invalid_records.append(row_copy)
        elif email_val.lower() in seen_emails:
            row_copy["_validation_status"] = "DUPLICATE"
            duplicate_records.append(row_copy)
        else:
            row_copy["_validation_status"] = "VALID"
            seen_emails.add(email_val.lower())
            valid_records.append(row_copy)

    return {
        "total": len(records),
        "valid_count": len(valid_records),
        "invalid_count": len(invalid_records),
        "duplicate_count": len(duplicate_records),
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "duplicate_records": duplicate_records,
        "email_column": email_col
    }

def export_status_report(records_with_status: List[Dict[str, Any]], format: str = "xlsx") -> bytes:
    """Generate an Excel or CSV file containing original data plus delivery verification columns."""
    df = pd.DataFrame(records_with_status)
    
    # Clean internal helper columns
    drop_cols = [c for c in df.columns if c.startswith("_row_id") or c.startswith("_target_email")]
    df = df.drop(columns=drop_cols, errors="ignore")
    
    # Ensure status columns are placed at the end or prioritized
    priority_status_cols = ["Delivery_Status", "Delivered_At", "Error_Reason", "Attempts"]
    for pcol in priority_status_cols:
        if pcol not in df.columns:
            df[pcol] = "PENDING" if pcol == "Delivery_Status" else ""

    output = io.BytesIO()
    if format == "csv":
        df.to_csv(output, index=False, encoding="utf-8-sig")
    else:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Dispatch Results")
    
    output.seek(0)
    return output.read()
