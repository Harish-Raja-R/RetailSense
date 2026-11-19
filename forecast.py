"""Rolling-origin evaluation of 28-day M5 sales forecasts."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

HORIZON = 28
VALIDATION = (1829, 1857, 1885)
HOLDOUT = 1913
KEYS = ['store_id', 'item_id']


def features(history):
    """All target weekdays can be aligned with the last four observed weeks."""
    weeks = history[:, -28:].reshape(-1, 4, 7)
    weekday_level = np.tile(weeks.mean(axis=1), (1, 4))
    level = np.repeat(weeks.mean(axis=(1, 2)), 28)
    recent = np.repeat(weeks[:, -1].mean(axis=1), 28)
    horizon = np.tile(np.arange(1, 29) / 28, len(history))
    return np.column_stack([np.log1p(level), np.log1p(recent),
                            np.log1p(weekday_level.ravel()), horizon])


def predict(history):
    if history.ndim != 2 or history.shape[1] < 56:
        raise ValueError('Need at least 56 daily observations per series')
    # Anchor training windows at the cutoff so the latest label is observed.
    origins = range(history.shape[1] - 28, 27, -28)
    x = np.concatenate([features(history[:, :day]) for day in origins])
    y = np.concatenate([history[:, day:day + 28].ravel() for day in origins])
    if y.any():
        model = PoissonRegressor(alpha=0.01, max_iter=300).fit(x, y)
        fitted = model.predict(features(history)).reshape(-1, 28)
    else:
        fitted = np.zeros((len(history), 28))
    return {'weekly_naive': np.tile(history[:, -7:], (1, 4)),
            'mean_28': np.repeat(history[:, -28:].mean(axis=1)[:, None], 28, axis=1),
            'poisson': fitted}


def score_window(values, series, origin):
    predictions = predict(values[:, :origin])
    actual = values[:, origin:origin + HORIZON].ravel()
    rows = []
    for name, estimate in predictions.items():
        frame = series.loc[series.index.repeat(HORIZON)].reset_index(drop=True)
        frame['model'] = name
        frame['origin'] = origin
        frame['horizon'] = np.tile(np.arange(1, 29), len(series))
        frame['target_day'] = origin + frame.horizon
        frame['forecast'] = estimate.ravel()
        frame['actual'] = actual
        frame['error'] = frame.forecast - frame.actual
        frame['abs_error'] = frame.error.abs()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def metrics(frame, groups):
    sums = frame.groupby(groups, as_index=False).agg(
        observations=('actual', 'size'), units=('actual', 'sum'),
        absolute_error=('abs_error', 'sum'), signed_error=('error', 'sum'))
    sums['wape'] = sums.absolute_error / sums.units.replace(0, np.nan)
    sums['mae'] = sums.absolute_error / sums.observations
    sums['bias_units_per_day_series'] = sums.signed_error / sums.observations
    return sums


def run(cohort, output):
    manifest = json.loads((cohort/'manifest.json').read_text())
    membership = (cohort/'cohort.csv').read_bytes()
    if hashlib.sha256(membership).hexdigest() != manifest['membership_sha256'] or manifest['cutoff'] > VALIDATION[0]:
        raise ValueError('Invalid cohort membership or cutoff')
    fact = pd.read_csv(cohort/'fact_sales.csv')
    fact['target_day'] = fact.d.str.removeprefix('d_').astype(int)
    matrix = fact.pivot(index=KEYS, columns='target_day', values='units')
    series = pd.read_csv(cohort/'cohort.csv').set_index(KEYS)
    if (not matrix.index.equals(series.sort_index().index)
            or list(matrix.columns) != list(range(1, 1942))
            or not np.isfinite(matrix.to_numpy()).all()):
        raise ValueError('Incomplete daily cohort history')
    series = series.loc[matrix.index, ['volume_band']].reset_index()
    values = matrix.to_numpy()
    validation = pd.concat([score_window(values, series, d) for d in VALIDATION])
    ranking = metrics(validation, ['model']).sort_values(['wape', 'model'])
    winner = ranking.iloc[0].model
    test = score_window(values, series, HOLDOUT)
    results = pd.concat([validation.assign(split='validation'), test.assign(split='holdout')])
    results['date'] = results.target_day.map(fact.drop_duplicates('target_day').set_index('target_day').date)
    results['selected'] = results.model.eq(winner)
    summary = metrics(results, ['split', 'model'])
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)/'results'
        stage.mkdir()
        results.to_csv(stage/'predictions.csv', index=False)
        for name, groups in [('summary', []), ('by_band', ['volume_band']), ('by_horizon', ['horizon']), ('by_origin', ['origin'])]:
            metrics(results, ['split', 'model', *groups]).to_csv(stage/f'{name}.csv', index=False)
        (stage/'selection.json').write_text(json.dumps(dict(model=winner,
            validation_origins=VALIDATION, holdout_origin=HOLDOUT,
            membership_sha256=manifest['membership_sha256']), indent=2))
        stage.rename(output)
    print(summary.to_string(index=False))
    print('Validation winner:', winner)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=Path('outputs/m5-cohort'))
    parser.add_argument('--output', type=Path, default=Path('outputs/forecast'))
    args = parser.parse_args()
    run(args.cohort, args.output)
