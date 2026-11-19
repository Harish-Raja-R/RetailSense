import unittest
import numpy as np
from inventory import replay, review


class InventoryTests(unittest.TestCase):
    def test_receipt_timing_and_outstanding_orders(self):
        units = np.ones(100)
        daily, orders = replay(units,14,'forecast_cover',0,start=29,end=56)
        self.assertEqual(orders[0]['suggested_units'],7)
        self.assertEqual(orders[1]['on_order'],7)
        self.assertEqual(orders[1]['suggested_units'],7)
        self.assertEqual(sum(r['receipts'] for r in daily[:14]),0)
        self.assertEqual(daily[14]['receipts'],7)

    def test_future_spike_cannot_change_order_and_unfilled_demand_is_lost(self):
        units = np.ones(100)
        units[28] = 100
        daily, orders = replay(units,7,'forecast_cover',0,start=29,end=56)
        self.assertEqual(orders[0]['suggested_units'],0)
        self.assertEqual(daily[0]['lost'],86)
        self.assertEqual(daily[0]['closing'],0)
        self.assertEqual(daily[1]['demand'],1)
        self.assertEqual(review(np.zeros(28),0,0,'forecast_cover',7,3)['suggested_units'],0)
