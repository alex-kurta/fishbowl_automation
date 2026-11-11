import re

QUOTE_PREFIXES = ("q-", "quote-")
PO_IN_SUBJECT = re.compile(r"#\s*([A-Za-z0-9][A-Za-z0-9\-_]*)")

COMMENT_BLOCK = re.compile(
    r"Comments?\s*:(.*?)(?:\n[ \t>*]*Items\b|\n[ \t>*]*SKU\s*:)",
    re.DOTALL | re.IGNORECASE,
)
COMMENT_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_/]{2,}")


class SkipMessage(Exception):
    """Raised when an email must be left alone: no import, no move, no notification."""


def is_quote_number(value: str) -> bool:
    return (value or "").strip().lower().startswith(QUOTE_PREFIXES)


def quote_reference(subject: str, order_number: str = "") -> str:
    if is_quote_number(order_number):
        return order_number.strip()
    match = PO_IN_SUBJECT.search(subject or "")
    if match and is_quote_number(match.group(1)):
        return match.group(1)
    return ""


def comment_text(body: str) -> str:
    match = COMMENT_BLOCK.search(body or "")
    if not match:
        return ""

    lines = []
    for line in match.group(1).splitlines():
        cleaned = line.strip().lstrip(">*").strip().strip("*").strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def comment_references(body: str) -> list[str]:
    text = comment_text(body)
    found = []
    seen = set()

    for token in COMMENT_TOKEN.findall(text):
        cleaned = token.strip("-_/")
        if sum(char.isdigit() for char in cleaned) < 4:
            continue
        if cleaned.isdigit() and len(cleaned) < 5:
            continue
        if cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        found.append(cleaned)
        if len(found) >= 8:
            break

    return found

