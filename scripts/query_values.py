import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
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


def q(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def main():
    conn = connect()

    print("=== TAX RATE NAMES ===")
    for r in q(conn, "SELECT DISTINCT taxRateName FROM so WHERE taxRateName IS NOT NULL AND taxRateName != '' ORDER BY taxRateName"):
        print(f"  {r[0]}")

    print("\n=== CARRIER NAMES (via carrier table) ===")
    for r in q(conn, "SELECT DISTINCT c.name FROM carrier c INNER JOIN so ON c.id = so.carrierId ORDER BY c.name"):
        print(f"  {r[0]}")

    print("\n=== CARRIER SERVICE NAMES ===")
    for r in q(conn, "SELECT DISTINCT cs.name FROM carrierservice cs INNER JOIN so ON cs.id = so.carrierServiceId ORDER BY cs.name"):
        print(f"  {r[0]}")

    print("\n=== LOCATION GROUP NAMES ===")
    for r in q(conn, "SELECT DISTINCT lg.name FROM locationgroup lg INNER JOIN so ON lg.id = so.locationGroupId ORDER BY lg.name"):
        print(f"  {r[0]}")

    print("\n=== UOM VALUES ===")
    for r in q(conn, "SELECT DISTINCT uom.name FROM uom INNER JOIN soitem ON uom.id = soitem.uomId ORDER BY uom.name"):
        print(f"  {r[0]}")

    print("\n=== SOITEM TYPE IDs + NAMES ===")
    for r in q(conn, "SELECT DISTINCT sot.id, sot.name FROM soitemtype sot ORDER BY sot.id"):
        print(f"  {r[0]} = {r[1]}")

    print("\n=== TAX CODES (via taxrate table) ===")
    for r in q(conn, "SELECT DISTINCT tr.name FROM taxrate tr INNER JOIN soitem si ON tr.id = si.taxId ORDER BY tr.name"):
        print(f"  {r[0]}")

    print("\n=== SHIPPING TERMS ===")
    for r in q(conn, "SELECT DISTINCT st.name FROM shipterms st INNER JOIN so ON st.id = so.shipTermsId ORDER BY st.name"):
        print(f"  {r[0]}")

    print("\n=== PAYMENT TERMS ===")
    for r in q(conn, "SELECT DISTINCT pt.name FROM paymentterms pt INNER JOIN so ON pt.id = so.paymentTermsId ORDER BY pt.name"):
        print(f"  {r[0]}")

    print("\n=== FOB VALUES ===")
    for r in q(conn, "SELECT DISTINCT fob.name FROM fobpoint fob INNER JOIN so ON fob.id = so.fobPointId ORDER BY fob.name"):
        print(f"  {r[0]}")

    print("\n=== SALESMAN VALUES ===")
    for r in q(conn, "SELECT DISTINCT salesman FROM so WHERE salesman IS NOT NULL AND salesman != '' ORDER BY salesman"):
        print(f"  {r[0]}")

    print("\n=== STATUS IDs + NAMES ===")
    for r in q(conn, "SELECT DISTINCT ss.id, ss.name FROM sostatus ss ORDER BY ss.id"):
        print(f"  {r[0]} = {r[1]}")

    print("\n=== CUSTOM FIELDS ON SO ===")
    rows = q(conn, "SELECT DISTINCT customFields FROM so WHERE customFields IS NOT NULL LIMIT 1")
    if rows:
        import json
        cf = json.loads(rows[0][0])
        for k, v in cf.items():
            print(f"  CF-{v['name']} (id={k}, type={v['type']})")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"database query failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from None