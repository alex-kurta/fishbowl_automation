import unittest

from pipeline.config import ROOT, SCHEMA_REPORT_DIR, TRAINING_DIR
from pipeline.model import Order, OrderLine


class SmokeTests(unittest.TestCase):
    def test_agents_md_present(self):
        self.assertTrue((ROOT / "AGENTS.md").exists())

    def test_data_dirs_exist(self):
        for path in (TRAINING_DIR, SCHEMA_REPORT_DIR):
            self.assertTrue(path.exists(), f"missing {path}")

    def test_order_model(self):
        order = Order(
            order_number="p",
            customer_name="c",
            lines=[OrderLine(sku="i", quantity=1, unit_price=2.0)],
        )
        self.assertEqual(len(order.lines), 1)
        self.assertEqual(order.lines[0].sku, "i")


if __name__ == "__main__":
    unittest.main()