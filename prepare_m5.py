"""Validate M5 inputs and prepare the two-store cohort with bounded memory."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import numpy as np
import pandas as pd

from retailsense import prepare


def run(raw, output):
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sales = raw / 'sales_train_evaluation.csv'
    days = [f'd_{n}' for n in range(1, 1942)]
    scores = []
    total = 0
    for chunk in pd.read_csv(sales, chunksize=500, dtype={day: 'int32' for day in days}):
        values = chunk[days].to_numpy()
        if np.any(values < 0) or chunk[['item_id', 'store_id']].isna().any().any():
            raise ValueError('Invalid sales or series identifiers')
        total += int(values.sum())
        scores.append(chunk[['item_id', 'store_id']].assign(
            historical_units=values[:, :1829].sum(axis=1),
            full_units=values.sum(axis=1)))
    scores = pd.concat(scores, ignore_index=True)
    if len(scores) != 30490 or scores.duplicated(['item_id', 'store_id']).any():
        raise ValueError('Unexpected M5 series count or duplicate series')
    with duckdb.connect() as db:
        db.register('scores', scores)
        cohort = db.sql("""WITH ranked AS (
            SELECT *,ntile(3) OVER (PARTITION BY store_id ORDER BY historical_units,item_id)
            AS volume_band FROM scores WHERE store_id IN ('CA_1','TX_1') AND historical_units>0)
            SELECT * FROM ranked QUALIFY row_number() OVER (PARTITION BY store_id,volume_band
            ORDER BY sha256('42|' || store_id || '|' || item_id),item_id)<=20
            ORDER BY store_id,item_id""").df()
    if list(cohort.groupby(['store_id','volume_band']).size()) != [20]*6:
        raise ValueError('Unexpected cohort composition')
    keys = set(zip(cohort.store_id, cohort.item_id))
    with TemporaryDirectory(dir=output.parent) as tmp:
        subset = Path(tmp)/'subset'
        subset.mkdir()
        with sales.open(newline='') as src, (subset/sales.name).open('w',newline='') as dest:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dest, reader.fieldnames)
            writer.writeheader()
            writer.writerows(row for row in reader if (row['store_id'],row['item_id']) in keys)
        for name in ['calendar.csv','sell_prices.csv']:
            shutil.copyfile(raw/name,subset/name)
        stage = Path(tmp)/'result'
        manifest = prepare(subset,stage)
        if manifest['quality']['units'] != int(cohort.full_units.sum()) or manifest['quality']['rows'] != 120*1941:
            raise ValueError('Wide sales failed to reconcile with joined cohort')
        # Preserve the original input fingerprints, including the full sales file.
        for name in manifest['files']:
            with (raw/name).open('rb') as handle:
                manifest['files'][name] = dict(bytes=(raw/name).stat().st_size,
                    sha256=hashlib.file_digest(handle,'sha256').hexdigest())
        cohort.drop(columns='full_units').to_csv(stage/'cohort.csv',index=False)
        manifest.update(source='User-supplied M5 competition archive', cutoff=1829, seed=42,
                        full_series=len(scores), full_units=total, selected_series=len(cohort),
                        membership_sha256=hashlib.sha256((stage/'cohort.csv').read_bytes()).hexdigest())
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
        stage.rename(output)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.raw,args.output),indent=2))
