import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pipeline.config import ROOT

load_dotenv(ROOT / ".env")

import pymysql

print("=== CONNECTION DIAGNOSTIC ===")
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "3305")
user = os.getenv("DB_USERNAME")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME", "fishbowl_demo")

print(f"host: {host}")
print(f"port: {port}")
print(f"user: {user if user else '(not set)'}")
print(f"password: {'(set)' if password else '(not set)'}")
print(f"database: {database}")

try:
    conn = pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
    )
    print("connection: OK")
    conn.close()
except pymysql.err.OperationalError as e:
    code, msg = e.args
    print(f"connection failed: OperationalError code={code}")
    if code == 1045:
        print("  -> access denied (bad user/password)")
    elif code == 2003:
        print("  -> can't connect to server (wrong host/port or MySQL not running)")
    elif code == 1049:
        print("  -> unknown database")
    else:
        print(f"  -> {msg}")
except Exception as e:
    print(f"connection failed: {type(e).__name__}: {e}")