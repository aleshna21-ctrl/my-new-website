import os
import re
import sys
import json
import ssl
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = r"C:\Users\alesh\jev-workspace\gtm-research"
if not os.path.isdir(TARGET_DIR):
    TARGET_DIR = str(BASE_DIR)
else:
    try:
        os.chdir(TARGET_DIR)
    except Exception:
        pass

DIODE_PATH = Path(r"C:\Users\alesh\jev-workspace\notification-outbox\metadata_outbox.json")
if not DIODE_PATH.exists():
    DIODE_PATH = BASE_DIR / "data" / "metadata_outbox.json"

ARCHIVE_PATH = Path(r"C:\Users\alesh\jev-workspace\notification-outbox\metadata_outbox.archive.json")
if not ARCHIVE_PATH.exists():
    ARCHIVE_PATH = BASE_DIR / "data" / "metadata_outbox.archive.json"

DEFAULT_RECIPIENT = "aleshna21@gmail.com"
SMTP_HOST = "smtp.gmail.com"

def get_credentials():
    sender = os.environ.get("GMAIL_SENDER", DEFAULT_RECIPIENT)
    password = os.environ.get("GMAIL_APP_PASSWORD")
    
    # Read from local .env if available
    env_file = Path(TARGET_DIR) / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GMAIL_APP_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("GMAIL_SENDER="):
                sender = line.split("=", 1)[1].strip().strip('"').strip("'")

    # Read from smtp_config.json if not in env
    config_file = Path(TARGET_DIR) / "smtp_config.json"
    if not password and config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            password = cfg.get("smtp_pass")
            sender = cfg.get("smtp_user", sender)
        except Exception:
            pass
                
    if not password:
        print("[ERROR] GMAIL_APP_PASSWORD not found in environment, .env, or smtp_config.json.")
        return sender.strip() if sender else None, None
        
    # Google App Passwords must be exactly 16 alphanumeric characters without spaces
    password = password.replace(" ", "").strip()
    return sender.strip(), password

def assert_zero_pii_and_figures(events: list) -> None:
    payload_str = json.dumps(events)
    if re.search(r'[\$€£]|USD|\b\d+\.\d{2}\b', payload_str):
        raise ValueError("CRITICAL POLICY VIOLATION: Financial figures or currency detected in diode payload!")
    for ev in events:
        for k, v in ev.items():
            if "@" in str(v):
                raise ValueError(f"CRITICAL POLICY VIOLATION: Email address detected in event field '{k}': {v}")

def dispatch_email(sender: str, password: str, recipient: str, msg: MIMEMultipart) -> bool:
    context = ssl.create_default_context()
    
    # Attempt 1: Port 587 with STARTTLS (Most reliable across firewalls/ISPs)
    print(f"[*] Attempting dispatch via {SMTP_HOST}:587 (STARTTLS)...")
    try:
        with smtplib.SMTP(SMTP_HOST, 587, timeout=25) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        print(f"[SUCCESS] Dispatched via Port 587 to {recipient}.")
        return True
    except smtplib.SMTPAuthenticationError as auth_err:
        print(f"[ERROR] Gmail Authentication failed: {auth_err}")
        print("[TIP] Ensure 2-Step Verification is ON and you generated a 16-character 'App Password' (not your main Google account password).")
        return False
    except Exception as exc_587:
        print(f"[!] Port 587 failed: {exc_587}. Falling back to Port 465 (SSL)...")
        
    # Attempt 2: Port 465 with direct SSL
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465, context=context, timeout=25) as server:
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        print(f"[SUCCESS] Dispatched via Port 465 to {recipient}.")
        return True
    except Exception as exc_465:
        print(f"[ERROR] Both Port 587 and 465 failed: {exc_465}")
        return False

def relay_metadata_outbox():
    if not DIODE_PATH.exists():
        print(f"[*] Diode outbox {DIODE_PATH} does not exist.")
        return

    try:
        events = json.loads(DIODE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Could not parse metadata_outbox.json: {exc}")
        return

    if not isinstance(events, list) or len(events) == 0:
        print("[*] No pending state transitions in metadata_outbox.json to relay.")
        return

    print(f"[*] Found {len(events)} pending transition event(s). Validating zero-PII diode policy...")
    assert_zero_pii_and_figures(events)
    print("[+] Zero-PII and zero-financial policy verified.")

    sender_email, app_password = get_credentials()
    if not app_password:
        return

    subject = f"[JEV Alert Relay] {len(events)} State Transition(s) Bundled"
    
    body_lines = [
        "JEV ENGINE METADATA DIODE — STATE TRANSITION RELAY",
        f"Relayed At: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Bundled Transitions: {len(events)}",
        "=" * 60,
        ""
    ]
    for idx, ev in enumerate(events, 1):
        body_lines.append(
            f"{idx:02d}. [{ev.get('timestamp_utc', 'N/A')}] Job: {ev.get('job_id', 'UNKNOWN')} "
            f"({ev.get('job_type', 'unknown')}) -> {ev.get('from_state', '?')} => {ev.get('to_state', '?')} "
            f"[Event: {ev.get('event_id', 'none')}]"
        )
    body_lines.extend([
        "",
        "=" * 60,
        "Diode Policy: Strictly 0 PII, 0 Financial Figures, 1-Way Loopback Outbound."
    ])
    
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = DEFAULT_RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(body_lines), "plain", "utf-8"))

    success = dispatch_email(sender_email, app_password, DEFAULT_RECIPIENT, msg)
    if success:
        archived_events = []
        if ARCHIVE_PATH.exists():
            try:
                archived_events = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
                if not isinstance(archived_events, list):
                    archived_events = []
            except Exception:
                archived_events = []
        archived_events.extend(events)
        ARCHIVE_PATH.write_text(json.dumps(archived_events, indent=2), encoding="utf-8")
        DIODE_PATH.write_text("[]", encoding="utf-8")
        print(f"[+] Archived {len(events)} event(s) and cleared {DIODE_PATH.name}.")

    result = {
        "status": "ok" if success else "pending",
        "events_bundled": len(events),
        "dispatched": success,
        "recipient": DEFAULT_RECIPIENT,
        "pii_verified": True,
        "archived": success,
        "message": f"Dispatched {len(events)} events to {DEFAULT_RECIPIENT} via Gmail SMTP." if success else "SMTP relay attempted; credentials or network pending."
    }
    return result

def dispatch_pending_alerts():
    return relay_metadata_outbox()

def dispatch_bundled_alerts():
    return relay_metadata_outbox()

if __name__ == "__main__":
    relay_metadata_outbox()
