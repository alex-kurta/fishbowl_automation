import os
import unittest
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from unittest import mock

from pipeline.config import TRAINING_DIR, inbox_hold_active
from pipeline.model import Order, OrderLine
from pipeline.stages.extract import extract_order, extract_order_from_body, html_to_text
from pipeline.stages.guards import (
    comment_references,
    is_quote_number,
    quote_reference,
)
from pipeline.stages.import_to_fishbowl import validate_headers
from pipeline.stages.inbox import InboxMessage, _body_text, has_pdf_attachment, is_order_email
from pipeline.stages.normalize import ITEM_HEADERS, _normalize_sku, order_to_csv
from pipeline.stages.notify import build_failure_notification, build_notification
from pipeline.stages.product_alerts import item_notes, pick_ticket_code


class InboxHoldTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("MAIL_HOLD_INBOX_UNTIL", None)

    def tearDown(self):
        os.environ.pop("MAIL_HOLD_INBOX_UNTIL", None)
        if self._saved is not None:
            os.environ["MAIL_HOLD_INBOX_UNTIL"] = self._saved

    def test_no_hold_when_unset(self):
        self.assertFalse(inbox_hold_active())

    def test_hold_active_before_deadline(self):
        os.environ["MAIL_HOLD_INBOX_UNTIL"] = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat()
        self.assertTrue(inbox_hold_active())

    def test_hold_expired_after_deadline(self):
        os.environ["MAIL_HOLD_INBOX_UNTIL"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        self.assertFalse(inbox_hold_active())

    def test_naive_deadline_treated_as_utc(self):
        os.environ["MAIL_HOLD_INBOX_UNTIL"] = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).replace(tzinfo=None).isoformat()
        self.assertTrue(inbox_hold_active())

    def test_unparseable_deadline_is_ignored(self):
        os.environ["MAIL_HOLD_INBOX_UNTIL"] = "tomorrow morning"
        self.assertFalse(inbox_hold_active())


class InboxSubjectTests(unittest.TestCase):
    def test_forwarded_order_subject(self):
        self.assertTrue(is_order_email("FW: Example Laboratories: New order: #100000064"))

    def test_direct_order_subject(self):
        self.assertTrue(is_order_email("Example Laboratories: New order: #1000000001"))

    def test_non_order_subject(self):
        self.assertFalse(is_order_email("Re: shipping question about my order"))
        self.assertFalse(is_order_email("Invoice attached"))

    def test_own_notification_is_not_an_order(self):
        self.assertFalse(is_order_email("Fishbowl order entered: SO 900002 (PO 100000064)"))

    def test_failure_notification_is_not_an_order(self):
        message = InboxMessage(
            uid="1",
            subject="FW: Example Laboratories: New order: #100000064",
            body="see attached PDF",
            sender="customer@example.com",
            received="today",
        )
        subject, body = build_failure_notification(message, ValueError("no line items"))
        self.assertFalse(is_order_email(subject))
        self.assertNotIn("#", subject)
        self.assertNotIn("new order", subject.lower())
        self.assertIn("100000064", subject)
        self.assertIn(message.subject, body)
        self.assertIn("no line items", body)


class PdfAttachmentTests(unittest.TestCase):
    def _message(self, filename=None, subtype=None):
        from email.message import EmailMessage as MimeMessage

        message = MimeMessage()
        message["Subject"] = "test"
        message.set_content("see attached")
        if filename:
            message.add_attachment(
                b"%PDF-1.4", maintype="application", subtype="pdf", filename=filename
            )
        elif subtype:
            message.add_attachment(b"%PDF-1.4", maintype="application", subtype=subtype)
        return message_from_bytes(message.as_bytes())

    def test_pdf_attachment_detected(self):
        self.assertTrue(has_pdf_attachment(self._message(filename="order.pdf")))

    def test_uppercase_pdf_extension_detected(self):
        self.assertTrue(has_pdf_attachment(self._message(filename="PO_1234.PDF")))

    def test_pdf_content_type_without_filename_detected(self):
        self.assertTrue(has_pdf_attachment(self._message(subtype="pdf")))

    def test_email_without_attachment_is_processed(self):
        self.assertFalse(has_pdf_attachment(self._message()))

    def test_non_pdf_attachment_is_processed(self):
        from email.message import EmailMessage as MimeMessage

        message = MimeMessage()
        message["Subject"] = "test"
        message.set_content("see attached")
        message.add_attachment(
            b"some notes", maintype="text", subtype="plain", filename="notes.txt"
        )
        parsed = message_from_bytes(message.as_bytes())
        self.assertFalse(has_pdf_attachment(parsed))


