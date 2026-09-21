# Local Deployment Guide (Clone → Run)

Use this guide to install **OmniMail Dispatcher** on your own computer from GitHub. This flow uses the **`local-deployment`** branch: SMTP credentials are stored in a **`.env`** file on your machine (never committed to Git).

For cloud hosting on Render, use [DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md) and the **`main`** branch instead.

---

## What you need

| Requirement | Notes |
|-------------|--------|
| **Git** | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Python 3.10+** | Check with `python --version` |
| **Internet** | To clone the repo and install packages (SMTP still uses your mail provider when sending) |

---

## Step 1: Clone the repository

Open **PowerShell**, **Command Prompt**, or **Terminal** and run:

```bash
git clone https://github.com/shajidalikhan/omnimail-dispatcher.git
cd omnimail-dispatcher
```

Switch to the local-deployment branch:

```bash
git checkout local-deployment
```

---

## Step 2: Create a virtual environment (recommended)

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## Step 3: Install dependencies

With the virtual environment activated:

```bash
pip install -r requirements.txt
```

---

## Step 4: Configure credentials (`.env`)

Copy the example file and edit it with your details:

**Windows:**

```powershell
copy .env.example .env
notepad .env
```

**macOS / Linux:**

```bash
cp .env.example .env
nano .env   # or use any text editor
```

Example values:

```env
DEFAULT_DISPATCHER=gmail
SENDER_EMAIL=your.email@gmail.com
SENDER_NAME=Prof. / Dr. Your Name
SENDER_KEY=your_16_character_app_password
CUSTOM_SMTP_SERVER=
CUSTOM_SMTP_PORT=587
CUSTOM_USE_TLS=true
```

**Gmail:** use a [Google App Password](https://myaccount.google.com/apppasswords), not your normal Gmail password.

You can also leave `.env` empty at first and fill credentials in the web UI, then click **Save to .env (Local)**.

> **Important:** `.env` is listed in `.gitignore`. Do not commit it or share it.

---

## Step 5: Run the application

From the project folder (venv activated):

```bash
python run_local.py
```

This starts the server on **http://127.0.0.1:8000** and opens your default browser.

**Alternative (no auto-open browser):**

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000 manually.

To stop the server, press **Ctrl+C** in the terminal.

---

## Step 6: First use in the browser

1. **Step 1 — Dispatcher & Key:** Choose provider (e.g. Gmail or **Dry Run** for testing), enter sender email, display name, and app password. Click **Save to .env (Local)**.
2. **Step 2 — Import:** Upload Excel/CSV or paste recipients.
3. **Step 3 — Template:** Personalize subject/body, preview, optional test email.
4. **Step 4 — Dispatch:** Set throttle delay and launch the batch; download the report when finished.

After a restart, Step 1 fields should pre-fill from `.env`.

---

## Updating to the latest version

```bash
cd omnimail-dispatcher
git checkout local-deployment
git pull origin local-deployment
pip install -r requirements.txt
```

Your local `.env` is unchanged by `git pull`.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| **`python` not found** | Install Python from [python.org](https://www.python.org/downloads/) and enable “Add Python to PATH”. On macOS/Linux try `python3` instead of `python`. |
| **Port 8000 already in use** | Stop the other process, or run: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080` and open http://127.0.0.1:8080 |
| **Save to .env fails** | Run the app from the repo root (folder that contains `backend/` and `run_local.py`). Ensure the folder is writable. |
| **SMTP / login errors** | Confirm App Password, 2FA on the mail account, and that `SENDER_EMAIL` matches the account that owns the app password. |
| **Credentials not pre-filling** | Confirm you are on `local-deployment`, `.env` exists in the repo root, and you restarted the server after saving. |

---

## Security (local branch only)

- Run this branch only on **your own PC** (`127.0.0.1`).
- Do **not** deploy `local-deployment` to a public server with real keys in `.env`.
- For shared/cloud deployment with zero key storage on disk, use **`main`** and [DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md).
