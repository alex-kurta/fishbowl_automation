import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import ORDER_NOTIFY_TO, OUTPUT_DIR
from pipeline.stages.extract import extract_order
from pipeline.stages.import_to_fishbowl import DuplicateOrderError, import_sales_order
from pipeline.stages.normalize import order_to_csv
from pipeline.stages.notify import build_notification, send_notification
from pipeline.stages.verify import find_sales_order, sales_order_items


def run(email_path: Path, pdf_path: Path | None = None, execute: bool = False):
    order = extract_order(email_path, pdf_path)
    csv_path = order_to_csv(order, OUTPUT_DIR / f"order_{order.order_number}.csv")
    print(f"order_number={order.order_number}")
    print(f"csv_path={csv_path}")
    print(f"line_count={len(order.lines)}")

    if not execute:
        print("dry_run_only=True")
        print("No Fishbowl import was executed.")
        return None

    try:
        import_sales_order(csv_path)
    except DuplicateOrderError as exc:
        sys.exit(f"import refused: {exc}")

    so = find_sales_order(order.order_number)
    if so is None:
        sys.exit(f"import returned success but no SO found for PO {order.order_number}")

    subject, body, html_body = build_notification(order, so, sales_order_items(so["id"]))
    send_notification(subject, body, ORDER_NOTIFY_TO, html_body)
    print(f"sales_order={so['num']}")
    print(f"notification_sent_to={ORDER_NOTIFY_TO}")
    return so


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fishbowl order import pipeline")
    parser.add_argument("email", type=Path, help="saved .eml or .msg of the customer order email")
    parser.add_argument("--pdf", type=Path, default=None, help="optional PDF attachment with the order")
    parser.add_argument("--execute", action="store_true", help="actually import and notify")
    args = parser.parse_args()

    run(args.email, args.pdf, args.execute)
