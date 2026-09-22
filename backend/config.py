import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# ── DEPLOYMENT MODE CONFIGURATION ────────────────────────────────────────────
# When LOCAL_MODE is enabled (e.g. launched via run_local.py or start_local.bat),
# credentials including the mail key are persisted to the local .env file so users
# on their personal machines do not have to re-enter them on every launch.
# When LOCAL_MODE is false (e.g. Cloud / Render / Multi-user hosting), the key is
# NEVER written to disk or sent to the client (Strict Zero-Retention Security).
def is_local_mode() -> bool:
    """Check if server is running in single-machine local mode."""
    return os.getenv("LOCAL_MODE", "false").strip().lower() in ("true", "1", "yes")

LOCAL_MODE = is_local_mode()

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


_CREDENTIAL_KEYS = {
    "DEFAULT_DISPATCHER",
    "SENDER_EMAIL",
    "SENDER_NAME",
    "SENDER_KEY",
    "CUSTOM_SMTP_SERVER",
    "CUSTOM_SMTP_PORT",
    "CUSTOM_USE_TLS",
}


def save_credentials_to_env(
    dispatcher_type: str,
    sender_email: str,
    sender_name: str,
    password_or_key: str,
    smtp_server: str = "",
    smtp_port: int = 587,
    use_tls: bool = True
):
    """
    LOCAL MODE: Persist all credentials including the key to the local .env file.
    Allows the user to avoid re-entering details on every server restart.
    Safe only because this server runs exclusively on the user's own machine.
    """
    updates = {
        "DEFAULT_DISPATCHER": dispatcher_type,
        "SENDER_EMAIL": sender_email,
        "SENDER_NAME": sender_name,
        "SENDER_KEY": password_or_key if LOCAL_MODE else "",
        "CUSTOM_SMTP_SERVER": smtp_server,
        "CUSTOM_SMTP_PORT": str(smtp_port),
        "CUSTOM_USE_TLS": str(use_tls).lower(),
    }

    preserved: list[str] = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#"):
                preserved.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key not in _CREDENTIAL_KEYS:
                preserved.append(line)

    lines = preserved[:]
    if preserved:
        lines.append("")
    for key in (
        "DEFAULT_DISPATCHER",
        "SENDER_EMAIL",
        "SENDER_NAME",
        "SENDER_KEY",
        "CUSTOM_SMTP_SERVER",
        "CUSTOM_SMTP_PORT",
        "CUSTOM_USE_TLS",
    ):
        lines.append(f"{key}={updates[key]}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Reload env immediately so changes take effect in the same process
    load_dotenv(ENV_PATH, override=True)


def get_auth_settings():
    """Retrieve HTTP Basic Auth config (disabled by default in local mode)."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    auth_enabled_str = os.getenv("AUTH_ENABLED", "").lower()
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "")

    # Disabled by default in local mode unless explicitly configured in .env
    is_enabled = auth_enabled_str in ("1", "true", "yes") or (
        bool(admin_pass) and auth_enabled_str != "false"
    )
    return {
        "auth_enabled": is_enabled,
        "username": admin_user,
        "password": admin_pass or "admin123"
    }


def get_saved_credentials():
    """
    Return saved credentials from .env.
    In LOCAL_MODE, the key is included so the UI pre-fills it for single-machine convenience.
    In Cloud/Shared mode, the key is NEVER exposed (Zero-Retention Policy).
    """
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    return {
        "dispatcher_type": os.getenv("DEFAULT_DISPATCHER", "gmail"),
        "sender_email": os.getenv("SENDER_EMAIL", ""),
        "sender_name": os.getenv("SENDER_NAME", ""),
        "sender_key": os.getenv("SENDER_KEY", "") if LOCAL_MODE else "",
        "custom_smtp_server": os.getenv("CUSTOM_SMTP_SERVER", ""),
        "custom_smtp_port": int(os.getenv("CUSTOM_SMTP_PORT", "587")),
        "custom_use_tls": os.getenv("CUSTOM_USE_TLS", "true").lower() == "true",
    }
