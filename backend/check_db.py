import sqlite3

def check_db():
    conn = sqlite3.connect("factory.db")
    cursor = conn.cursor()
    
    print("\n--- Device States ---")
    cursor.execute("SELECT * FROM device_state")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
        
    print("\n--- Recent Telemetry (Last 5) ---")
    cursor.execute("SELECT * FROM telemetry ORDER BY timestamp DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    print("\n--- Recent Alerts (Last 5) ---")
    cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
        
    conn.close()

if __name__ == "__main__":
    check_db()
