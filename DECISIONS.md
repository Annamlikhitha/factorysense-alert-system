# DECISIONS.md — FactorySense Challenge

## 1. Data Model & Schema Choices

### Tables

| Table | Purpose |
|---|---|
| `telemetry` | Append-only log of every reading. Never mutated after insert. |
| `device_state` | One row per device. Mutable — stores running state for the alert state machine. |
| `alerts` | Append-only audit log of every alert fired. |

### Why this separation?

**`telemetry` is an event log, `device_state` is a state machine.**  
These are different data access patterns. The telemetry table is always
appended to and queried in reverse-time order (last 50 per device). The
device_state table is read and updated on every incoming reading, so it
needs to be a single row per device — not recomputed from the telemetry log
on every request (that would require scanning up to 50 rows on every POST).

### Schema choices

- **`timestamp` stored as ISO-8601 string** rather than SQLite's `DATETIME`
  type. SQLite's type affinity system is permissive but inconsistent.
  ISO-8601 strings sort correctly lexicographically, parse unambiguously
  across Python and any future language, and avoid timezone pitfalls.
  
- **`device_state.temp_streak` / `vib_streak` persisted to DB** rather than
  kept in memory. If the server restarts mid-streak, the streak survives.
  This avoids a class of false-negative bugs (server crashes right before a
  threshold breach, restarts, streak resets to 0, alert never fires).

- **`device_state.last_alert_type`** — stores what type of alert was active
  before a SILENT transition, so the RESOLVED message names the correct
  condition. Without this, we'd have to query the alerts table on every
  resolution.

- **Indexes on `telemetry.device_id`** — the primary access pattern is
  `WHERE device_id = ? ORDER BY id DESC LIMIT 50`. The B-tree index on
  `device_id` makes this O(log n) rather than a full table scan.

---

## 2. Alert State Machine

### States

```
NORMAL → TEMP_ALERT      (3+ consecutive temp > 75°C)
NORMAL → VIB_ALERT       (5+ consecutive vib  > 2.5g)
NORMAL → SILENT          (no reading for > 120s)
TEMP_ALERT → NORMAL      (temp streak resets)
VIB_ALERT  → NORMAL      (vib streak resets)
SILENT     → NORMAL      (reading received)
```

### Deduplication

The state transition **is** the deduplication. An alert fires if and only if
`device.state != new_state`. While the device stays in TEMP_ALERT, every
subsequent reading that still exceeds the threshold produces no alert — the
state is already TEMP_ALERT, so the condition `old_state != new_state` is
false.

When the device returns to NORMAL (streak drops to zero), the condition
fires again and exactly one RESOLVED message is sent.

This logic is **persisted in SQLite**, so it is durable across restarts. An
in-memory flag would reset on restart, causing spurious re-alerts after a
deploy.

### Secondary cooldown (utils.py)

There is also a time-based cooldown in `send_whatsapp()`, keyed on
`(device_id, alert_type)` — **not** on status. This is a secondary safety
net, not the primary dedup. It prevents the state machine from sending a
flood of TRIGGERED messages if there is a bug in the state machine itself
(defensive programming). RESOLVED messages bypass the cooldown and are
always delivered, ensuring the factory owner always knows when a situation
clears.

### State priority

Temperature alert takes priority over vibration if both conditions are met
simultaneously. In practice this is rare, but the choice is explicit and
documented here rather than being an implicit artifact of `elif` ordering.

---

## 3. Silent-Failure Detection

### The challenge

Silence is detected by the **absence** of data. There is no event to hook
into, so we need a proactive background scan.

### Implementation

`scheduler.py` runs an async loop (`asyncio.create_task`) that:

1. Wakes every 10 seconds (`CHECK_INTERVAL`).
2. Queries `device_state` for all known devices.
3. Parses each device's `last_seen` timestamp.
4. If `now - last_seen > 120s` and state != SILENT → fires SILENT TRIGGERED.
5. If state == SILENT and `now - last_seen <= 120s` → fires SILENT RESOLVED.

