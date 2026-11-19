"""Export and reconcile the RetailSense reporting model from phase outputs."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb


def export(root, output):
    sources = dict(sales='m5-cohort/fact_sales', predictions='forecast/predictions',
                   inventory='inventory/inventory_daily', orders='inventory/order_reviews',
                   benchmarks='forecast/summary', scenarios='inventory/scenarios',
                   queue='inventory/next_orders')
    tables = {
        'DimDate': """WITH anchor AS (SELECT min(date) AS first_date FROM sales)
            SELECT i AS day_key, first_date + (i-1)::INTEGER AS date
            FROM anchor, range(1,(SELECT max(arrival_day)+1 FROM orders)) r(i)""",
        'DimProduct': 'SELECT DISTINCT item_id,dept_id,cat_id FROM sales',
        'DimStore': 'SELECT DISTINCT store_id,state_id FROM sales',
        'DimModel': 'SELECT DISTINCT model,selected FROM predictions',
        'DimScenario': 'SELECT DISTINCT scenario,lead_days,policy,buffer_days FROM inventory',
        'FactSales': """SELECT item_id,store_id,substr(d,3)::INTEGER AS day_key,
            units,sell_price,missing_price FROM sales""",
        'FactForecast': """SELECT item_id,store_id,model,target_day AS day_key,origin,horizon,
            split,volume_band,actual,forecast,error,abs_error FROM predictions""",
        'FactInventory': """SELECT item_id,store_id,scenario,day AS day_key,opening,
            receipts,demand,fulfilled,lost,closing FROM inventory""",
        'FactOrder': """SELECT item_id,store_id,scenario,day AS day_key,arrival_day,
            mean_daily,target,on_hand,on_order,suggested_units FROM orders"""
    }
    grains = dict(FactSales=['day_key','item_id','store_id'],
                  FactForecast=['day_key','item_id','store_id','model','origin'],
                  FactInventory=['day_key','item_id','store_id','scenario'],
                  FactOrder=['day_key','item_id','store_id','scenario'])
    dimensions = dict(day_key='DimDate',item_id='DimProduct',store_id='DimStore',
                      model='DimModel',scenario='DimScenario')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as db:
        stage = Path(temp)/'model'
        stage.mkdir()
        for name, source in sources.items():
            db.read_csv(str(root/(source+'.csv'))).create_view(name)
        counts = {}
        for table, query in tables.items():
            path = stage/(table+'.csv')
            db.sql(query).write_csv(str(path),header=True)
            db.read_csv(str(path)).create_view(table)
            counts[table] = db.sql(f'SELECT count(*) FROM {table}').fetchall()[0][0]
        def check(query, label):
            if db.sql(query).fetchall()[0][0]:
                raise ValueError(label)
        for key, dim in dimensions.items():
            check(f'SELECT count(*)-count(DISTINCT {key}) FROM {dim}',dim)
        for fact, keys in grains.items():
            cols = ','.join(keys)
            check(f'SELECT count(*) FROM (SELECT {cols} FROM {fact} GROUP BY ALL HAVING count(*)>1)',fact)
            for key in set(keys) & dimensions.keys():
                check(f'SELECT count(*) FROM {fact} ANTI JOIN {dimensions[key]} USING({key})',fact+' '+key)
        check("""SELECT count(*) FROM sales s JOIN DimDate d ON d.day_key=substr(s.d,3)::INT
            WHERE s.date<>d.date""",'Date alignment')
        receipt = json.loads((root/'m5-cohort/manifest.json').read_text())
        if (counts['FactSales'],db.sql('SELECT sum(units) FROM FactSales').fetchall()[0][0]) != (
                receipt['quality']['rows'],receipt['quality']['units']):
            raise ValueError('Sales reconciliation')
        check("""WITH x AS (SELECT split,model,sum(abs_error)/sum(actual) wape,
            avg(abs_error) mae,avg(error) bias,count(*) n FROM FactForecast GROUP BY ALL)
            SELECT count(*) FROM x FULL JOIN benchmarks b USING(split,model)
            WHERE x.n IS NULL OR b.observations IS NULL OR n<>observations OR
            abs(x.wape-b.wape)>1e-8 OR abs(x.mae-b.mae)>1e-8 OR
            abs(x.bias-b.bias_units_per_day_series)>1e-8""",'Forecast reconciliation')
        check("""WITH x AS (SELECT scenario,sum(fulfilled)/sum(demand) fill,
            sum(closing)/count(DISTINCT day_key) stock,sum(lost) lost_units,
            sum(closing)*0.02+sum(lost) cost FROM FactInventory GROUP BY ALL)
            SELECT count(*) FROM x FULL JOIN scenarios s USING(scenario)
            WHERE fill IS NULL OR fill_rate IS NULL OR abs(fill-fill_rate)>1e-8
            OR abs(stock-avg_daily_stock_all_series)>1e-8 OR lost_units<>lost
            OR abs(cost-assumed_cost_points)>1e-8""",'Inventory reconciliation')
        check("""WITH latest AS (SELECT * FROM FactOrder WHERE day_key=(SELECT max(day_key) FROM FactOrder))
            SELECT count(*) FROM latest FULL JOIN queue q USING(store_id,item_id,scenario)
            WHERE latest.suggested_units IS DISTINCT FROM q.suggested_units""",'Order reconciliation')
        (stage/'checks.json').write_text(json.dumps(counts,indent=2))
        stage.rename(output)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('outputs'))
    parser.add_argument('--output',type=Path,default=Path('outputs/powerbi'))
    args = parser.parse_args()
    print(export(args.root,args.output))
