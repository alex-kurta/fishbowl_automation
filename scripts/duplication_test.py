import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, TRAINING_DIR
from pipeline.stages.extract import extract_order
from pipeline.stages.import_to_fishbowl import DuplicateOrderError, import_sales_order
from pipeline.stages.normalize import order_to_csv

MSG = TRAINING_DIR / "sample_order_forwarded.msg"

order = extract_order(MSG)
csv_path = order_to_csv(order, OUTPUT_DIR / "dup_test.csv")
print(f"extracted order {order.order_number}, CSV: {csv_path}")
print(f"attempting import of PONum {order.order_number} ...")

try:
    so_number = import_sales_order(csv_path)
except DuplicateOrderError as exc:
    print(f"\nRESULT: import refused as expected")
    print(f"  {exc}")
    sys.exit(0)
except NotImplementedError as exc:
    print(f"\nRESULT: import stage not built yet, duplicate guard did not trigger")
    print(f"  {exc}")
    sys.exit(1)

print(f"\nRESULT: FAIL - import succeeded as SO {so_number}, duplicate was not caught")
sys.exit(1)