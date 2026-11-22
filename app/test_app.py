import unittest

from app import build_event


class BuildEventTest(unittest.TestCase):
    def test_valid_order_becomes_event(self):
        event = build_event({"item": "book", "qty": 2})
        self.assertEqual(event["type"], "OrderPlaced")
        self.assertEqual(event["item"], "book")
        self.assertEqual(event["qty"], 2)
        self.assertTrue(event["orderId"])

    def test_client_order_id_is_kept_for_deduplication(self):
        event = build_event({"orderId": "order-42", "item": "pen"})
        self.assertEqual(event["orderId"], "order-42")

    def test_missing_item_is_rejected(self):
        with self.assertRaises(ValueError):
            build_event({"qty": 1})

    def test_bad_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            build_event({"item": "pen", "qty": 0})
        with self.assertRaises(ValueError):
            build_event({"item": "pen", "qty": "many"})


if __name__ == "__main__":
    unittest.main()
