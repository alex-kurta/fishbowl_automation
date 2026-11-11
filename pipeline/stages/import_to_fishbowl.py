import csv
import io
import re
from pathlib import Path

from pipeline.db.client import run_query
from pipeline.fishbowl_api import FishbowlApiClient

IMPORT_TYPE = "ImportSalesOrder"


class DuplicateOrderError(Exception):
    def __init__(self, order_number: str, existing: list[dict]):
        self.order_number = order_number
        self.existing = existing
        details = ", ".join(
            f"SO {row['num']} (id {row['id']}, customer PO '{row['customerPO']}', "
            f"status {row['statusId']}, created {row['dateCreated']})"
            for row in existing
        )
        super().__init__(f"order {order_number} already exists in Fishbowl: {details}")


INACTIVE_STATUSES = (80, 85)


def find_existing_orders(order_number: str) -> list[dict]:
    pattern = f"(^|[^0-9]){re.escape(order_number)}([^0-9]|$)"
    sql = (
        "SELECT id, num, customerPO, statusId, dateCreated FROM so "
        "WHERE (num = %s OR customerPO REGEXP %s OR customFields REGEXP %s) "
        "AND statusId NOT IN %s"
    )
    rows, columns = run_query(sql, (order_number, pattern, pattern, INACTIVE_STATUSES))
    return [dict(zip(columns, row)) for row in rows]


def po_number_from_csv(csv_path: Path) -> str:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        for row in reader:
            if row and row[0] == "SO":
                return dict(zip(header, row)).get("PONum", "").strip()
    return ""


def csv_to_import_rows(csv_path: Path) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        parsed = list(csv.reader(handle))

    rows = []
    for row in parsed:
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="", quoting=csv.QUOTE_ALL).writerow(row)
        rows.append(buffer.getvalue())
    return rows


def validate_headers(import_headers: list[str], import_rows: list[str]) -> tuple[bool, str]:
    if len(import_rows) < 2:
        return False, "generated CSV is missing one or both header rows"
    if len(import_headers) < 2:
        return False, "Fishbowl returned fewer than two header rows"
    if next(csv.reader([import_rows[0]])) != next(csv.reader([import_headers[0]])):
        return False, "SO header row does not match Fishbowl ImportSalesOrder header"
    generated_item = next(csv.reader([import_rows[1]]))
    expected_item = next(csv.reader([import_headers[1]]))
    if generated_item[: len(expected_item)] != expected_item:
        return False, "Item header row does not match Fishbowl ImportSalesOrder header"
    return True, "headers match"


def import_sales_order(csv_path: Path, client: FishbowlApiClient | None = None) -> str:
    order_number = po_number_from_csv(csv_path)
    if order_number:
        existing = find_existing_orders(order_number)
        if existing:
            raise DuplicateOrderError(order_number, existing)

    rows = csv_to_import_rows(csv_path)
    owns_client = client is None
    if owns_client:
        client = FishbowlApiClient.from_env()
        client.login()
    try:
        headers = client.get_import_headers(IMPORT_TYPE)
        rows[0] = headers[0]
        rows[1] = headers[1]
        client.import_rows(IMPORT_TYPE, rows)
    finally:
        if owns_client:
            client.logout()
    return order_number
