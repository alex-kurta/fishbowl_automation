import html
import re
import smtplib
from email.message import EmailMessage

from pipeline.config import (
    MAIL_HOST,
    MAIL_PASSWORD,
    MAIL_SMTP_PORT,
    MAIL_USERNAME,
)

ORDER_NUMBER_IN_SUBJECT = re.compile(r"#\s*(\d{5,})")

PO_NUMBER_ALERT_NEW_CUSTOMER = "NEW CUSTOMER ATTEMPTING TO USE PO NUMBER - ORDER NOT PROCESSED"
PO_NUMBER_ALERT_EXISTING_CUSTOMER = "ORDER HAS A PO NUMBER"


def _money(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _bold_text(text: str) -> str:
    return f"\n** {text} **\n"


def build_notification(order, so, items) -> tuple[str, str, str]:
    alerts = [(line.sku, line.alert) for line in order.lines if line.alert]
    item_lines = [
        f"  {item['productNum']}  qty {item['qtyOrdered']}  ${_money(item['unitPrice'])}"
        for item in items
    ]
    subject = f"Fishbowl order entered: SO {so['num']} (PO {order.order_number})"

    blocks = [
        "An order was entered into Fishbowl automatically and needs manual review.",
        "",
    ]
    if alerts:
        blocks.append("ALERTS - CHECK BEFORE RELEASE")
        blocks.extend(f"  {sku}: {alert}" for sku, alert in alerts)
        blocks.append("")

    if order.po_number:
        if getattr(order, "_po_customer_new", False):
            blocks.append(_bold_text(PO_NUMBER_ALERT_NEW_CUSTOMER))
        else:
            blocks.append(_bold_text(PO_NUMBER_ALERT_EXISTING_CUSTOMER))

    blocks.extend(
        [
            f"Fishbowl SO:   {so['num']}",
            f"Customer PO:  {order.order_number}",
            f"Customer:     {order.customer_name}",
            f"Contact:      {order.customer_contact} <{order.email}>",
            f"Subtotal:     ${order.subtotal:.2f}",
            f"Shipping:     ${order.shipping_cost:.2f}",
            f"Total:        ${order.total:.2f}",
            "",
            "Items:",
            *item_lines,
            "",
            "Please open the sales order in Fishbowl and correct any fields that need attention.",
        ]
    )

    alert_html = ""
    if alerts:
        lines = "".join(
            f'<p style="margin:0;font-weight:bold;">{html.escape(alert)} '
            f'<span style="font-weight:normal;color:#444;">(product {html.escape(str(sku))})</span></p>'
            for sku, alert in alerts
        )
        alert_html = (
            '<div style="border:2px solid #b00020;background:#fff4f4;padding:10px 12px;'
            'margin:0 0 16px 0;">'
            '<p style="margin:0 0 6px 0;font-weight:bold;color:#b00020;">'
            "ALERTS - CHECK BEFORE RELEASE</p>"
            f"{lines}</div>"
        )

    po_alert_html = ""
    if order.po_number:
        if getattr(order, "_po_customer_new", False):
            po_alert_html = (
                '<div style="border:2px solid #b00020;background:#fff4f4;padding:10px 12px;'
                'margin:0 0 16px 0;">'
                f'<p style="margin:0;font-weight:bold;color:#b00020;">{html.escape(PO_NUMBER_ALERT_NEW_CUSTOMER)}</p>'
                '</div>'
            )
        else:
            po_alert_html = (
                '<div style="border:2px solid #b00020;background:#fff4f4;padding:10px 12px;'
                'margin:0 0 16px 0;">'
                f'<p style="margin:0;font-weight:bold;color:#b00020;">{html.escape(PO_NUMBER_ALERT_EXISTING_CUSTOMER)}</p>'
                '</div>'
            )

    rows = "".join(
        f"<tr><td>{html.escape(str(item['productNum']))}</td>"
        f"<td>{html.escape(str(item['qtyOrdered']))}</td>"
        f"<td>${html.escape(_money(item['unitPrice']))}</td></tr>"
        for item in items
    )
    return (
        subject,
        "\n".join(blocks),
        _notification_html_with_alerts(order, so, items, alert_html, po_alert_html),
    )


def _notification_html_with_alerts(order, so, items, alert_html, po_alert_html) -> str:
    esc = html.escape
    rows = "".join(
        f"<tr><td>{esc(str(item['productNum']))}</td>"
        f"<td>{esc(str(item['qtyOrdered']))}</td>"
        f"<td>${esc(_money(item['unitPrice']))}</td></tr>"
        for item in items
    )
    return (
        '<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111;">'
        "<p>An order was entered into Fishbowl automatically and needs manual review.</p>"
        f"{alert_html}"
        f"{po_alert_html}"
        '<table cellpadding="4" style="border-collapse:collapse;">'
        f'<tr><td><strong>Fishbowl SO</strong></td><td>{esc(str(so["num"]))}</td></tr>'
        f"<tr><td><strong>Customer PO</strong></td><td>{esc(str(order.order_number))}</td></tr>"
        f"<tr><td><strong>Customer</strong></td><td>{esc(str(order.customer_name))}</td></tr>"
        f"<tr><td><strong>Contact</strong></td><td>{esc(str(order.customer_contact))} "
        f"<{esc(str(order.email))}></td></tr>"
        f"<tr><td><strong>Subtotal</strong></td><td>${order.subtotal:.2f}</td></tr>"
        f"<tr><td><strong>Shipping</strong></td><td>${order.shipping_cost:.2f}</td></tr>"
        f"<tr><td><strong>Total</strong></td><td>${order.total:.2f}</td></tr>"
        "</table>"
        "<p><strong>Items</strong></p>"
        '<table cellpadding="4" style="border-collapse:collapse;">'
        '<tr style="text-align:left;"><th>Product</th><th>Qty</th><th>Price</th></tr>'
        f"{rows}</table>"
        "<p>Please open the sales order in Fishbowl and correct any fields that need attention.</p>"
        "</body></html>"
    )


def build_failure_notification(message, error: Exception) -> tuple[str, str]:
    match = ORDER_NUMBER_IN_SUBJECT.search(message.subject or "")
    po = match.group(1) if match else ""
    subject = "Fishbowl entry failed"
    if po:
        subject = f"{subject}: PO {po}"
    subject = f"{subject} - manual entry needed"

    body = "\n".join(
        [
            "An order email could not be entered into Fishbowl automatically.",
            "It is still in this inbox and needs to be entered by hand.",
            "",
            f"Reason:          {error}",
            f"Original subject: {message.subject}",
            f"Sender:          {message.sender}",
            f"Received:        {message.received}",
            "",
            "Please enter this order in Fishbowl manually.",
        ]
    )
    return subject, body


def send_notification(subject: str, body: str, to: str, html_body: str = "") -> None:
    message = EmailMessage()
    message["From"] = MAIL_USERNAME
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if MAIL_SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(MAIL_HOST, MAIL_SMTP_PORT)
    else:
        server = smtplib.SMTP(MAIL_HOST, MAIL_SMTP_PORT)
        server.starttls()
    try:
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)
    finally:
        server.quit()