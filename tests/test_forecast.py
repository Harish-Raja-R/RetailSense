import unittest
import numpy as np
import pandas as pd
from forecast import score_window, metrics


class ForecastTests(unittest.TestCase):
    def test_future_sales_cannot_change_forecasts(self):
        history = np.random.default_rng(12).poisson(2, size=(2, 140))
        series = pd.DataFrame({'store_id':['a','b'], 'item_id':['x','x'], 'volume_band':[1,2]})
        first = score_window(history, series, 112)
        history[:, 112:] += 900
        second = score_window(history, series, 112)
        np.testing.assert_allclose(first.forecast, second.forecast)
        self.assertTrue((second.actual == first.actual + 900).all())
        weekly = first[first.model == 'weekly_naive'].forecast.to_numpy().reshape(2,28)
        np.testing.assert_equal(weekly, np.tile(history[:,105:112], (1,4)))

    def test_zero_actual_slice_and_signed_bias(self):
        frame = pd.DataFrame({'model':['x','x'], 'actual':[0,0], 'error':[1,3], 'abs_error':[1,3]})
        row = metrics(frame,['model']).iloc[0]
        self.assertTrue(np.isnan(row.wape))
        self.assertEqual(row.mae, 2)
        self.assertEqual(row.bias_units_per_day_series, 2)
