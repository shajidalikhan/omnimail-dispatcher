# Local Deployment Guide (Clone → Run)

Use this guide to run **OmniMail Dispatcher** locally on your personal computer directly from the **`main`** branch. In local mode, your SMTP credentials and App Passwords are saved to your private **`.env`** file so you never have to re-enter them on each launch.

> **Cloud Hosting:** For multi-user hosting on Render with Zero-Retention security (where keys are kept in browser memory only and never saved to disk), see [DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md).

---

## What you need

| Requirement | Notes |
|-------------|--------|
| **Git** | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Python 3.10+** | Check with `python --version` (be sure to check "Add Python to PATH" during install) |
| **Internet** | For package installation and connecting to your SMTP mail provider |

---

## Fast Track (Windows 1-Click Launch)

1. **Clone the repository:**
   ```cmd
   git clone https://github.com/shajidalikhan/omnimail-dispatcher.git
   cd omnimail-dispatcher
   ```
2. **Double-click `start_local.bat`** (or `start_dispatcher.bat`).
3. That's it! It launches the local server and automatically opens your browser at `http://127.0.0.1:8000`.

---

## Step-by-Step Setup (All Platforms)

### Step 1: Clone the repository

```bash
git clone https://github.com/shajidalikhan/omnimail-dispatcher.git
cd omnimail-dispatcher
```

### Step 2: Create a virtual environment (recommended)

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

### Step 3: Install dependencies

With your virtual environment activated:
```bash
pip install -r requirements.txt
```

### Step 4: Run the application

```bash
python run_local.py
```

`run_local.py` automatically sets `LOCAL_MODE=true`, finds an available port (defaults to 8000), starts the server bound strictly to `127.0.0.1`, and launches your default web browser.

To stop the server, press **Ctrl+C** in the terminal window.

---

## Using the Application & Saving Credentials

1. **Step 1 — Dispatcher & Key:**
   - Select your provider (e.g., **Gmail**, **Outlook**, **Custom SMTP**, or **Safe Dry Run**).
   - Enter your Sender Email, Display Name, and 16-character App Password.
   - Click **Save to .env (Local)**.
   - Your credentials are stored in `.env` on your computer. When you restart the app, they will automatically be pre-filled!
2. **Step 2 — Import Recipients:** Upload your Excel (`.xlsx`) or CSV file.
3. **Step 3 — Personalization & Template:** Compose your subject and body using dynamic tags (e.g. `{{Name}}`). Review the live preview and spam score.
4. **Step 4 — Dispatch & Verification:** Set sending delay and launch. Download the delivery verification report when completed.

---

## Updating to the Latest Version

```bash
cd omnimail-dispatcher
git pull origin main
pip install -r requirements.txt
```

Your private `.env` file is excluded in `.gitignore` and remains intact when pulling updates.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **`python` not recognized** | Download Python from [python.org](https://www.python.org/downloads/) and ensure "Add Python to PATH" is checked. |
| **Port 8000 already in use** | `run_local.py` automatically detects occupied ports and switches to the next free port (e.g., 8001). |
| **Missing modules error** | Run `pip install -r requirements.txt`. |
| **SMTP / Authentication errors** | For Gmail, generate a 16-character App Password at [Google Account > Security > App Passwords](https://myaccount.google.com/apppasswords). Normal Google account passwords will be rejected by SMTP. |

---

## Security Architecture

- **Local Mode (`LOCAL_MODE=true`):** Activated by `run_local.py` or `start_local.bat`. Binds only to localhost (`127.0.0.1`). Credentials are saved in `.env` for user convenience.
- **Cloud Mode (`LOCAL_MODE=false`):** Default for production/cloud deployments. Enforces strict **Zero-Retention**: keys are held in volatile browser session memory only and are never saved to server disk or exposed over network APIs.
