import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import DB_CONFIG, SCHEMA_REPORT_DIR
from pipeline.db.client import run_query


def ensure_credentials():
    if not DB_CONFIG["user"] or not DB_CONFIG["password"]:
        raise SystemExit(
            "database credentials missing. Copy .env.example to .env in the project "
            "root and fill in DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME."
        )


def all_tables():
    sql = (
        "SELECT TABLE_NAME, TABLE_ROWS "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s "
        "ORDER BY TABLE_NAME"
    )
    return run_query(sql, (DB_CONFIG["database"],))


def table_columns(table):
    sql = (
        "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION"
    )
    return run_query(sql, (DB_CONFIG["database"], table))


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"wrote {path}")


def main():
    ensure_credentials()
    SCHEMA_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tables, _ = all_tables()
    names = [row[0] for row in tables]
    write_csv(SCHEMA_REPORT_DIR / "tables.csv", ["TABLE_NAME", "TABLE_ROWS"], tables)

    targets = [name for name in names if name.startswith("so") or "compan" in name.lower()]
    if not targets:
        targets = names
    for table in targets:
        columns, column_headers = table_columns(table)
        safe = table.replace(".", "_")
        write_csv(SCHEMA_REPORT_DIR / f"{safe}_columns.csv", column_headers, columns)

    print(f"schema report ready in {SCHEMA_REPORT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"database query failed: {type(exc).__name__}")
        raise SystemExit(1) from None