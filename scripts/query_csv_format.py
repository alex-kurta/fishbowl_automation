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

    print("=== SO STATUS DISTRIBUTION ===")
    for r in q(conn, "SELECT statusId, COUNT(*) FROM so GROUP BY statusId ORDER BY statusId"):
        print(f"  statusId={r[0]} count={r[1]}")

    print("\n=== TAX RATE USAGE (top 10) ===")
    for r in q(conn, "SELECT taxRateName, COUNT(*) FROM so WHERE taxRateName IS NOT NULL AND taxRateName != '' GROUP BY taxRateName ORDER BY COUNT(*) DESC LIMIT 10"):
        print(f"  {r[0]:30} count={r[1]}")

    print("\n=== TAX RATE FOR SPRINGFIELD ADDRESSES ===")
    for r in q(conn, "SELECT billToCity, taxRateName, COUNT(*) FROM so WHERE billToCity LIKE '%%Springfield%%' GROUP BY billToCity, taxRateName ORDER BY COUNT(*) DESC LIMIT 10"):
        print(f"  city={r[0]:20} taxRate={r[1]:30} count={r[2]}")

    print("\n=== KIT ITEMS (soitemtype 80) ===")
    for r in q(conn, "SELECT si.productNum, si.description, si.typeId, si.showItemFlag, si.unitPrice FROM soitem si WHERE si.typeId = 80 LIMIT 10"):
        print(f"  sku={r[0]:15} desc={r[1]:40} type={r[2]} show={r[3]} price={r[4]}")

    print("\n=== KIT COMPONENTS (showItemFlag=0, unitPrice=0) ===")
    for r in q(conn, "SELECT si.productNum, si.description, si.typeId, si.showItemFlag, si.unitPrice FROM soitem si WHERE si.showItemFlag = 0 AND si.unitPrice = 0 LIMIT 10"):
        print(f"  sku={r[0]:15} desc={r[1]:40} type={r[2]} show={r[3]} price={r[4]}")

    print("\n=== ORDER DATE SCHEDULED (FulfillmentDate) ===")
    for r in q(conn, "SELECT s.num, s.dateCreated, s.dateFirstShip FROM so s ORDER BY s.id DESC LIMIT 5"):
        print(f"  SO#{r[0]} created={r[1]} firstShip={r[2]}")

    print("\n=== SO HEADER LINE FORMAT (checking trailing commas) ===")
    for r in q(conn, "SELECT customFields FROM so WHERE customFields IS NOT NULL LIMIT 1"):
        import json
        cf = json.loads(r[0])
        print(f"  Custom fields count: {len(cf)}")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"database query failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from None