### Why `await asyncio.sleep(CHECK_INTERVAL)` at the top of the loop?

Sleep-first avoids a false positive on cold start. When the server first
boots, all devices have `last_seen` values from before the restart. If we
scan immediately, every device that hasn't reported in the last 2 minutes
would trigger a spurious SILENT alert, even if those devices are actively
running. Sleeping for 10 seconds gives the first batch of readings a chance
to arrive before we scan.

### Worst-case detection latency

`TIMEOUT (120s) + CHECK_INTERVAL (10s) = 130s`. A device that stops at
second 0 will be detected at second 130 at the latest. This is a
well-understood tradeoff: more frequent polling reduces latency but adds
DB load.

### Streak reset on SILENT

When a device goes SILENT, its `temp_streak` and `vib_streak` counters are
reset to 0. When it comes back online, its streak counts from fresh readings,
not from readings that happened before the silence. This avoids a bug where a
device that was in TEMP_ALERT, went silent, and came back online would
immediately re-trigger a TEMP_ALERT from a stale streak.

---

## 4. Scaling to 1,000 Devices

The current design would need the following changes:

### Storage
- **Replace SQLite with TimescaleDB** (as noted in the spec). SQLite has a
  single-writer lock; at 1,000 devices × 6 req/min = 6,000 writes/minute,
  write contention would become the bottleneck. TimescaleDB's hypertable
  partitioning is designed for exactly this workload.
- **Add a Redis layer** for `device_state`. Reading and writing a single row
  from a hot Redis key is O(1) and avoids DB round trips on every telemetry
  POST. The DB becomes the source of truth for recovery; Redis is the fast
  path.

### Alerting
- **Move alert logic into a message queue** (Celery + Redis or AWS SQS).
  Currently, alert processing happens synchronously inside the HTTP request
  handler. Under load, Twilio API latency would slow down every POST.
  A queue decouples ingestion from alerting.
- **The silence monitor** would need to be distributed (e.g., one worker per
  N devices, or a partitioned cron job). A single async loop scanning 1,000
  device rows every 10 seconds is fine, but it becomes a single point of
  failure.

### API
- **Add pagination** to `GET /devices/{id}/status`. Returning 50 readings is
  fine now; at high volume, this endpoint would need cursor-based pagination.
- **Rate limiting** on `POST /telemetry` to guard against misbehaving devices
  flooding the service.

---

## 5. 48-Hour Tradeoffs

| Decision | Tradeoff |
|---|---|
| SQLite over TimescaleDB | SQLite is zero-config and self-contained. Fine for 3 devices, would need migration at scale. |
| Sync SQLAlchemy over async | Simpler to reason about for this scope. Async SQLAlchemy adds complexity for marginal gain at 3 devices. |
| Single-process deployment | No worker queue, no Redis. Alert processing is synchronous. Acceptable for the demo, not for production. |
| In-process silence monitor | The asyncio task runs in the same process as the API. A crash takes both down. In production, this should be a separate worker. |
| ISO-8601 strings for timestamps | Avoids timezone bugs at the cost of string parsing on every comparison. Acceptable for this scope; a proper TIMESTAMPTZ column would be better in production. |
| WhatsApp Sandbox | The Twilio Sandbox requires the recipient to opt in by sending a join message. In production, a registered WhatsApp Business number would be used. |
176: 
177: ---
178: 
179: ## 6. Live Demo & Deployment
180: 
181: - **Live Backend**: [https://factorysense-alert-system.onrender.com](https://factorysense-alert-system.onrender.com)
182: - **Demo Video**: [https://drive.google.com/file/d/1kuc-4cs8VdOO8I0tAgLP18yYQdhBTPYL/view?usp=sharing](https://drive.google.com/file/d/1kuc-4cs8VdOO8I0tAgLP18yYQdhBTPYL/view?usp=sharing)
