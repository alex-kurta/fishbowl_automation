import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pipeline.config import ROOT

load_dotenv(ROOT / ".env")

import pymysql

def connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3305")),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "fishbowl_demo"),
        charset="utf8mb4",
    )

def query(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall(), [d[0] for d in cur.description]

def main():
    conn = connect()

    print("=== TABLES IN fishbowl_demo ===")
    rows, cols = query(conn, "SHOW TABLES")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== SO TABLE STRUCTURE ===")
    rows, cols = query(conn, "DESCRIBE `so`")
    for row in rows:
        print(f"  {row[0]:30} {row[1]:30} {row[2]}")

    print("\n=== SOITEM TABLE STRUCTURE ===")
    rows, cols = query(conn, "DESCRIBE `soitem`")
    for row in rows:
        print(f"  {row[0]:30} {row[1]:30} {row[2]}")

    print("\n=== SAMPLE SO ROWS (last 5) ===")
    rows, cols = query(conn, "SELECT * FROM `so` ORDER BY id DESC LIMIT 5")
    print(f"  Columns: {cols}")
    for row in rows:
        print(f"  {row}")

    print("\n=== CUSTOMER NAMES IN SO ===")
    rows, cols = query(conn, "SELECT DISTINCT customerName FROM `so` ORDER BY customerName LIMIT 20")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== SO STATUS VALUES ===")
    rows, cols = query(conn, "SELECT DISTINCT status FROM `so` ORDER BY status")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== TAX RATE NAMES ===")
    rows, cols = query(conn, "SELECT DISTINCT taxRateName FROM `so` ORDER BY taxRateName")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== CARRIER NAMES ===")
    rows, cols = query(conn, "SELECT DISTINCT carrierName FROM `so` ORDER BY carrierName")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== LOCATION GROUP NAMES ===")
    rows, cols = query(conn, "SELECT DISTINCT locationGroupName FROM `so` ORDER BY locationGroupName")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== UOM VALUES IN SOITEM ===")
    rows, cols = query(conn, "SELECT DISTINCT UOM FROM `soitem` ORDER BY UOM")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== SOITEM TYPE IDS ===")
    rows, cols = query(conn, "SELECT DISTINCT itemTypeId FROM `soitem` ORDER BY itemTypeId")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== TAX CODES ===")
    rows, cols = query(conn, "SELECT DISTINCT taxCode FROM `soitem` ORDER BY taxCode")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== SHIPPING TERMS ===")
    rows, cols = query(conn, "SELECT DISTINCT shippingTerms FROM `so` ORDER BY shippingTerms")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== PAYMENT TERMS ===")
    rows, cols = query(conn, "SELECT DISTINCT paymentTerms FROM `so` ORDER BY paymentTerms")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== FOB VALUES ===")
    rows, cols = query(conn, "SELECT DISTINCT FOB FROM `so` ORDER BY FOB")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== CARRIER SERVICES ===")
    rows, cols = query(conn, "SELECT DISTINCT carrierService FROM `so` ORDER BY carrierService")
    for row in rows:
        print(f"  {row[0]}")

    print("\n=== SALESMAN VALUES ===")
    rows, cols = query(conn, "SELECT DISTINCT salesman FROM `so` ORDER BY salesman")
    for row in rows:
        print(f"  {row[0]}")

    conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"database query failed: {type(exc).__name__}")
        raise SystemExit(1) from None