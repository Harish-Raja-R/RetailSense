"""Weekly lost-sales inventory replay for the selected Phase 3 mean forecast."""
import argparse
import hashlib
import json
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


def review(history, stock, inbound, policy, lead, buffer_days):
    daily = float(history[-28:].mean())
    cover = 14 if policy == 'fixed_cover' else lead + 7
    target = ceil(daily * (cover + buffer_days))
    return dict(mean_daily=daily, target=target, on_hand=stock, on_order=inbound,
                suggested_units=max(0, target - stock - inbound))


def replay(units, lead, policy, buffer_days, start=1886, end=1941):
    # Array index zero corresponds to d_1. Reviews precede that day's demand.
    if lead < 1 or start < 29 or end > len(units) or start > end:
        raise ValueError('Invalid replay interval or supplier lead time')
    stock = ceil(14 * units[start-29:start-1].mean())
    inbound = {}
    ledger, orders = [], []
    for day in range(start, end+2):
        opening = stock
        receipts = inbound.pop(day, 0)
        stock += receipts
        if (day-start) % 7 == 0:
            order = review(units[day-29:day-1], stock, sum(inbound.values()),
                           policy, lead, buffer_days)
            orders.append(dict(day=day, arrival_day=day+lead, **order))
            inbound[day+lead] = order['suggested_units']
        if day > end:
            break
        demand = int(units[day-1])
        fulfilled = min(stock, demand)
        stock -= fulfilled
        ledger.append(dict(day=day, opening=opening, receipts=receipts, demand=demand,
                           fulfilled=fulfilled, lost=demand-fulfilled, closing=stock))
    return ledger, orders


def run(cohort, selection, output):
    chosen = json.loads(selection.read_text())
    digest = hashlib.sha256((cohort/'cohort.csv').read_bytes()).hexdigest()
    if (chosen['model'] != 'mean_28' or chosen['membership_sha256'] != digest
            or chosen['holdout_origin'] != 1913):
        raise ValueError('Expected the verified Phase 3 cohort and selected mean forecast')
    sales = pd.read_csv(cohort/'fact_sales.csv')
    sales['day'] = sales.d.str[2:].astype(int)
    matrix = sales.pivot(index=['store_id','item_id'], columns='day', values='units')
    if list(matrix.columns) != list(range(1,1942)) or matrix.isna().any().any():
        raise ValueError('Incomplete M5 replay input')
    members = pd.read_csv(cohort/'cohort.csv').set_index(['store_id','item_id']).sort_index()
    if not matrix.index.equals(members.index):
        raise ValueError('Sales series differ from selected cohort')
    ledgers, orders = [], []
    for (store, item), row in matrix.iterrows():
        for lead in (7, 14):
            for policy, buffer in [('fixed_cover',0), ('forecast_cover',0), ('forecast_cover',3)]:
                keys = dict(store_id=store, item_id=item, lead_days=lead, policy=policy,
                            buffer_days=buffer, scenario=f'{policy}_L{lead}_B{buffer}')
                ledger, reviews = replay(row.to_numpy(), lead, policy, buffer)
                ledgers.extend(dict(**keys, **r) for r in ledger if r['day'] >= 1914)
                orders.extend(dict(**keys, **r) for r in reviews if r['day'] >= 1914)
    daily = pd.DataFrame(ledgers)
    queue = pd.DataFrame(orders)
    if not ((daily.opening + daily.receipts - daily.fulfilled == daily.closing).all()
            and (daily.fulfilled + daily.lost == daily.demand).all()):
        raise ValueError('Inventory reconciliation failed')
    summary = daily.groupby('scenario').agg(demand=('demand','sum'), fulfilled=('fulfilled','sum'),
        lost=('lost','sum'), stock_days=('closing','sum')).reset_index()
    summary['fill_rate'] = summary.fulfilled / summary.demand
    summary['avg_daily_stock_all_series'] = summary.stock_days / 28
    summary['assumed_cost_points'] = 0.02 * summary.stock_days + summary.lost
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'run'
        stage.mkdir()
        daily.to_csv(stage/'inventory_daily.csv',index=False)
        queue.to_csv(stage/'order_reviews.csv',index=False)
        queue[queue.day == 1942].sort_values(['scenario','suggested_units'],
            ascending=[True,False]).to_csv(stage/'next_orders.csv',index=False)
        summary.to_csv(stage/'scenarios.csv',index=False)
        stage.rename(output)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=Path('outputs/m5-cohort'))
    p.add_argument('--selection', type=Path, default=Path('outputs/forecast/selection.json'))
    p.add_argument('--output', type=Path, default=Path('outputs/inventory'))
    args = p.parse_args()
    run(args.cohort, args.selection, args.output)
