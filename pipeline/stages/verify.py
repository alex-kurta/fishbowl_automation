import re

from pipeline.db.client import run_query

INACTIVE_STATUSES = (80, 85)


def find_sales_order(order_number: str) -> dict | None:
    pattern = f"(^|[^0-9]){re.escape(order_number)}([^0-9]|$)"
    sql = (
        "SELECT id, num, statusId, customerPO, dateCreated, subTotal, totalPrice, salesman "
        "FROM so WHERE (customerPO REGEXP %s OR num = %s) AND statusId NOT IN %s "
        "ORDER BY id DESC LIMIT 1"
    )
    rows, columns = run_query(sql, (pattern, order_number, INACTIVE_STATUSES))
    if not rows:
        return None
    return dict(zip(columns, rows[0]))


def sales_order_items(so_id: int) -> list[dict]:
    sql = (
        "SELECT productNum, description, qtyOrdered, unitPrice, typeId "
        "FROM soitem WHERE soId = %s ORDER BY soLineItem"
    )
    rows, columns = run_query(sql, (so_id,))
    return [dict(zip(columns, row)) for row in rows]


def open_sales_order(sales_order_number: str) -> None:
    raise NotImplementedError("opening the Fishbowl client window is not wired up yet")