class QuoteGateTests(unittest.TestCase):
    def test_q_dash_prefix_detected(self):
        self.assertTrue(is_quote_number("Q-12345"))

    def test_quote_prefix_detected(self):
        self.assertTrue(is_quote_number("Quote-12345"))

    def test_case_insensitive(self):
        self.assertTrue(is_quote_number("q-12345"))
        self.assertTrue(is_quote_number("QUOTE-12345"))

    def test_real_po_not_treated_as_quote(self):
        self.assertFalse(is_quote_number("100000065"))
        self.assertFalse(is_quote_number("QY00000000000000"))

    def test_quote_in_subject_detected(self):
        self.assertEqual(quote_reference("New order: #Q-12345"), "Q-12345")
        self.assertEqual(quote_reference("FW: New order: #Quote-987"), "Quote-987")

    def test_quote_order_number_detected(self):
        self.assertEqual(quote_reference("anything", "Q-555"), "Q-555")

    def test_normal_order_not_gated(self):
        self.assertEqual(
            quote_reference("Example Laboratories: New order: #100000065", "100000065"),
            "",
        )


class CommentGateTests(unittest.TestCase):
    def test_quote_number_in_comment(self):
        body = (
            "Comments:\n\nFrom Quote 900001. We would like 24 wks gestation, "
            "female for the 2468 cells.\n\nItems\n\nQty\n\nPrice\n"
        )
        self.assertEqual(comment_references(body), ["900001"])

    def test_discount_code_is_not_a_reference(self):
        body = "Comments:\n\ndiscount code: SAVE20\n\nItems\n\nQty\n\nPrice\n"
        self.assertEqual(comment_references(body), [])

    def test_po_token_in_comment(self):
        self.assertEqual(comment_references("Comments:\n\nPO90001\n\nItems"), ["PO90001"])

    def test_alphanumeric_po_in_comment(self):
        body = (
            "Comments:\n\nPlease label the PO number 000000000ABC and Lot Number "
            "on the package list.\n\nItems"
        )
        self.assertIn("000000000ABC", comment_references(body))

    def test_quoted_markers_stripped(self):
        self.assertEqual(comment_references("Comments:\n>\n> *PO90001 *\n>\n\nItems"), ["PO90001"])

    def test_no_comment_section(self):
        self.assertEqual(comment_references("Items\n\nQty\n\nPrice\n"), [])

    def test_short_numbers_ignored(self):
        self.assertEqual(comment_references("Comments:\n\nShip by 2468 or 24 units\n\nItems"), [])


class SkuNormalizationTests(unittest.TestCase):
    def test_repeated_prefix_collapsed(self):
        self.assertEqual(_normalize_sku(OrderLine(sku="5678-5678")), "5678")

    def test_repeated_prefix_with_option(self):
        self.assertEqual(_normalize_sku(OrderLine(sku="8765-8765-4")), "8765-4")

    def test_plain_sku_untouched(self):
        self.assertEqual(_normalize_sku(OrderLine(sku="0099")), "0099")

    def test_hyphenated_sku_untouched(self):
        self.assertEqual(_normalize_sku(OrderLine(sku="3D-9100-48")), "3D-9100-48")

    def test_plate_size_option_selects_sku(self):
        line = OrderLine(sku="3D-9100", selected_option="96 well plate")
        with mock.patch("pipeline.stages.normalize.OPTION_SKU_BASE", "3D-9100"):
            self.assertEqual(_normalize_sku(line), "3D-9100-96")

    def test_plate_size_rule_follows_configured_base(self):
        line = OrderLine(sku="ABC-1000", selected_option="24 well plate")
        with mock.patch("pipeline.stages.normalize.OPTION_SKU_BASE", "ABC-1000"):
            self.assertEqual(_normalize_sku(line), "ABC-1000-24")


