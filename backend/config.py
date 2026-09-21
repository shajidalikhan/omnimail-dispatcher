import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Preset SMTP Dispatchers
DISPATCHER_PRESETS = {
    "gmail": {
        "name": "Gmail (Google)",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": True,
        "instructions": "Use a 16-character Google App Password (not your normal Gmail password). Enable 2FA on your Google Account, then go to Account > Security > App Passwords."
    },
    "outlook": {
        "name": "Outlook / Office 365",
        "smtp_server": "smtp.office365.com",
        "smtp_port": 587,
        "use_tls": True,
        "instructions": "Use your Microsoft 365 or Outlook.com email and an App Password or SMTP-enabled account password."
    },
    "yahoo": {
        "name": "Yahoo Mail",
        "smtp_server": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "use_tls": True,
        "instructions": "Generate an App Password in Yahoo Account Security settings."
    },
    "custom": {
        "name": "Custom / Institutional SMTP",
        "smtp_server": "",
        "smtp_port": 587,
        "use_tls": True,
        "instructions": "Enter your university or organization's SMTP server host and port."
    },
    "dry_run": {
        "name": "Dry Run / Simulation (Safe Mode)",
        "smtp_server": "localhost",
        "smtp_port": 0,
        "use_tls": False,
        "instructions": "Simulates dispatch without contacting real mail servers. Perfect for verifying templates, variables, and output reports safely."
    }
}

def save_credentials_to_env(dispatcher_type: str, sender_email: str, sender_name: str, password_or_key: str, smtp_server: str = "", smtp_port: int = 587, use_tls: bool = True):
    """Save user credentials and dispatcher choice locally into .env for convenience."""
    lines = [
        f"DEFAULT_DISPATCHER={dispatcher_type}\n",
        f"SENDER_EMAIL={sender_email}\n",
        f"SENDER_NAME={sender_name}\n",
        f"SENDER_KEY={password_or_key}\n",
        f"CUSTOM_SMTP_SERVER={smtp_server}\n",
        f"CUSTOM_SMTP_PORT={smtp_port}\n",
        f"CUSTOM_USE_TLS={str(use_tls).lower()}\n",
    ]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

def get_auth_settings():
    """Retrieve HTTP Basic Auth configuration."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    auth_enabled_str = os.getenv("AUTH_ENABLED", "").lower()
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "")
    
    # Enabled if explicitly set to true or if ADMIN_PASSWORD is set
    is_enabled = auth_enabled_str in ("1", "true", "yes") or (bool(admin_pass) and auth_enabled_str != "false")
    return {
        "auth_enabled": is_enabled,
        "username": admin_user,
        "password": admin_pass or "admin123"
    }

def get_saved_credentials():
    """Retrieve saved defaults without sensitive keys (Zero-Retention Policy)."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    return {
        "dispatcher_type": os.getenv("DEFAULT_DISPATCHER", "gmail"),
        "sender_email": os.getenv("SENDER_EMAIL", ""),
        "sender_name": os.getenv("SENDER_NAME", ""),
        "sender_key": "",  # NEVER return stored passwords/keys to client (Zero-Retention)
        "custom_smtp_server": os.getenv("CUSTOM_SMTP_SERVER", ""),
        "custom_smtp_port": int(os.getenv("CUSTOM_SMTP_PORT", "587")),
        "custom_use_tls": os.getenv("CUSTOM_USE_TLS", "true").lower() == "true",
    }


