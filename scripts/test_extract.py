import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, TRAINING_DIR
from pipeline.stages.extract import extract_order
from pipeline.stages.normalize import order_to_csv

msg_path = TRAINING_DIR / "sample_order_website.msg"
order = extract_order(msg_path)
csv_path = order_to_csv(order, OUTPUT_DIR / "order.csv")

print(f"CSV written to: {csv_path}")
print()
print("=== ORDER SUMMARY ===")
print(f"Order #: {order.order_number}")
print(f"Date: {order.date}")
print(f"Customer: {order.customer_name}")
print(f"Contact: {order.customer_contact}")
print(f"Email: {order.email}")
print(f"Billing: {order.billing.name}, {order.billing.company}")
print(f"  {order.billing.street}")
print(f"  {order.billing.city}, {order.billing.state} {order.billing.zip_code}")
print(f"  {order.billing.country}")
print(f"Shipping: {order.shipping.name}, {order.shipping.company}")
print(f"  {order.shipping.street}")
print(f"  {order.shipping.city}, {order.shipping.state} {order.shipping.zip_code}")
print(f"  {order.shipping.country}")
print(f"Carrier: {order.carrier} {order.carrier_service}")
print(f"Payment: {order.payment_method}")
print(f"Subtotal: ${order.subtotal:.2f}")
print(f"Shipping: ${order.shipping_cost:.2f}")
print(f"Total: ${order.total:.2f}")
print()
print("=== LINE ITEMS ===")
for line in order.lines:
    print(f"  {line.sku:12} {line.description:50} qty={line.quantity} price=${line.unit_price:.2f} option={line.selected_option}")
