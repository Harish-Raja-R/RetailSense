"""Generate the RetailSense Desktop project using the local Phase 5 exports."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/'
DIMS = {'day_key':'DimDate','item_id':'DimProduct','store_id':'DimStore',
        'model':'DimModel','scenario':'DimScenario'}


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def schema(kind, version='1.0.0'):
    return SCHEMA + kind + '/' + version + '/schema.json'


def build(data, dest):
    report = dest/'RetailSense.Report'
    model = dest/'RetailSense.SemanticModel'
    tables, relations, columns = [], [], {}
    dax = (Path(__file__).parent/'measures.dax').read_text()
    measures = dict(re.findall(r'^([^/\n][^=\n]*?) = (.+)$', dax, re.M))
    measures.update({'Holdout WAPE':'CALCULATE([WAPE], FactForecast[split] = "holdout")',
                     'Holdout MAE':'CALCULATE([MAE], FactForecast[split] = "holdout")',
                     'Holdout bias':'CALCULATE([Bias Units Per Item Day], FactForecast[split] = "holdout")'})
    for col, label in [('suggested_units','Next order units'),('target','Target stock'),
                       ('on_hand','Stock on hand'),('on_order','Inbound stock')]:
        measures[label] = (f'IF(HASONEVALUE(DimScenario[scenario]), '
                           f'CALCULATE(SUM(FactOrder[{col}]), FactOrder[day_key] = 1942))')
    strings = set('item_id store_id state_id model scenario split cat_id dept_id policy'.split())
    decimals = set('sell_price forecast error abs_error mean_daily'.split())
    for path in sorted(data.glob('*.csv')):
        name = path.stem
        with path.open(encoding='utf-8-sig') as handle:
            columns[name] = next(csv.reader(handle))
        defs, types = [], []
        for col in columns[name]:
            typ, mtype = 'int64','Int64.Type'
            if col in strings:
                typ, mtype = 'string','type text'
            elif col in decimals:
                typ, mtype = 'double','type number'
            elif col in ('missing_price','selected'):
                typ, mtype = 'boolean','type logical'
            elif col == 'date':
                typ, mtype = 'dateTime','type date'
            defs.append(dict(name=col, dataType=typ, sourceColumn=col, summarizeBy='none'))
            types.append('{"'+col+'", '+mtype+'}')
            if name.startswith('Fact') and col in DIMS:
                relations.append(dict(name=name+'_'+col,fromTable=name,fromColumn=col,
                                      toTable=DIMS[col],toColumn=col))
        file = str(path.resolve()).replace('"','""')
        query = f'Csv.Document(File.Contents("{file}"),[Delimiter=",",Encoding=65001,QuoteStyle=QuoteStyle.Csv])'
        expr = 'Table.TransformColumnTypes(Table.PromoteHeaders('+query+'),{'+', '.join(types)+'},"en-US")'
        table = dict(name=name,columns=defs,partitions=[dict(name=name,mode='import',
                     source=dict(type='m',expression=expr))])
        if name == 'FactSales':
            table['measures'] = [dict(name=k,expression=v,formatString=(
                '0.00%' if k in ('WAPE','Holdout WAPE','Simulated Fill Rate') else '#,0.###'))
                for k,v in measures.items()]
        tables.append(table)
    if len(tables)!=9:
        raise ValueError('Expected nine Phase 5 CSV tables')
    write(model/'model.bim',dict(name='RetailSense',compatibilityLevel=1600,
          model=dict(culture='en-US',defaultPowerBIDataSourceVersion='powerBI_V3',
                     tables=tables,relationships=relations)))
    write(model/'definition.pbism',dict(version='1.0',settings={}))
    write(report/'definition.pbir',dict(version='4.0',datasetReference=dict(
          byPath=dict(path='../RetailSense.SemanticModel'))))
    write(dest/'RetailSense.pbip',dict(version='1.0',artifacts=[dict(report=dict(
          path='RetailSense.Report'))],settings=dict(enableAutoRecovery=True)))
    definition = report/'definition'
    write(definition/'version.json',{'$schema':schema('report/definition/versionMetadata'),'version':'2.0.0'})
    write(definition/'report.json',{'$schema':schema('report/definition/report','2.0.0'),
          'themeCollection':{'baseTheme':{'name':'CY24SU06','reportVersionAtImport':'5.55',
          'type':'SharedResources'}}})
    pages = [
        ('Sales and Assortment', [('clusteredBarChart',{'Category':['DimProduct.cat_id'],'Y':['Units Sold']}),
         ('tableEx',{'Values':['DimStore.store_id','DimProduct.dept_id','Units Sold']})]),
        ('Forecast Performance',[('clusteredBarChart',{'Category':['DimModel.model'],'Y':['Holdout WAPE']}),
         ('tableEx',{'Values':['DimModel.model','FactForecast.volume_band','Holdout WAPE','Holdout MAE','Holdout bias']})]),
        ('Inventory Scenarios',[('clusteredBarChart',{'Category':['DimScenario.scenario'],'Y':['Simulated Fill Rate']}),
         ('tableEx',{'Values':['DimScenario.scenario','Average Daily Closing Stock','Simulated Lost Units','Assumed Cost Points']})]),
        ('Replenishment Queue',[('slicer',{'Values':['DimScenario.scenario']}),
         ('tableEx',{'Values':['DimScenario.scenario','DimStore.store_id','DimProduct.item_id','Target stock','Stock on hand','Inbound stock','Next order units']})])]
    order = []
    for title, visuals in pages:
        page = hashlib.sha256(title.encode()).hexdigest()[:20]
        order.append(page)
        parent = definition/'pages'/page
        write(parent/'page.json',{'$schema':schema('report/definition/page','2.0.0'),
              'name':page,'displayName':title,'displayOption':'FitToPage','height':720,'width':1280})
        for idx,(kind,roles) in enumerate(visuals):
            name = hashlib.sha256((page+kind).encode()).hexdigest()[:20]
            state = {}
            for role,fields in roles.items():
                projections = []
                for field in fields:
                    entity, prop = ('FactSales',field) if field in measures else field.split('.')
                    is_measure = field in measures
                    if not is_measure and prop not in columns[entity]:
                        raise ValueError(field)
                    binding = {'Expression':{'SourceRef':{'Entity':entity}},'Property':prop}
                    projections.append({'field':{'Measure' if is_measure else 'Column':binding},
                                        'queryRef':entity+'.'+prop})
                state[role] = {'projections':projections}
            split = 140 if title == 'Replenishment Queue' else 335
            write(parent/'visuals'/name/'visual.json',{'$schema':schema('report/definition/visualContainer','2.1.0'),
                'name':name,'position':dict(x=32,y=20 if idx==0 else split+30,z=idx,
                width=1216,height=split if idx==0 else 660-split,tabOrder=idx),
                'visual':{'visualType':kind,'query':{'queryState':state}}})
    write(definition/'pages/pages.json',{'$schema':schema('report/definition/pagesMetadata'),
          'pageOrder':order,'activePageName':order[0]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('outputs/powerbi'))
    parser.add_argument('--dest',type=Path,default=Path('outputs/desktop'))
    args = parser.parse_args()
    build(args.data,args.dest)
