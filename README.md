# OmniMail Dispatcher

**OmniMail Dispatcher** is an intelligent, privacy-first desktop platform for sending personalized bulk emails. It ingests recipient datasets from various sources (Excel, CSV, JSON, raw paste), provides a rich personalization studio with copywriting guidelines and spam-hygiene checks, throttles sending to prevent anti-spam blocks, and tracks delivery status with downloadable verification reports.

---

## Key Features

1. **Flexible Mail ID & Dispatcher Selection**:
   - Choose between **Gmail**, **Outlook / Office 365**, **Yahoo**, **Custom / Institutional SMTP**, or **Safe Simulation (Dry Run)**.
   - Configure Sender Mail ID (From address), Display Name, and custom credentials.
2. **Dedicated Mail Key / App Password Space**:
   - Input your 16-character App Password or API key with visibility toggle (show/hide).
   - Securely saved locally into `.env` (never hardcoded in code or transmitted to external servers).
   - Step-by-step guidance card for generating Google App Passwords.
3. **Multi-Source Recipient Ingestion**:
   - Accepts Microsoft Excel (`.xlsx`, `.xls`), CSV, TSV, JSON, or raw clipboard paste.
   - Smart email column auto-detection and custom column selector.
   - Automatic RFC regex validation, duplicate detection, and sanitization.
4. **Personalization Studio & Copywriting Guide**:
   - Dynamic variable chips (e.g. `{{Name}}`, `{{University}}`, `{{Research_Area}}`) dynamically generated from your uploaded columns.
   - Fallback syntax support: `{{Name | default('Colleague')}}`.
   - Real-time Spam & Deliverability Score (0–100) that flags spam trigger words and analyzes subject line length.
   - Built-in guidance rules explaining cold email salutations, relevant context, single CTAs, and anti-spam best practices.
   - Live recipient-by-recipient preview with next/previous pagination.
5. **Pre-flight Testing**:
   - Send a single live test email to your personal address before launching the batch.
6. **Throttled Queue & Real-Time Verification Audit**:
   - Configurable rate-limiting slider (e.g., 2 to 10 seconds between emails) to protect account reputation.
   - Real-time progress bar, delivery logs, pause/resume, and stop controls.
   - Download updated delivery reports in **Excel (`.xlsx`)** or **CSV** with `Delivery_Status`, `Delivered_At`, and `Error_Reason` columns appended.
   - 1-click **"Retry Failed Recipients"** button to re-queue only unsuccessful sends.

---

## Quick Start Guide

Detailed setup steps for Windows, macOS, and Linux are in **[LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md)**.

### Option 1: Double-Click Launcher (Windows)
Double-click `start_local.bat` (or `start_dispatcher.bat`) in the root folder.

### Option 2: Terminal / Command Prompt
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run local server
python run_local.py
```
The program will start the local server and automatically open your default browser at `http://127.0.0.1:8000`.

---

## Workflow Steps

### Step 1: Dispatcher & Key Setup
- Select your mail provider (e.g. **Gmail** or **Dry Run** for zero-risk testing).
- Enter your **Sender Email** and **Display Name**.
- Enter your **App Password** (for Gmail: Go to Google Account > Security > 2-Step Verification > App Passwords).
- Click **Save Credentials (.env)**.

### Step 2: Import Recipients
- Drag and drop your `.xlsx` or `.csv` recipient spreadsheet (or click **Load Built-in Sample Dataset**).
- Confirm the target email column.
- Review validation metrics (Valid recipients, Invalid emails, Duplicates).

### Step 3: Template & Personalization
- Insert dynamic chips like `+ {{Name}}` or `+ {{University}}` into your subject line and email body.
- Check the deliverability score and review recommendations.
- Flip through recipient previews with the arrows to ensure personalization looks natural.
- Click **Send Single Test Email** to verify how it appears in your own inbox.

### Step 4: Dispatch & Verification
- Set the throttle interval (recommended: 3.0s).
- Click **Launch Batch Dispatch**.
- Watch real-time delivery logs and status progress.
- Once finished, click **Download Excel (.xlsx)** to save your verified delivery report.

---

## Cloud Deployment (Render.com)

OmniMail Dispatcher comes production-ready for deployment on **Render.com** (with free SSL & HTTP Basic Authentication).
Refer to [DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md) for full step-by-step instructions.

