import asyncio
from datetime import datetime, timezone
from .database import SessionLocal
from .models import DeviceState
from .alert_engine import send_alert
from .utils import tprint, C

CHECK_INTERVAL = 10   # seconds between scans
TIMEOUT        = 120  # seconds of silence before alert


async def monitor_silence():
    tprint(f"{C.CYAN}{C.BOLD}[SYSTEM] Silence monitor started (checks every {CHECK_INTERVAL}s, timeout={TIMEOUT}s){C.RESET}")
    while True:
        await asyncio.sleep(CHECK_INTERVAL)   # sleep FIRST so first readings arrive
        db = SessionLocal()
        try:
            devices = db.query(DeviceState).all()
            now     = datetime.now(timezone.utc)

            for d in devices:
                if not d.last_seen:
                    continue

                # Parse ISO-8601 string — handle both Z and +00:00 suffix
                try:
                    last_seen = datetime.fromisoformat(d.last_seen.replace("Z", "+00:00"))
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                except Exception as e:
                    tprint(f"{C.RED}[SYSTEM ERROR] Bad last_seen for Device {d.device_id}: {e}{C.RESET}")
                    continue

                diff = (now - last_seen).total_seconds()

                if diff > TIMEOUT:
                    # ── Device is SILENT ──────────────────────────────────────
                    if d.state != "SILENT":
                        tprint(
                            f"{C.YELLOW}{C.BOLD}[SYSTEM] Device {d.device_id} SILENT "
                            f"(last seen {diff:.0f}s ago > {TIMEOUT}s threshold){C.RESET}"
                        )
                        # Reset streaks so stale counters don't cause false alert on return
                        d.temp_streak     = 0
                        d.vib_streak      = 0
                        d.last_alert_type = "SILENT"
                        d.state           = "SILENT"
                        send_alert(db, d.device_id, "SILENT", "TRIGGERED")

                else:
                    # ── Device last_seen is fresh ─────────────────────────────
                    if d.state == "SILENT":
                        # Race condition guard:
                        # process_reading() normally handles SILENT→NORMAL and
                        # sends RESOLVED.  But if the scheduler sees fresh last_seen
                        # while state is still SILENT (e.g. reading came in between
                        # DB sessions), resolve it here too so it doesn't stay stuck.
                        tprint(
                            f"{C.GREEN}{C.BOLD}[SYSTEM] Device {d.device_id} back online "
                            f"(last seen {diff:.0f}s ago — scheduler clearing stale SILENT){C.RESET}"
                        )
                        send_alert(db, d.device_id, "SILENT", "RESOLVED")
                        d.state = "NORMAL"

            db.commit()
        except Exception as e:
            tprint(f"{C.RED}[SYSTEM ERROR] Silence monitor loop crashed: {e}{C.RESET}")
            import traceback
            tprint(f"{C.RED}{traceback.format_exc()}{C.RESET}")
        finally:
            db.close()