"""Freeze the Phase 2 cohort from a completed RetailSense preparation run."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import duckdb


def build_cohort(prepared, output, stores=('CA_1', 'TX_1'), cutoff=1829, quota=20):
    manifest = json.loads((prepared / 'manifest.json').read_text())
    if cutoff < 1 or quota < 1 or len(set(stores)) != 2:
        raise ValueError('Expected two distinct stores and positive cutoff and quota')
    if manifest['quality']['last_sales_day'] <= cutoff:
        raise ValueError('Cutoff must leave observations for evaluation')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary, duckdb.connect() as db:
        stage = Path(temporary) / 'run'
        stage.mkdir()
        db.execute("""CREATE TABLE candidates AS
            SELECT *, CAST(substr(d, 3) AS INTEGER) AS day_index
            FROM read_csv(?) WHERE store_id IN (?, ?)""",
                   [str(prepared / 'fact_sales.csv'), *stores])
        db.execute("""CREATE TABLE cohort AS
            WITH volumes AS (
                SELECT store_id,item_id,sum(units) AS historical_units
                FROM candidates WHERE day_index <= ?
                GROUP BY store_id,item_id HAVING sum(units)>0
            ), bands AS (
                SELECT *, ntile(3) OVER (
                    PARTITION BY store_id ORDER BY historical_units,item_id
                ) AS volume_band FROM volumes
            )
            SELECT * FROM bands QUALIFY row_number() OVER (
                PARTITION BY store_id,volume_band
                ORDER BY sha256('42|' || store_id || '|' || item_id), item_id
            ) <= ?""", [cutoff, quota])
        sizes = db.execute("""SELECT count(*) FROM cohort
            GROUP BY store_id,volume_band""").fetchall()
        if sorted(sizes) != [(quota,)] * 6:
            raise ValueError('Insufficient eligible series in a store or volume band')
        db.execute("""CREATE TABLE selected AS SELECT c.*, b.volume_band
            FROM candidates c JOIN cohort b USING (store_id,item_id)""")
        rows, units = db.execute('SELECT count(*),sum(units) FROM selected').fetchone()
        source = db.execute("""SELECT count(*),sum(units) FROM candidates
            SEMI JOIN cohort USING (store_id,item_id)""").fetchone()
        if source != (rows, units) or rows != 6 * quota * manifest['quality']['last_sales_day']:
            raise ValueError('Cohort rows or units failed reconciliation')
        db.execute("COPY (SELECT * FROM cohort ORDER BY store_id,item_id) TO ? (HEADER)",
                   [str(stage / 'cohort.csv')])
        db.execute("""COPY (SELECT * FROM selected ORDER BY store_id,item_id,day_index)
            TO ? (HEADER)""", [str(stage / 'fact_sales.csv')])
        receipt = dict(source_manifest=manifest, cutoff=cutoff, stores=list(stores),
                       seed=42, per_band=quota, series=quota*6, rows=rows, units=units,
                       membership_sha256=hashlib.sha256((stage/'cohort.csv').read_bytes()).hexdigest())
        (stage / 'manifest.json').write_text(json.dumps(receipt, indent=2))
        stage.rename(output)
        return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_cohort(args.prepared, args.output), indent=2))