class HeaderValidationTests(unittest.TestCase):
    def test_matching_headers_pass(self):
        so = '"Flag","SONum","Status"'
        item = '"Flag","SOItemTypeID","ProductNumber"'
        ok, _ = validate_headers([so, item], [so, item])
        self.assertTrue(ok)

    def test_mismatched_so_header_fails(self):
        so = '"Flag","SONum","Status"'
        item = '"Flag","SOItemTypeID","ProductNumber"'
        ok, message = validate_headers([so, item], ['"Flag","Wrong","Status"', item])
        self.assertFalse(ok)
        self.assertIn("SO header", message)

    def test_missing_header_rows_fails(self):
        ok, message = validate_headers(['"Flag"'], ['"Flag"'])
        self.assertFalse(ok)
        self.assertIn("missing one or both header rows", message)


class ImapBodyFormatTests(unittest.TestCase):
    BODY = (
        "Hello Jane Doe,\n\n"
        "(jane@example.edu)\n\n"
        "Thank you for ordering from Example Laboratories, Inc.\n\n"
        "Your Order #100000065\n\n"
        "Placed on Nov 5, 2026, 9:38:33 AM\n\n"
        "Billing Info\n\n\nJane Doe\n\nExample University\n\n"
        "1 Main St\n\nRm 2\n\nSpringfield, Illinois, 62704\n\nUnited States\n\n\n"
        "Shipping Info\n\n\nJohn Smith\n\nExample University\n\n"
        "2 Lab Rd\n\nBldg 3\n\nShelbyville, Illinois, 62705\n\nUnited States\n\n\n"
        "Payment Method\n\n\nCredit Cards (card processor)\n\n\n"
        "Shipping Method\n\n\nFederal Express - Priority Overnight\n\n\n"
        "Items \tQty \tPrice\n\n"
        "Example Medium\n\n"
        "SKU: 4321-4321\n\n"
        "Please select type of Medium below:\n"
        "Complete kit (includes supplements) - 4321\n\n"
        "3\t $300.00\n"
        "Subtotal \t$300.00\n"
        "Shipping & Handling \t$20.00\n"
        "Grand Total \t$320.00\n"
    )

    def setUp(self):
        self.order = extract_order_from_body(
            self.BODY, "Example Laboratories: New order: #100000065"
        )

    def test_line_items_parsed_from_tabbed_header(self):
        self.assertEqual(len(self.order.lines), 1)
        line = self.order.lines[0]
        self.assertEqual(line.sku, "4321-4321")
        self.assertEqual(line.quantity, 3)

    def test_listed_price_is_treated_as_line_total(self):
        self.assertEqual(self.order.lines[0].unit_price, 100.0)
        extended = sum(l.quantity * l.unit_price for l in self.order.lines)
        self.assertAlmostEqual(extended, self.order.subtotal, places=2)

    def test_totals_parsed_from_inline_values(self):
        self.assertEqual(self.order.subtotal, 300.0)
        self.assertEqual(self.order.shipping_cost, 20.00)
        self.assertEqual(self.order.total, 320.00)

    def test_customer_uses_company_not_contact(self):
        self.assertEqual(self.order.customer_name, "Example University")
        self.assertEqual(self.order.customer_contact, "Jane Doe")

    def test_addresses_survive_blank_lines(self):
        self.assertEqual(self.order.billing.city, "Springfield")
        self.assertEqual(self.order.billing.state, "Illinois")
        self.assertEqual(self.order.billing.zip_code, "62704")
        self.assertEqual(self.order.shipping.city, "Shelbyville")

    def test_shipping_method_from_inline_block(self):
        self.assertEqual(self.order.carrier, "FedEx")
        self.assertEqual(self.order.carrier_service, "Priority Overnight")


