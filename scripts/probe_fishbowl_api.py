import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.fishbowl_api import FishbowlApiClient, FishbowlApiError, FishbowlAuthError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def main() -> int:
    client = FishbowlApiClient.from_env()
    print(f"host={client.host}")
    print(f"port={client.port}")
    try:
        login = client.login()
        print("login_status=1000")
        print(f"server_version={login.server_version}")
        print(f"user_id={login.user_id}")
        print(f"full_name={login.full_name}")

        import_names = client.get_import_list()
        print("import_list_status=1000")
        print(f"has_import_sales_order={'ImportSalesOrder' in import_names}")
        print(f"has_import_sales_order_details={'ImportSalesOrderDetails' in import_names}")
        print(f"import_count={len(import_names)}")

        header_rows = client.get_import_headers("ImportSalesOrder")
        print("import_header_status=1000")
        print(f"import_header_rows={len(header_rows)}")
        for idx, row in enumerate(header_rows, 1):
            print(f"header_row_{idx}={row}")

        client.logout()
        print("logout_status=1000")
        return 0
    except FishbowlAuthError as exc:
        print(f"login_outer_status={exc.status_code}")
        print(f"login_status={exc.status_code}")
        print(f"login_message={exc.status_message}")
        return 1
    except FishbowlApiError as exc:
        print(f"api_status={exc.status_code}")
        print(f"api_message={exc.status_message}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
