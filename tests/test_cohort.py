import csv
import tempfile
import unittest
from pathlib import Path

from cohort import build_cohort
from retailsense import make_fixture, prepare, write_csv


class CohortTests(unittest.TestCase):
    def test_future_changes_and_row_order_preserve_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / 'raw'
            make_fixture(raw)
            receipts = []
            for run in range(2):
                prepared = root / f'prepared-{run}'
                prepare(raw, prepared)
                result = build_cohort(prepared, root / f'cohort-{run}',
                                      ('SYNTH_CA', 'SYNTH_TX'), cutoff=308, quota=2)
                self.assertEqual(result['series'], 12)
                self.assertEqual(result['rows'], 12 * 420)
                receipts.append(result)
                if run == 0:
                    sales = raw / 'sales_train_evaluation.csv'
                    with sales.open() as handle:
                        records = list(csv.DictReader(handle))
                    for row in records:
                        row['d_309'] = '50000'
                    write_csv(sales, list(records[0]), reversed(records))
            self.assertEqual(receipts[0]['membership_sha256'], receipts[1]['membership_sha256'])
            self.assertNotEqual(receipts[0]['units'], receipts[1]['units'])
