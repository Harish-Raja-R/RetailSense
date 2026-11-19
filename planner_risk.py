"""Estimate total sales over the review interval plus supplier lead time."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_pinball_loss
from threadpoolctl import threadpool_limits

from forecast import HOLDOUT, KEYS, VALIDATION

Q = 0.90


def inputs(history, days):
    """Non-overlapping historical totals also provide an empirical P90 benchmark."""
    windows = history[:, -8 * days:].reshape(len(history), 8, days).sum(axis=2)
    recent = history[:, -28:]
    baseline = np.quantile(windows, Q, axis=1)
    x = np.column_stack([windows[:, -1], windows.mean(axis=1), baseline,
                         recent[:, -7:].mean(axis=1), recent.std(axis=1),
                         (recent == 0).mean(axis=1)])
    return x, baseline


def estimate(history, days):
    origins = range(8 * days, history.shape[1] - days + 1, 7)
    features, labels = [], []
    for origin in origins:
        features.append(inputs(history[:, :origin], days)[0])
        labels.append(history[:, origin:origin + days].sum(axis=1))
    model = HistGradientBoostingRegressor(loss='quantile', quantile=Q, max_iter=100,
                                          max_leaf_nodes=15, early_stopping=False, random_state=42)
    x, baseline = inputs(history, days)
    with threadpool_limits(limits=2):
        model.fit(np.concatenate(features), np.concatenate(labels))
        fitted = np.maximum(0, model.predict(x))
    return {'empirical': baseline, 'boosted': fitted}


def run(cohort, queue_path, output):
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((cohort/'manifest.json').read_text())
    members = pd.read_csv(cohort/'cohort.csv').set_index(KEYS).sort_index()
    if (manifest['cutoff'] > VALIDATION[0] or hashlib.sha256((cohort/'cohort.csv').read_bytes()).hexdigest()
            != manifest['membership_sha256']):
        raise ValueError('Cohort provenance mismatch')
    fact = pd.read_csv(cohort/'fact_sales.csv')
    fact['day'] = fact.d.str.removeprefix('d_').astype(int)
    matrix = fact.pivot(index=KEYS, columns='day', values='units')
    values = matrix.to_numpy()
    if (not matrix.index.equals(members.index) or list(matrix.columns) != list(range(1, 1942))
            or not np.isfinite(values).all() or (values < 0).any()):
        raise ValueError('Incomplete or invalid cohort history')
    audit, forecasts = [], []
    for days in (14, 21):
        losses = {'empirical': [], 'boosted': []}
        for origin in (*VALIDATION, HOLDOUT):
            if origin == HOLDOUT:
                winner = min(losses, key=lambda name: np.mean(losses[name]))
            actual = values[:, origin:origin + days].sum(axis=1)
            for name, prediction in estimate(values[:, :origin], days).items():
                loss = mean_pinball_loss(actual, prediction, alpha=Q)
                if origin != HOLDOUT:
                    losses[name].append(loss)
                audit.append(dict(days=days, origin=origin, model=name, pinball=loss,
                                  coverage=np.mean(actual <= prediction),
                                  selected=origin == HOLDOUT and name == winner))
        frame = matrix.index.to_frame(index=False)
        frame['lead_days'] = days - 7
        frame['p90_units'] = np.ceil(estimate(values, days)[winner]).astype(int)
        frame['risk_model'] = winner
        forecasts.append(frame)
    queue = pd.read_csv(queue_path)
    if not queue.day.eq(1942).all() or queue.duplicated(KEYS + ['scenario']).any():
        raise ValueError('Expected unique next-review scenario rows on day 1942')
    risk = queue.merge(pd.concat(forecasts), on=KEYS + ['lead_days'], validate='many_to_one', how='left')
    if risk.p90_units.isna().any() or len(risk) != 6 * len(matrix):
        raise ValueError('Incomplete scenario coverage')
    risk['exposure_units'] = (risk.p90_units - risk.on_hand - risk.on_order - risk.suggested_units).clip(lower=0)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'export'
        stage.mkdir()
        risk.to_csv(stage/'FactRisk.csv', index=False)
        pd.DataFrame(audit).to_csv(stage/'backtest.csv', index=False)
        stage.rename(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=Path('outputs/m5-cohort'))
    parser.add_argument('--queue', type=Path, default=Path('outputs/inventory/next_orders.csv'))
    parser.add_argument('--output', type=Path, default=Path('outputs/planner-risk'))
    args = parser.parse_args()
    run(args.cohort, args.queue, args.output)
