"""
FactorySense Sensor Simulator
─────────────────────────────
Device 1 → always NORMAL
Device 2 → always NORMAL
Device 3 → cycles through: TEMP SPIKE → NORMAL → VIB SPIKE → NORMAL → SILENT

Run: python simulator.py
"""

import requests
import random
import time
from datetime import datetime, timezone
import threading
import sys

BASE_URL      = "http://127.0.0.1:8000"
READ_INTERVAL = 10      # seconds between readings
SILENT_GAP    = 130     # seconds Device 3 goes silent


# ─── Thread-safe colors ────────────────────────────────────────────────────────
_lock = threading.Lock()

class C:
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    DIM    = '\033[90m'
    RESET  = '\033[0m'
    BOLD   = '\033[1m'


def tprint(*args, **kwargs):
    with _lock:
        print(*args, **kwargs, flush=True)


# ─── Helpers ───────────────────────────────────────────────────────────────────
def get_timestamp():
    return datetime.now(timezone.utc).isoformat()


def send(payload):
    try:
        r = requests.post(f"{BASE_URL}/telemetry", json=payload, timeout=10)
        status_color = C.GREEN if r.status_code == 200 else C.RED
        tprint(
            f"{C.DIM}  ↑ Device {payload['device_id']} | "
            f"T={payload['temperature_c']}°C  V={payload['vibration_g']}g  "
            f"→ {status_color}{r.status_code}{C.DIM}{C.RESET}"
        )
    except requests.exceptions.ConnectionError:
        tprint(f"{C.RED}  [ERROR] Cannot reach {BASE_URL} — is the server running?{C.RESET}")
    except Exception as e:
        tprint(f"{C.RED}  [ERROR] Device {payload['device_id']}: {e}{C.RESET}")


def normal_reading(device_id):
    return {
        "device_id":     device_id,
        "timestamp":     get_timestamp(),
        "temperature_c": round(random.uniform(55, 70), 2),
        "vibration_g":   round(random.uniform(0.5, 1.8), 2),
    }


def temp_spike_reading():
    return {
        "device_id":     "3",
        "timestamp":     get_timestamp(),
        "temperature_c": round(random.uniform(80, 90), 2),   # above 75°C threshold
        "vibration_g":   round(random.uniform(0.5, 1.5), 2),
    }


def vib_spike_reading():
    return {
        "device_id":     "3",
        "timestamp":     get_timestamp(),
        "temperature_c": round(random.uniform(55, 70), 2),
        "vibration_g":   round(random.uniform(3.0, 4.5), 2), # above 2.5g threshold
    }


# ─── Device loops ──────────────────────────────────────────────────────────────
def device_1_loop():
    while True:
        send(normal_reading("1"))
        time.sleep(READ_INTERVAL)


def device_2_loop():
    while True:
        send(normal_reading("2"))
        time.sleep(READ_INTERVAL)


def device_3_loop():
    while True:
        # ── Phase 1: Temperature spike (need 3 consecutive > 75°C) ──────────
        tprint(f"\n{C.RED}{C.BOLD}{'═'*50}")
        tprint(f"  🔥  Device 3 — TEMPERATURE SPIKE PHASE")
        tprint(f"  Sending 3 readings above {75}°C threshold...")
        tprint(f"{'═'*50}{C.RESET}")
        for i in range(3):
            tprint(f"{C.DIM}  Reading {i+1}/3{C.RESET}")
            send(temp_spike_reading())
            if i < 2:
                time.sleep(READ_INTERVAL)

        time.sleep(READ_INTERVAL)

        # ── Phase 2: Back to normal (resolves temp alert) ────────────────────
        tprint(f"\n{C.GREEN}{C.BOLD}{'═'*50}")
        tprint(f"  🟢  Device 3 — RETURNING TO NORMAL")
        tprint(f"{'═'*50}{C.RESET}")
        for i in range(3):
            send(normal_reading("3"))
            time.sleep(READ_INTERVAL)

        # ── Phase 3: Vibration spike (need 5 consecutive > 2.5g) ────────────
        tprint(f"\n{C.YELLOW}{C.BOLD}{'═'*50}")
        tprint(f"  ⚡  Device 3 — VIBRATION SPIKE PHASE")
        tprint(f"  Sending 5 readings above {2.5}g threshold...")
        tprint(f"{'═'*50}{C.RESET}")
        for i in range(5):
            tprint(f"{C.DIM}  Reading {i+1}/5{C.RESET}")
            send(vib_spike_reading())
            if i < 4:
                time.sleep(READ_INTERVAL)

        time.sleep(READ_INTERVAL)

        # ── Phase 4: Back to normal (resolves vib alert) ─────────────────────
        tprint(f"\n{C.GREEN}{C.BOLD}{'═'*50}")
        tprint(f"  🟢  Device 3 — RETURNING TO NORMAL")
        tprint(f"{'═'*50}{C.RESET}")
        for i in range(3):
            send(normal_reading("3"))
            time.sleep(READ_INTERVAL)

        # ── Phase 5: Silent failure ───────────────────────────────────────────
        tprint(f"\n{C.DIM}{C.BOLD}{'═'*50}")
        tprint(f"  💀  Device 3 — GOING SILENT for {SILENT_GAP}s")
        tprint(f"  (Alert fires after 120s of silence)")
        tprint(f"{'═'*50}{C.RESET}")
        time.sleep(SILENT_GAP)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tprint(f"\n{C.CYAN}{C.BOLD}{'═'*50}")
    tprint(f"  🚀  FactorySense Simulator")
    tprint(f"  Target: {BASE_URL}")
    tprint(f"  Devices: 1 (normal), 2 (normal), 3 (stress test)")
    tprint(f"{'═'*50}{C.RESET}\n")

    # Verify server is reachable before starting
    try:
        import requests as req
        req.get(f"{BASE_URL}/docs", timeout=3)
        tprint(f"{C.GREEN}  ✓ Server is reachable{C.RESET}\n")
    except Exception:
        tprint(f"{C.RED}  ✗ WARNING: Cannot reach {BASE_URL} — start the server first!{C.RESET}\n")

    threads = [
        threading.Thread(target=device_1_loop, daemon=True, name="Device-1"),
        threading.Thread(target=device_2_loop, daemon=True, name="Device-2"),
        threading.Thread(target=device_3_loop, daemon=True, name="Device-3"),
    ]

    for t in threads:
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        tprint(f"\n{C.CYAN}[SIMULATOR] Stopped by user.{C.RESET}")
        sys.exit(0)