import re
from html.parser import HTMLParser
from pathlib import Path

from pipeline.model import Address, Order, OrderLine

HTML_MARKER = re.compile(r"<(!doctype\s+html|html|body|table)\b", re.IGNORECASE)
BLOCK_TAGS = {
    "p",
    "div",
    "tr",
    "table",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
}
SKIP_TAGS = {"script", "style", "head", "title"}


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def looks_like_html(text: str) -> bool:
    return bool(HTML_MARKER.search(text or ""))


def html_to_text(raw: str) -> str:
    parser = _HtmlText()
    parser.feed(raw or "")
    parser.close()
    lines = []
    for line in "".join(parser.parts).splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def extract_order(email_path: Path, pdf_path: Path | None = None) -> Order:
    import extract_msg

    msg = extract_msg.openMsg(str(email_path))
    body = msg.body or ""
    return _parse_body(body, msg.subject or "")


def extract_order_from_body(body: str, subject: str = "") -> Order:
    return _parse_body(body or "", subject or "")


def _parse_body(body: str, subject: str) -> Order:
    if looks_like_html(body):
        body = html_to_text(body)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    order = Order()
    order.order_number = _extract_order_number(body, subject)
    order.date = _extract_date(body)
    order.customer_contact, order.email = _extract_contact(body)
    order.billing = _extract_address(body, "Billing Info")
    order.shipping = _extract_address(body, "Shipping Info")
    order.customer_name = order.billing.company or order.billing.name
    order.payment_method = _extract_payment_method(body)
    order.carrier, order.carrier_service = _extract_shipping_method(body)
    order.lines = _extract_lines(body)
    order.subtotal, order.shipping_cost, order.total = _extract_totals(body)
    _reconcile_line_prices(order)
    order.note = _build_note(order)
    return order


def _reconcile_line_prices(order: Order) -> None:
    if not order.lines or order.subtotal <= 0:
        return

    as_unit = sum(line.quantity * line.unit_price for line in order.lines)
    if abs(as_unit - order.subtotal) <= 0.02:
        return

    as_extended = sum(line.unit_price for line in order.lines)
    if abs(as_extended - order.subtotal) <= 0.02:
        for line in order.lines:
            if line.quantity > 1 and line.unit_price:
                line.unit_price = round(line.unit_price / line.quantity, 2)


def _extract_order_number(body: str, subject: str) -> str:
    m = re.search(r"Your Order #(\d+)", body)
    if m:
        return m.group(1)
    m = re.search(r"#(\d+)", subject)
    if m:
        return m.group(1)
    return ""


def _extract_date(body: str) -> str:
    m = re.search(r"Placed on (\w+ \d+, \d{4})", body)
    if m:
        from datetime import datetime

        dt = datetime.strptime(m.group(1), "%b %d, %Y")
        return dt.strftime("%#m/%#d/%Y")
    return ""


def _extract_contact(body: str) -> tuple[str, str]:
    m = re.search(r"Hello (.+?),\s*\(([^)]+)\)", body)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


SECTION_HEADERS = (
    "Billing Info",
    "Shipping Info",
    "Payment Method",
    "Shipping Method",
    "Additional Information",
    "Items",
)
SECTION_STOP = re.compile(
    r"^[ \t]*(?:" + "|".join(re.escape(name) for name in SECTION_HEADERS) + r")[ \t]*$",
    re.MULTILINE,
)


def _section_lines(body: str, section: str) -> list[str]:
    start = re.search(rf"^[ \t]*{re.escape(section)}[ \t]*$", body, re.MULTILINE)
    if not start:
        return []
    rest = body[start.end():]
    stop = SECTION_STOP.search(rest)
    block = rest[: stop.start()] if stop else rest[:500]
    return [line.strip() for line in block.splitlines() if line.strip()]


CITY_STATE_ZIP = re.compile(
    r"^(?P<city>[^,]+?)\s*,\s*(?P<state>[^,\d]+?)\s*[,\s]\s*(?P<zip>\d{5}(?:-\d{4})?)\s*$"
)
PHONE_LINE = re.compile(r"^(?:T|Tel|Phone|Ph|Fax)\s*[:.]", re.IGNORECASE)
STREET_HINT = re.compile(
    r"\b(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|ct|court"
    r"|pl|place|way|hwy|highway|pkwy|parkway|cir|circle|sq|square|ter|terrace"
    r"|trl|trail|ste|suite|rm|room|bldg|building|fl|floor|unit|apt|po box|p\.o\.)\b",
    re.IGNORECASE,
)
COUNTRY_LINE = re.compile(r"^[A-Za-z][A-Za-z .&'\-]*$")


def _looks_like_street(line: str) -> bool:
    return bool(re.match(r"^\d", line) or STREET_HINT.search(line))


