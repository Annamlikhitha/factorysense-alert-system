# FactorySense Alert Pipeline

A robust, production-ready IoT telemetry and alerting backend designed for real-time sensor monitoring. FactorySense ingests industrial sensor telemetry (temperature and vibration), applies state-machine-driven rules to detect anomalies, and automatically dispatches alerts via WhatsApp using Twilio.

## 🚀 Features

- **Real-Time Data Ingestion:** Fast and scalable telemetry ingestion using FastAPI.
- **State-Machine Alert Engine:** Tracks device status anomalies and prevents duplicate (spurious) alerts using streak-based thresholding.
- **WhatsApp Integration:** Instant mobile notifications powered by Twilio. Includes smart cooldown logic to avoid alert fatigue.
- **Silence Monitoring:** Background scheduler continuously audits device activity and flags sensors that have stopped reporting (silent failures).
- **Audit Logging:** Every alert is permanently recorded in a SQLite database for auditing and compliance.
- **Sensor Simulator:** Includes a built-in multi-threaded simulator to generate realistic test scenarios (normal states, temperature spikes, vibration spikes, and silence).

## 📂 Project Structure

```text
factorysense-alert-pipeline/
│
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── database.py          # SQLAlchemy engine & session setup
│   ├── models.py            # SQLite Database tables definition
│   ├── schemas.py           # Pydantic models for data validation
│   ├── crud.py              # Database operations
│   ├── alert_engine.py      # Core alerting and state transition logic
│   ├── scheduler.py         # Background daemon for detecting silent devices
│   ├── simulator.py         # Test script simulating various sensor states
│   ├── utils.py             # WhatsApp Twilio client and thread-safe helpers
│   ├── .env.example         # Example environment variables file
│   └── .gitignore           # Python specific ignore rules
│
├── requirements.txt         # Project dependencies
├── DECISIONS.md             # Architecture decisions and documentation
└── .gitignore               # Root ignore rules for sensitive files/caches
```

## 🛠️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/Annamlikhitha/factorysense-alert-system.git
cd factorysense-alert-system
```

### 2. Install dependencies
Ensure you have Python 3 installed.
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Inside the `backend/` directory, create a `.env` file based on `.env.example`:
```bash
cd backend
cp .env.example .env
```
Update `.env` with your Twilio credentials and target WhatsApp number:
```env
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=whatsapp:+91xxxxxxxxxx
ALERT_COOLDOWN=60
```

### 4. Run the Backend API Server
Start the FastAPI server (it automatically handles DB migration and starts the silence monitor).
```bash
uvicorn main:app --reload
```

### 5. Run the Simulator (In a new terminal)
Test the pipeline by running the provided simulator. It simulates 3 devices (2 normal, 1 going through various stress states).
```bash
cd backend
python simulator.py
```

## 📊 Endpoints

- `POST /telemetry`: Ingests sensor data.
- `GET /devices`: Lists all known devices and their current states.
- `GET /devices/{device_id}/status`: Gets the state and the last 50 readings of a specific device.
- `GET /alerts`: Retrieves the recent alert history.