class AddressBlockFormatTests(unittest.TestCase):
    BODY = (
        "Hello Jane Doe,\n\n"
        "(jane@example.edu)\n\n"
        "Your Order #100000099\n\n"
        "Placed on Nov 5, 2026, 9:38:33 AM\n\n"
        "Billing Info\n\n{block}\n\n"
        "Shipping Info\n\n{block}\n\n"
        "Payment Method\n\nCredit Cards (card processor)\n\n"
        "Shipping Method\n\nFederal Express - Priority Overnight\n\n"
        "Items \tQty \tPrice\n\n"
        "Example Medium\n\n"
        "SKU: 4321-4321\n\n"
        "1\t $300.00\n"
        "Subtotal \t$300.00\n"
        "Grand Total \t$300.00\n"
    )

    def parse(self, block):
        return extract_order_from_body(self.BODY.format(block=block), "New order: #100000099")

    def test_single_street_line_keeps_city_state_zip_out_of_street(self):
        order = self.parse(
            "Jane Doe\n"
            "Example University\n"
            "123 Main St\n"
            "Riverton, Illinois, 62707\n"
            "United States\n"
            "T: 555-0100"
        )
        addr = order.shipping
        self.assertEqual(addr.name, "Jane Doe")
        self.assertEqual(addr.company, "Example University")
        self.assertEqual(addr.street, "123 Main St")
        self.assertEqual(addr.city, "Riverton")
        self.assertEqual(addr.state, "Illinois")
        self.assertEqual(addr.zip_code, "62707")
        self.assertEqual(addr.country, "United States")

    def test_block_without_company_line(self):
        addr = self.parse(
            "Pat Lee\n"
            "456 Oak Ave\n"
            "Capital City, Illinois, 62706\n"
            "United States"
        ).shipping
        self.assertEqual(addr.company, "")
        self.assertEqual(addr.street, "456 Oak Ave")
        self.assertEqual(addr.city, "Capital City")
        self.assertEqual(addr.state, "Illinois")
        self.assertEqual(addr.zip_code, "62706")

    def test_company_street_city_country_block(self):
        addr = self.parse(
            "Pat Lee\n"
            "Example University\n"
            "456 Oak Ave\n"
            "Capital City, Illinois, 62706\n"
            "United States"
        ).shipping
        self.assertEqual(addr.company, "Example University")
        self.assertEqual(addr.street, "456 Oak Ave")
        self.assertEqual(addr.city, "Capital City")
        self.assertEqual(addr.state, "Illinois")
        self.assertEqual(addr.zip_code, "62706")
        self.assertEqual(addr.country, "United States")

    def test_compact_state_zip_with_plus_four(self):
        addr = self.parse(
            "Alex Doe\n"
            "MIT\n"
            "123 Main St\n"
            "Springfield, IL 62704-1234\n"
            "United States"
        ).shipping
        self.assertEqual(addr.street, "123 Main St")
        self.assertEqual(addr.city, "Springfield")
        self.assertEqual(addr.state, "IL")
        self.assertEqual(addr.zip_code, "62704-1234")

    def test_two_street_lines_still_parsed(self):
        addr = self.parse(
            "John Smith\n"
            "Example University\n"
            "2 Lab Rd\n"
            "Bldg 3\n"
            "Shelbyville, Illinois, 62705\n"
            "United States"
        ).shipping
        self.assertEqual(addr.street, "2 Lab Rd\nBldg 3")
        self.assertEqual(addr.city, "Shelbyville")
        self.assertEqual(addr.zip_code, "62705")

    def test_phone_line_is_not_taken_as_country(self):
        addr = self.parse(
            "Chris Doe\n"
            "Example University\n"
            "789 Pine Rd\n"
            "Springfield, Illinois, 62704\n"
            "T: 555-0100"
        ).shipping
        self.assertEqual(addr.street, "789 Pine Rd")
        self.assertEqual(addr.city, "Springfield")
        self.assertEqual(addr.country, "United States")

    def test_repeated_name_line_is_dropped_from_street(self):
        addr = self.parse(
            "John Smith\n"
            "2 Lab Rd\n"
            "John Smith\n"
            "Shelbyville, Illinois, 62705\n"
            "United States"
        ).shipping
        self.assertEqual(addr.street, "2 Lab Rd")
        self.assertEqual(addr.name, "John Smith")

    def test_csv_row_carries_state_and_zip_separately(self):
        import csv
        import tempfile
        from pathlib import Path

        from pipeline.stages.normalize import order_to_csv

        order = self.parse(
            "Jane Doe\n"
            "Example University\n"
            "123 Main St\n"
            "Riverton, Illinois, 62707\n"
            "United States"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = order_to_csv(order, Path(tmp) / "order.csv")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        so = dict(zip(rows[0], rows[2]))
        self.assertEqual(so["ShipToAddress"], "123 Main St")
        self.assertEqual(so["ShipToCity"], "Riverton")
        self.assertEqual(so["ShipToState"], "IL")
        self.assertEqual(so["ShipToZip"], "62707")


class ProductAlertNoteTests(unittest.TestCase):
    def test_pick_ticket_code_variants(self):
        cases = {
            "Give Pick Ticket to AA": "AA",
            "Give Pick Ticket to DD.": "DD",
            "Give Pick Ticket to EE": "EE",
            "Give Pick Ticket to AA and ask AA for lead time": "AA",
            "Give Pick Ticket to CC": "CC",
            "Give Pick Ticket to BB / NO discounts": "BB",
        }
        for note, expected in cases.items():
            self.assertEqual(pick_ticket_code(note), expected, note)

    def test_non_pick_ticket_notes_are_ignored(self):
        self.assertEqual(pick_ticket_code("Not sold separately, part of 8888"), "")
        self.assertEqual(pick_ticket_code("Place an order from Example Vendor. NEVER DISCOUNT"), "")
        self.assertEqual(pick_ticket_code(""), "")

    def test_item_notes_looks_up_each_sku(self):
        rows = [
            ("5001", "Give Pick Ticket to BB"),
            ("5002", "Give Pick Ticket to EE"),
            ("9999", "Not sold separately, part of 8888"),
        ]
        with mock.patch(
            "pipeline.stages.product_alerts.run_query", return_value=(rows, None)
        ) as run_query:
            notes = item_notes(["5001", "5002", "9999"])
        self.assertEqual(notes, {"5001": "BB", "5002": "EE"})
        self.assertEqual(run_query.call_args[0][1], ["5001", "5002", "9999"])

    def test_item_notes_without_skus_skips_lookup(self):
        with mock.patch("pipeline.stages.product_alerts.run_query") as run_query:
            self.assertEqual(item_notes([]), {})
        run_query.assert_not_called()

    def test_lowercase_product_number_matches(self):
        rows = [("demo-1000", "Give Pick Ticket to AA")]
        with mock.patch(
            "pipeline.stages.product_alerts.run_query", return_value=(rows, None)
        ):
            self.assertEqual(item_notes(["demo-1000"]), {"DEMO-1000": "AA"})

    def test_note_lands_in_csv_item_note_column(self):
        import csv
        import tempfile
        from pathlib import Path

        order = Order(
            order_number="100000099",
            customer_name="Example University",
            lines=[
                OrderLine(
                    sku="5001",
                    description="Product",
                    quantity=1,
                    unit_price=10.0,
                    note="BB",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = order_to_csv(order, Path(tmp) / "order.csv")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        item = dict(zip(ITEM_HEADERS, rows[3]))
        self.assertEqual(item["Note"], "BB")
        self.assertEqual(item["ProductNumber"], "5001")


class NotificationAlertTests(unittest.TestCase):
    def make_order(self, alert=""):
        return Order(
            order_number="100000099",
            customer_name="Example University",
            customer_contact="Jane Doe",
            email="jane@example.edu",
            subtotal=10.0,
            shipping_cost=2.0,
            total=12.0,
            lines=[
                OrderLine(
                    sku="5001",
                    description="Product",
                    quantity=1,
                    unit_price=10.0,
                    note="MB",
                    alert=alert,
                )
            ],
        )

    ITEMS = [
        {"productNum": "5001", "qtyOrdered": 1, "unitPrice": 10.0},
    ]

    def test_alert_is_visible_in_plain_text(self):
        subject, body, html_body = build_notification(
            self.make_order("Give Pick Ticket to AA"),
            {"num": "900007"},
            self.ITEMS,
        )
        self.assertIn("Fishbowl order entered: SO 900007", subject)
        self.assertIn("ALERTS - CHECK BEFORE RELEASE", body)
        self.assertIn("5001: Give Pick Ticket to AA", body)

    def test_alert_is_bold_in_html(self):
        _, _, html_body = build_notification(
            self.make_order("Give Pick Ticket to AA"),
            {"num": "900007"},
            self.ITEMS,
        )
        self.assertIn("ALERTS - CHECK BEFORE RELEASE", html_body)
        self.assertIn('font-weight:bold;">Give Pick Ticket to AA', html_body)

    def test_html_escapes_alert_text(self):
        _, _, html_body = build_notification(
            self.make_order("Give Pick Ticket to R&D"),
            {"num": "900007"},
            self.ITEMS,
        )
        self.assertIn("R&amp;D", html_body)

    def test_order_without_alerts_has_no_alert_block(self):
        _, body, html_body = build_notification(
            self.make_order(""), {"num": "900007"}, self.ITEMS
        )
        self.assertNotIn("ALERTS", body)
        self.assertNotIn("ALERTS", html_body)


class HtmlBodyFormatTests(unittest.TestCase):
    HTML = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head><style type="text/css">.hidden{color:#ffffff}</style></head>
<body style="margin: 0;">
<table class="main">
<tr><td class="header"><img src="logo.png" alt="Example Labs"></td></tr>
<tr><td>
<p>Hello Jane Doe,</p>
<p>(jane@example.edu)</p>
<p>Your Order #100000065</p>
<p>Placed on Nov 5, 2026, 9:38:33 AM</p>
</td></tr>
<tr><td><h3>Billing Info</h3></td></tr>
<tr><td>Jane Doe</td></tr>
<tr><td>Example University</td></tr>
<tr><td>1 Main St</td></tr>
<tr><td>Rm 2</td></tr>
<tr><td>Springfield, Illinois, 62704</td></tr>
<tr><td>United States</td></tr>
<tr><td><h3>Shipping Info</h3></td></tr>
<tr><td>John Smith</td></tr>
<tr><td>Example University</td></tr>
<tr><td>2 Lab Rd</td></tr>
<tr><td>Bldg 3</td></tr>
<tr><td>Shelbyville, Illinois, 62705</td></tr>
<tr><td>United States</td></tr>
<tr><td><h3>Payment Method</h3></td></tr>
<tr><td>Credit Cards (card processor)</td></tr>
<tr><td><h3>Shipping Method</h3></td></tr>
<tr><td>Federal Express - Priority Overnight</td></tr>
<tr><td><h3>Additional Information</h3></td></tr>
<tr><td>Order Comments:</td></tr>
<tr><td>From Quote 900001 we need the extra supplements</td></tr>
<tr><td><h3>Items</h3></td></tr>
<tr><td>Qty</td><td>Price</td></tr>
<tr><td>Example Medium</td></tr>
<tr><td>SKU: 4321-4321</td></tr>
<tr><td>Please select type of Medium below:</td></tr>
<tr><td>Complete kit (includes supplements) - 4321</td></tr>
<tr><td>3</td><td>$300.00</td></tr>
<tr><td>Subtotal</td><td>$300.00</td></tr>
<tr><td>Shipping &amp; Handling</td><td>$20.00</td></tr>
<tr><td>Grand Total</td><td>$320.00</td></tr>
</table>
</body>
</html>
"""

    def setUp(self):
        self.order = extract_order_from_body(
            self.HTML, "Example Laboratories: New order: #100000065"
        )

    def test_html_order_number_parsed(self):
        self.assertEqual(self.order.order_number, "100000065")

    def test_html_line_items_parsed(self):
        self.assertEqual(len(self.order.lines), 1)
        line = self.order.lines[0]
        self.assertEqual(line.sku, "4321-4321")
        self.assertEqual(line.quantity, 3)

    def test_html_line_total_divided_to_unit_price(self):
        self.assertEqual(self.order.lines[0].unit_price, 100.0)
        extended = sum(l.quantity * l.unit_price for l in self.order.lines)
        self.assertAlmostEqual(extended, self.order.subtotal, places=2)

    def test_html_totals_parsed(self):
        self.assertEqual(self.order.subtotal, 300.0)
        self.assertEqual(self.order.shipping_cost, 20.00)
        self.assertEqual(self.order.total, 320.00)

    def test_html_addresses_parsed(self):
        self.assertEqual(self.order.billing.city, "Springfield")
        self.assertEqual(self.order.billing.zip_code, "62704")
        self.assertEqual(self.order.shipping.city, "Shelbyville")

    def test_html_contact_and_shipping_method(self):
        self.assertEqual(self.order.customer_contact, "Jane Doe")
        self.assertEqual(self.order.email, "jane@example.edu")
        self.assertEqual(self.order.carrier, "FedEx")
        self.assertEqual(self.order.carrier_service, "Priority Overnight")

    def test_html_comment_gate_still_sees_comments(self):
        self.assertEqual(comment_references(html_to_text(self.HTML)), ["900001"])

    def test_style_block_dropped(self):
        text = html_to_text(self.HTML)
        self.assertNotIn("#ffffff", text)
        self.assertNotIn("hidden", text)

    def test_plain_text_body_not_treated_as_html(self):
        from pipeline.stages.extract import looks_like_html

        text = "Hello Jane,\n\nYour Order #100000065\n\nItems\n\nQty\n\nPrice\n"
        self.assertFalse(looks_like_html(text))
        order = extract_order_from_body(text, "New order: #100000065")
        self.assertEqual(order.order_number, "100000065")

    def test_mailbox_body_text_converts_html_part(self):
        from email.message import EmailMessage as MimeMessage

        message = MimeMessage()
        message["Subject"] = "Example Laboratories: New order: #100000065"
        message.set_content(self.HTML, subtype="html")
        parsed = message_from_bytes(message.as_bytes())
        body = _body_text(parsed)
        self.assertIn("Your Order #100000065", body)
        self.assertNotIn("<html", body)


class ExtractFromFileTests(unittest.TestCase):
    SAMPLE = TRAINING_DIR / "sample_order_forwarded.msg"

    def setUp(self):
        if not self.SAMPLE.exists():
            self.skipTest("sample order email not present")
        self.order = extract_order(self.SAMPLE)

    def test_forwarded_email_extracts_order(self):
        self.assertRegex(self.order.order_number, r"^\d+$")
        self.assertGreaterEqual(len(self.order.lines), 1)
        self.assertTrue(self.order.billing.state)

    def test_unit_prices_reconcile_with_subtotal(self):
        extended = sum(line.quantity * line.unit_price for line in self.order.lines)
        self.assertAlmostEqual(extended, self.order.subtotal, places=2)


if __name__ == "__main__":
    unittest.main()
