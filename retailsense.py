"""RetailSense foundation: reproducible input validation and SQL preparation."""

import argparse
import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_fixture(folder):
    """Create artificial M5-shaped files solely for exercising the pipeline."""
    folder.mkdir(parents=True, exist_ok=True)
    names = ['calendar.csv', 'sell_prices.csv', 'sales_train_evaluation.csv']
    if any((folder / name).exists() for name in names):
        raise ValueError('Fixture destination already contains input files')
    rng = random.Random(42)
    days = 420
    calendar = []
    for day in range(1, days + 29):
        actual_date = date(2020, 1, 1) + timedelta(days=day - 1)
        calendar.append({'d': f'd_{day}', 'date': actual_date.isoformat(),
                         'wm_yr_wk': (day - 1) // 7 + 1})
    sales, prices = [], []
    for store in ['SYNTH_CA', 'SYNTH_TX']:
        for item in range(12):
            item_id = f'SYNTH_{item:03d}'
            row = {'id': f'{item_id}_{store}_evaluation', 'item_id': item_id,
                   'store_id': store, 'state_id': store[-2:],
                   'dept_id': 'SYNTH_DEPT', 'cat_id': 'SYNTH_CATEGORY'}
            for day in range(1, days + 1):
                row[f'd_{day}'] = max(0, item // 3 + rng.randint(-2, 3)
                                      + int(day % 7 == 0))
            sales.append(row)
            for week in sorted({r['wm_yr_wk'] for r in calendar}):
                prices.append({'store_id': store, 'item_id': item_id,
                               'wm_yr_wk': week, 'sell_price': 2 + item / 2})
    write_csv(folder / names[0], list(calendar[0]), calendar)
    write_csv(folder / names[1], list(prices[0]), prices)
    write_csv(folder / names[2], list(sales[0]), sales)
    (folder / 'SYNTHETIC.json').write_text(json.dumps({'seed': 42, 'days': days}))


def require_empty(connection, sql, message):
    count = connection.execute(sql).fetchone()[0]
    if count:
        raise ValueError(f'{message}: {count} offending rows')


def prepare(raw, output):
    """Validate first and publish a new run directory after successful checks."""
    if output.exists():
        raise ValueError('Choose a new output directory to preserve previous runs')
    names = ['sales_train_evaluation.csv', 'calendar.csv', 'sell_prices.csv']
    manifest = {'data_kind': 'synthetic' if (raw / 'SYNTHETIC.json').exists()
                else 'user_supplied_m5_unverified_source', 'files': {}}
    for name in names:
        path = raw / name
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        manifest['files'][name] = {'sha256': digest, 'bytes': path.stat().st_size}
    con = duckdb.connect()
    try:
        for table, name in zip(['wide_sales', 'calendar', 'prices'], names):
            con.execute(f'CREATE TABLE {table} AS SELECT * FROM read_csv(?)',
                        [str(raw / name)])
        columns = [row[0] for row in con.execute('DESCRIBE wide_sales').fetchall()]
        day_columns = [c for c in columns if c.startswith('d_') and c[2:].isdigit()]
        days = sorted(int(c[2:]) for c in day_columns)
        if not days or days != list(range(1, max(days) + 1)):
            raise ValueError('Sales day columns must be contiguous from d_1')
        # INCLUDE NULLS is essential so invalid missing observations survive unpivot.
        day_sql = ', '.join(f'"d_{day}"' for day in days)
        con.execute(f'''CREATE TABLE sales AS
            SELECT item_id, store_id, state_id, dept_id, cat_id, d,
                   TRY_CAST(units AS DOUBLE) AS units
            FROM wide_sales UNPIVOT INCLUDE NULLS (units FOR d IN ({day_sql}))''')
        require_empty(con, '''SELECT count(*) FROM sales WHERE units IS NULL
            OR NOT isfinite(units) OR units < 0 OR units != floor(units)
            OR item_id IS NULL OR store_id IS NULL''', 'Invalid sales')
        for table, keys in [('sales', 'item_id,store_id,d'),
                            ('calendar', 'd'), ('prices', 'item_id,store_id,wm_yr_wk')]:
            require_empty(con, f'''SELECT count(*) FROM
                (SELECT {keys} FROM {table} GROUP BY {keys} HAVING count(*) > 1)''',
                f'Duplicate {table} keys')
        require_empty(con, '''SELECT count(*) FROM calendar WHERE d IS NULL
            OR TRY_CAST(date AS DATE) IS NULL OR wm_yr_wk IS NULL''', 'Invalid calendar')
        require_empty(con, '''SELECT count(*) FROM prices WHERE item_id IS NULL
            OR store_id IS NULL OR wm_yr_wk IS NULL OR sell_price IS NULL
            OR NOT isfinite(sell_price) OR sell_price <= 0''', 'Invalid prices')
        require_empty(con, '''SELECT count(*) FROM sales s LEFT JOIN calendar c
            ON s.d=c.d WHERE c.d IS NULL''', 'Missing calendar matches')
        con.execute('''CREATE TABLE fact_sales AS SELECT s.*, CAST(c.date AS DATE) AS date,
            c.wm_yr_wk, p.sell_price, p.sell_price IS NULL AS missing_price
            FROM sales s JOIN calendar c ON s.d=c.d
            LEFT JOIN prices p ON s.item_id=p.item_id AND s.store_id=p.store_id
            AND c.wm_yr_wk=p.wm_yr_wk''')
        original = con.execute('SELECT count(*),sum(units) FROM sales').fetchone()
        joined = con.execute('SELECT count(*),sum(units) FROM fact_sales').fetchone()
        if original != joined:
            raise ValueError('Join reconciliation failed')
        manifest['quality'] = {'rows': joined[0], 'units': joined[1],
                              'missing_price_rows': con.execute(
                                  'SELECT count(*) FROM fact_sales WHERE missing_price'
                              ).fetchone()[0], 'last_sales_day': max(days)}
        output.mkdir(parents=True)
        con.execute("COPY fact_sales TO ? (HEADER, DELIMITER ',')",
                    [str(output / 'fact_sales.csv')])
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        return manifest
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    fixture = sub.add_parser('fixture')
    fixture.add_argument('--raw', type=Path, required=True)
    build = sub.add_parser('prepare')
    build.add_argument('--raw', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'fixture':
        make_fixture(args.raw)
    else:
        print(json.dumps(prepare(args.raw, args.output), indent=2))


if __name__ == '__main__':
    main()
