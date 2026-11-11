import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, TRAINING_DIR
from pipeline.fishbowl_api import FishbowlApiClient
from pipeline.stages.extract import extract_order
from pipeline.stages.import_to_fishbowl import (
    DuplicateOrderError,
    csv_to_import_rows,
    import_sales_order,
    validate_headers,
)
from pipeline.stages.normalize import order_to_csv

DEFAULT_EMAIL = TRAINING_DIR / "sample_order_website.msg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally import a Fishbowl sales order")
    parser.add_argument(
        "email",
        nargs="?",
        default=str(DEFAULT_EMAIL),
        help="Path to the saved Outlook .msg file",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "order_import_ready.csv"),
        help="Path to write the generated CSV",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually import the sales order into Fishbowl",
    )
    args = parser.parse_args()

    email_path = Path(args.email)
    output_path = Path(args.output)

    order = extract_order(email_path)
    order_to_csv(order, output_path)
    import_rows = csv_to_import_rows(output_path)

    client = FishbowlApiClient.from_env()
    login = client.login()
    try:
        headers = client.get_import_headers("ImportSalesOrder")
        ok, message = validate_headers(headers, import_rows)
        print(f"server_version={login.server_version}")
        print(f"csv_path={output_path}")
        print(f"row_count={len(import_rows)}")
        print(f"header_validation={ok}")
        if not ok:
            print(f"header_validation_message={message}")
            return 1

        print(f"customer_name={order.customer_name}")
        print(f"po_number={order.order_number}")
        print(f"line_count={len(order.lines)}")
        print(f"execute={args.execute}")

        if not args.execute:
            print("dry_run_only=True")
            print("No Fishbowl import was executed.")
            return 0

        try:
            import_sales_order(output_path, client=client)
        except DuplicateOrderError as exc:
            print("duplicate_guard=True")
            print(f"duplicate_detail={exc}")
            return 1

        print("import_status=success")
        return 0
    finally:
        client.logout()


if __name__ == "__main__":
    raise SystemExit(main())
