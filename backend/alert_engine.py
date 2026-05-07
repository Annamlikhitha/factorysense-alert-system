from datetime import datetime, timezone
from .utils import send_whatsapp, tprint, C
from .crud import log_alert

# ─── Thresholds ────────────────────────────────────────────────────────────────
TEMP_THRESHOLD = 75     # °C — 3 consecutive readings triggers alert
VIB_THRESHOLD  = 2.5   # g  — 5 consecutive readings triggers alert


def _separator():
    tprint(f"{C.DIM}{'─' * 60}{C.RESET}")


def send_alert(db, device_id, alert_type, status):
    """Fire an alert: print to terminal + WhatsApp + DB audit log."""
    emoji  = "🚨" if status == "TRIGGERED" else "✅"
    color  = C.RED if status == "TRIGGERED" else C.GREEN
    msg    = f"{emoji} Device {device_id} | {alert_type} | {status}"

    _separator()
    tprint(f"{color}{C.BOLD}[ALERT] {msg}{C.RESET}")
    _separator()

    cooldown_key    = f"{device_id}_{alert_type}"
    bypass_cooldown = (status == "RESOLVED")
    send_whatsapp(msg, cooldown_key, bypass_cooldown=bypass_cooldown)

    log_alert(db, device_id, alert_type, status, datetime.now(timezone.utc).isoformat())


# ─── Helper: normalise state name → human alert type string ───────────────────
_STATE_TO_ALERT = {
    "TEMP_ALERT": "TEMPERATURE",
    "VIB_ALERT":  "VIBRATION",
    "SILENT":     "SILENT",
}


def process_reading(db, device, temp, vib, timestamp):
    """
    Core alert state machine.

    States:  NORMAL | TEMP_ALERT | VIB_ALERT | BOTH_ALERT | SILENT

    Rules
    ─────
    • Temp alert fires after 3 consecutive readings > TEMP_THRESHOLD.
    • Vib  alert fires after 5 consecutive readings > VIB_THRESHOLD.
    • Both can be active at the same time  → state = BOTH_ALERT.
    • Any state change sends the appropriate TRIGGERED / RESOLVED messages.
    • SILENT is cleared here when a new reading arrives; RESOLVED is always sent.
    • Deduplication: identical old_state == new_state suppresses duplicate alerts.
    """

    # Always stamp last_seen with real receive time (not stale device clock)
    device.last_seen = datetime.now(timezone.utc).isoformat()

    # ── Update streak counters ─────────────────────────────────────────────────
    if temp > TEMP_THRESHOLD:
        device.temp_streak = (device.temp_streak or 0) + 1
    else:
        device.temp_streak = 0

    if vib > VIB_THRESHOLD:
        device.vib_streak = (device.vib_streak or 0) + 1
    else:
        device.vib_streak = 0

    temp_alert = device.temp_streak >= 3
    vib_alert  = device.vib_streak  >= 5

    tprint(
        f"{C.DIM}[DEBUG] Device {device.device_id} | "
        f"Temp:{temp}°C (thresh:{TEMP_THRESHOLD}) Vib:{vib}g (thresh:{VIB_THRESHOLD}) | "
        f"TempStreak:{device.temp_streak}/3  VibStreak:{device.vib_streak}/5  "
        f"temp_alert={temp_alert}  vib_alert={vib_alert}{C.RESET}"
    )

    # ── Determine new state ────────────────────────────────────────────────────
    if temp_alert and vib_alert:
        new_state = "BOTH_ALERT"
    elif temp_alert:
        new_state = "TEMP_ALERT"
    elif vib_alert:
        new_state = "VIB_ALERT"
    else:
        new_state = "NORMAL"

    old_state = device.state or "NORMAL"

    tprint(
        f"{C.DIM}[STATE] Device {device.device_id}: {old_state} → {new_state}{C.RESET}"
    )

    # ── State-machine transitions ──────────────────────────────────────────────
    if old_state == new_state:
        # No change — suppress duplicate alert
        tprint(
            f"{C.DIM}[DEDUP]  Device {device.device_id} still in {old_state} — suppressing alert{C.RESET}"
        )
        db.commit()
        return

    # ── Step 1: If coming back from SILENT, always resolve SILENT first ────────
    if old_state == "SILENT":
        tprint(
            f"{C.YELLOW}{C.BOLD}[STATE]  Device {device.device_id}: "
            f"SILENT → {new_state} (device back online){C.RESET}"
        )
        send_alert(db, device.device_id, "SILENT", "RESOLVED")
        # Streaks were reset when SILENT was set — nothing stale to clear.
        # After resolving SILENT, treat old_state as NORMAL for further logic.
        old_state = "NORMAL"

    # ── Step 2: Resolve any alerts that are no longer active ──────────────────
    # Figure out which alerts were active in old_state
    old_temp = old_state in ("TEMP_ALERT", "BOTH_ALERT")
    old_vib  = old_state in ("VIB_ALERT",  "BOTH_ALERT")

    # Figure out which alerts are active in new_state
    new_temp = new_state in ("TEMP_ALERT", "BOTH_ALERT")
    new_vib  = new_state in ("VIB_ALERT",  "BOTH_ALERT")

    # Send RESOLVED for alerts that dropped off
    if old_temp and not new_temp:
        tprint(
            f"{C.GREEN}{C.BOLD}[STATE]  Device {device.device_id}: "
            f"TEMPERATURE resolved{C.RESET}"
        )
        send_alert(db, device.device_id, "TEMPERATURE", "RESOLVED")

    if old_vib and not new_vib:
        tprint(
            f"{C.GREEN}{C.BOLD}[STATE]  Device {device.device_id}: "
            f"VIBRATION resolved{C.RESET}"
        )
        send_alert(db, device.device_id, "VIBRATION", "RESOLVED")

    # ── Step 3: Trigger new alerts that weren't active before ─────────────────
    if new_temp and not old_temp:
        tprint(
            f"{C.RED}{C.BOLD}[STATE]  Device {device.device_id}: "
            f"TEMPERATURE triggered{C.RESET}"
        )
        send_alert(db, device.device_id, "TEMPERATURE", "TRIGGERED")

    if new_vib and not old_vib:
        tprint(
            f"{C.RED}{C.BOLD}[STATE]  Device {device.device_id}: "
            f"VIBRATION triggered{C.RESET}"
        )
        send_alert(db, device.device_id, "VIBRATION", "TRIGGERED")

    # ── Commit new state ───────────────────────────────────────────────────────
    device.state = new_state
    # Track last active alert type for RESOLVED fallback (used by scheduler)
    if new_state != "NORMAL":
        device.last_alert_type = new_state

    db.commit()