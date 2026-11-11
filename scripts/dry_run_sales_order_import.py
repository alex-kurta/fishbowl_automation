import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, TRAINING_DIR
from pipeline.fishbowl_api import FishbowlApiClient
from pipeline.stages.extract import extract_order
from pipeline.stages.normalize import order_to_csv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def connect_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3305")),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "fishbowl_demo"),
        charset="utf8mb4",
    )


def parse_csv_row(row_text: str) -> list[str]:
    return next(csv.reader([row_text]))


def main() -> int:
    msg_path = TRAINING_DIR / "sample_order_website.msg"
    out_path = OUTPUT_DIR / "order_dryrun.csv"

    order = extract_order(msg_path)
    order_to_csv(order, out_path)

    with open(out_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    client = FishbowlApiClient.from_env()
    login = client.login()
    import_headers = client.get_import_headers("ImportSalesOrder")
    client.logout()

    header1 = parse_csv_row(import_headers[0])
    header2 = parse_csv_row(import_headers[1])

    generated_header1 = rows[0]
    generated_header2 = rows[1]
    item_prefix_ok = generated_header2[:len(header2)] == header2
    item_padding_ok = all(cell == "" for cell in generated_header2[len(header2):])

    sku_rows = rows[3:]
    skus = [row[2] for row in sku_rows]

    with connect_db() as conn:
        with conn.cursor() as cur:
            product_hits = {}
            for sku in skus:
                cur.execute("SELECT COUNT(*) FROM product WHERE num = %s", (sku,))
                product_hits[sku] = cur.fetchone()[0] > 0

            checks = {}
            for label, query, value in [
                ("carrier_exists", "SELECT COUNT(*) FROM carrier WHERE name = %s", rows[2][18]),
                ("location_group_exists", "SELECT COUNT(*) FROM locationgroup WHERE name = %s", rows[2][30]),
                ("ship_terms_exists", "SELECT COUNT(*) FROM shipterms WHERE name = %s", rows[2][25]),
                ("payment_terms_exists", "SELECT COUNT(*) FROM paymentterms WHERE name = %s", rows[2][26]),
                ("fob_exists", "SELECT COUNT(*) FROM fobpoint WHERE name = %s", rows[2][27]),
                ("uom_exists", "SELECT COUNT(*) FROM uom WHERE code = %s", rows[3][5]),
            ]:
                cur.execute(query, (value,))
                checks[label] = cur.fetchone()[0] > 0

    print(f"server_version={login.server_version}")
    print(f"output_file={out_path}")
    print(f"header_row_1_exact_match={generated_header1 == header1}")
    print(f"header_row_2_prefix_match={item_prefix_ok}")
    print(f"header_row_2_padding_empty={item_padding_ok}")
    print(f"all_rows_have_42_columns={all(len(row) == 42 for row in rows)}")
    print(f"sonum_blank={rows[2][1] == ''}")
    print(f"status_20={rows[2][2] == '20'}")
    print(f"tax_rate_blank={rows[2][19] == ''}")
    print(f"salesman_blank={rows[2][24] == ''}")
    print(f"carrier_service_blank={rows[2][33] == ''}")
    print(f"priority_normal={rows[2][20] == '30'}")
    print(f"fob_origin={rows[2][27] == 'Origin'}")
    print(f"location_group_main={rows[2][30] == 'Main'}")
    print(f"bill_to_state={rows[2][8]}")
    print(f"ship_to_state={rows[2][14]}")
    print(f"states_are_2_char={len(rows[2][8]) == 2 and len(rows[2][14]) == 2}")
    print(f"taxcode_all_blank={all(row[8] == '' for row in sku_rows)}")
    print(f"kititem_all_false={all(row[13] == 'FALSE' for row in sku_rows)}")
    print(f"item_dates_match_order={all(row[11] == rows[2][31] for row in sku_rows)}")
    print(f"carrier_exists={checks['carrier_exists']}")
    print(f"location_group_exists={checks['location_group_exists']}")
    print(f"ship_terms_exists={checks['ship_terms_exists']}")
    print(f"payment_terms_exists={checks['payment_terms_exists']}")
    print(f"fob_exists={checks['fob_exists']}")
    print(f"uom_exists={checks['uom_exists']}")
    print("sku_checks=")
    for sku, ok in product_hits.items():
        print(f"  {sku}={ok}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