def _extract_address(body: str, section: str) -> Address:
    lines = _section_lines(body, section)
    if not lines:
        return Address()

    addr = Address()
    addr.name = lines[0]
    rest = [line for line in lines[1:] if not PHONE_LINE.match(line)]

    city_idx = next(
        (i for i, line in enumerate(rest) if CITY_STATE_ZIP.match(line)), None
    )
    if city_idx is None:
        if len(rest) >= 2:
            addr.company = rest[0]
        addr.street = "\n".join(rest[1:] if len(rest) > 1 else rest)
        return addr

    match = CITY_STATE_ZIP.match(rest[city_idx])
    addr.city = match.group("city").strip()
    addr.state = match.group("state").strip()
    addr.zip_code = match.group("zip").strip()

    head = rest[:city_idx]
    if len(head) >= 2 and not _looks_like_street(head[0]):
        addr.company = head[0]
        head = head[1:]
    addr.street = "\n".join(head)

    for line in rest[city_idx + 1:]:
        if COUNTRY_LINE.match(line):
            addr.country = line
            break

    addr.street = _drop_repeated_names(addr)
    return addr


def _drop_repeated_names(addr: Address) -> str:
    names = {" ".join(n.split()).casefold() for n in (addr.name, addr.company) if n.strip()}
    lines = [line for line in addr.street.splitlines() if line.strip()]
    return "\n".join(line for line in lines if " ".join(line.split()).casefold() not in names)


def _extract_payment_method(body: str) -> str:
    lines = _section_lines(body, "Payment Method")
    return lines[0] if lines else ""


def _extract_shipping_method(body: str) -> tuple[str, str]:
    lines = _section_lines(body, "Shipping Method")
    if not lines:
        return "", ""
    full = " ".join(lines)
    carrier = ""
    service = ""
    if "Federal Express" in full or "FedEx" in full:
        carrier = "FedEx"
    elif "UPS" in full:
        carrier = "UPS"
    elif "DHL" in full:
        carrier = "DHL"
    for keyword in ["Priority Overnight", "Standard Overnight", "2 Day",
                     "Next Day Air", "International Priority Overnight",
                     "International First Overnight", "Inernational Economy"]:
        if keyword in full:
            service = keyword
            break
    return carrier, service


ITEMS_BLOCK = re.compile(r"Items\s+Qty\s+Price\s*\n+(.+?)\n\s*Subtotal", re.DOTALL)
QTY_AND_PRICE = re.compile(r"^(\d+)\s+\$?([\d,]+\.\d{2})\s*$")
QTY_ONLY = re.compile(r"^(\d+)$")
PRICE_ONLY = re.compile(r"^\$?([\d,]+\.\d{2})\s*$")


def _extract_lines(body: str) -> list[OrderLine]:
    m = ITEMS_BLOCK.search(body)
    if not m:
        return []

    lines = [line.strip() for line in m.group(1).splitlines() if line.strip()]

    items = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("SKU:") or PRICE_ONLY.match(line):
            i += 1
            continue

        desc = line
        i += 1

        sku = ""
        if i < len(lines) and lines[i].startswith("SKU:"):
            sku = lines[i].replace("SKU:", "").strip()
            i += 1
        if not sku:
            continue

        qty = 0
        price = 0.0
        option_parts = []

        while i < len(lines):
            current = lines[i]

            both = QTY_AND_PRICE.match(current)
            if both:
                qty = int(both.group(1))
                price = float(both.group(2).replace(",", ""))
                i += 1
                break

            if QTY_ONLY.match(current):
                if i + 1 < len(lines) and PRICE_ONLY.match(lines[i + 1]):
                    qty = int(current)
                    price = float(PRICE_ONLY.match(lines[i + 1]).group(1).replace(",", ""))
                    i += 2
                    break
                i += 1
                continue

            if current.lower().startswith(("select ", "please select")):
                if i + 1 < len(lines):
                    option_parts.append(lines[i + 1])
                    i += 2
                    continue

            if "Cat#" in current:
                option_parts.append(current)

            i += 1

        if qty > 0:
            items.append(OrderLine(
                sku=sku,
                description=desc,
                quantity=qty,
                unit_price=price,
                selected_option=" | ".join(option_parts),
            ))

    return items


def _extract_totals(body: str) -> tuple[float, float, float]:
    subtotal = 0.0
    shipping = 0.0
    total = 0.0

    m = re.search(r"Subtotal\s+\$?([\d,]+\.\d{2})", body)
    if m:
        subtotal = float(m.group(1).replace(",", ""))

    m = re.search(r"Shipping & Handling\s+\$?([\d,]+\.\d{2})", body)
    if m:
        shipping = float(m.group(1).replace(",", ""))

    m = re.search(r"Grand Total\s+\$?([\d,]+\.\d{2})", body)
    if m:
        total = float(m.group(1).replace(",", ""))

    return subtotal, shipping, total


def _build_note(order: Order) -> str:
    parts = []
    if order.payment_method:
        parts.append(f"Payment: {order.payment_method}")
    if order.carrier and order.carrier_service:
        parts.append(f"Shipping: {order.carrier} {order.carrier_service}")
    if order.email:
        parts.append(f"Order email: {order.email}")
    return "\n".join(parts)
