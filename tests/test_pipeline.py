import csv
import tempfile
import unittest
from pathlib import Path

from retailsense import make_fixture, prepare, write_csv


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / 'raw'
        make_fixture(self.raw)

    def rewrite_sales(self, change):
        path = self.raw / 'sales_train_evaluation.csv'
        with path.open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        change(rows)
        write_csv(path, list(rows[0]), rows)

    def test_fixture_is_reproducible_and_reconciles(self):
        first = prepare(self.raw, self.root / 'first')
        other = self.root / 'other'
        make_fixture(other)
        second = prepare(other, self.root / 'second')
        self.assertEqual(first, second)
        self.assertEqual(first['quality']['rows'], 24 * 420)
        self.assertEqual(first['quality']['missing_price_rows'], 0)
        self.assertEqual(first['data_kind'], 'synthetic')

    def test_duplicate_sales_fail(self):
        self.rewrite_sales(lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValueError, 'Duplicate sales'):
            prepare(self.raw, self.root / 'out')

    def test_missing_sales_fail(self):
        self.rewrite_sales(lambda rows: rows[0].update(d_1=''))
        with self.assertRaisesRegex(ValueError, 'Invalid sales'):
            prepare(self.raw, self.root / 'out')

    def test_negative_sales_fail(self):
        self.rewrite_sales(lambda rows: rows[0].update(d_1=-1))
        with self.assertRaisesRegex(ValueError, 'Invalid sales'):
            prepare(self.raw, self.root / 'out')


if __name__ == '__main__':
    unittest.main()
