import re

from pipeline.db.client import run_query

PICK_TICKET = re.compile(
    r"give\s+pick\s+ticket\s+to\s+([A-Za-z0-9]{1,8})", re.IGNORECASE
)


def pick_ticket_code(alert_note: str) -> str:
    match = PICK_TICKET.search(alert_note or "")
    return match.group(1) if match else ""


def alert_notes(product_numbers) -> dict[str, str]:
    numbers = sorted({str(n).strip() for n in product_numbers if str(n).strip()})
    if not numbers:
        return {}
    placeholders = ", ".join(["%s"] * len(numbers))
    rows, _ = run_query(
        f"SELECT num, alertNote FROM product WHERE num IN ({placeholders})",
        numbers,
    )
    return {str(num).upper(): note or "" for num, note in rows}


def item_notes(product_numbers) -> dict[str, str]:
    return {
        number: code
        for number, note in alert_notes(product_numbers).items()
        if (code := pick_ticket_code(note))
    }
