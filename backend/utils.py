from twilio.rest import Client
import os
import threading
from dotenv import load_dotenv
from datetime import datetime, timezone
import logging

load_dotenv()

# Silence Twilio's verbose HTTP request/response logger
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)

# ─── Thread-safe print ─────────────────────────────────────────────────────────
_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    """Thread-safe print so simulator threads don't garble output."""
    with _print_lock:
        print(*args, **kwargs)

# ─── Colors ────────────────────────────────────────────────────────────────────
class C:
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    DIM    = '\033[90m'
    RESET  = '\033[0m'
    BOLD   = '\033[1m'

# ─── Twilio setup ──────────────────────────────────────────────────────────────
_sid   = os.getenv("TWILIO_ACCOUNT_SID")
_token = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(_sid, _token) if _sid and _token else None

# ─── Cooldown (keyed on device+type ONLY, NOT status) ─────────────────────────
# We track TRIGGERED time only.  RESOLVED always bypasses and does NOT
# reset the cooldown clock — so a fresh TRIGGERED can fire immediately
# after a RESOLVED without waiting the full cooldown window.

last_sent: dict[str, datetime] = {}
COOLDOWN = int(os.getenv("ALERT_COOLDOWN", 60))


def send_whatsapp(message: str, key: str, bypass_cooldown: bool = False):
    """
    Send a WhatsApp message via Twilio.
    key            — cooldown key, format: "{device_id}_{alert_type}"
    bypass_cooldown — set True for RESOLVED messages so they always go through.
                      RESOLVED does NOT update last_sent so the next TRIGGERED
                      is not blocked by the cooldown window.
    """
    if client is None:
        tprint(f"{C.DIM}[WHATSAPP] No Twilio creds — skipping: {message}{C.RESET}")
        return

    now = datetime.now(timezone.utc)

    if not bypass_cooldown:
        if key in last_sent and (now - last_sent[key]).total_seconds() < COOLDOWN:
            remaining = COOLDOWN - (now - last_sent[key]).total_seconds()
            tprint(f"{C.DIM}[WHATSAPP] Cooldown active for {key} ({remaining:.0f}s left) — skipping{C.RESET}")
            return

    recipients = [x.strip() for x in os.getenv("WHATSAPP_TO", "").split(",") if x.strip()]
    from_number = os.getenv("WHATSAPP_FROM", "whatsapp:+14155238886")

    if not recipients:
        tprint(f"{C.YELLOW}[WHATSAPP] WHATSAPP_TO is empty — set it in .env{C.RESET}")
        return

    success = False
    for to in recipients:
        try:
            client.messages.create(from_=from_number, body=message, to=to)
            tprint(f"{C.GREEN}[WHATSAPP ✓] Sent to {to}: {message}{C.RESET}")
            success = True
        except Exception as e:
            tprint(f"{C.RED}[WHATSAPP ✗] Failed to send to {to}: {e}{C.RESET}")

    # Only update last_sent for TRIGGERED messages (bypass_cooldown=False).
    # This way RESOLVED doesn't reset the cooldown window, allowing the next
    # TRIGGERED to fire immediately even if sent shortly after a RESOLVED.
    if not bypass_cooldown and success:
        last_sent[key] = now