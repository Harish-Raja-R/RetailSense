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
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f'Choose an empty report destination with --dest: {dest}')
    report = dest/'RetailSense.Report'
    model = dest/'RetailSense.SemanticModel'
    tables, relations, columns = [], [], {}
    dax = (Path(__file__).parent/'measures.dax').read_text()
    measures = dict(re.findall(r'^([^/\n][^=\n]*?) = (.+)$', dax, re.M))
    measures.update({'Holdout WAPE':'CALCULATE([WAPE], FactForecast[split] = "holdout")',
                     'Holdout MAE':'CALCULATE([MAE], FactForecast[split] = "holdout")',
                     'Holdout bias':'CALCULATE([Bias Units Per Item Day], FactForecast[split] = "holdout")'})
    for field, label in [('actual','Observed holdout units'), ('forecast','Selected forecast units')]:
        measures[label] = (f'CALCULATE(SUM(FactForecast[{field}]), DimModel[selected] = TRUE(), '
                           'FactForecast[split] = "holdout")')
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
    pages = {
        'Sales and Assortment': [
            ('Units sold', 'card', {'Values':['Units Sold']}, (24,20,235,128)),
            ('Store selection', 'slicer', {'Values':['DimStore.store_id']}, (275,20,300,128)),
            ('Category selection', 'slicer', {'Values':['DimProduct.cat_id']}, (591,20,665,128)),
            ('Daily unit sales', 'lineChart', {'Category':['DimDate.date'],'Y':['Units Sold']}, (24,164,780,524)),
            ('Units by department', 'clusteredBarChart', {'Category':['DimProduct.dept_id'],'Y':['Units Sold']}, (820,164,436,524)),
        ],
        'Forecast Performance': [
            ('Holdout WAPE by model', 'clusteredBarChart', {'Category':['DimModel.model'],'Y':['Holdout WAPE']}, (24,20,460,310)),
            ('Observed sales and selected forecast · 28-day holdout', 'lineChart', {'Category':['DimDate.date'],'Y':['Observed holdout units','Selected forecast units']}, (500,20,756,310)),
            ('Holdout errors by sales volume band', 'tableEx', {'Values':['DimModel.model','FactForecast.volume_band','Holdout WAPE','Holdout MAE','Holdout bias']}, (24,346,1232,342)),
        ],
        'Inventory Scenarios': [
            ('Simulated fill rate', 'clusteredBarChart', {'Category':['DimScenario.scenario'],'Y':['Simulated Fill Rate']}, (24,20,606,336)),
            ('Average units held across stores', 'clusteredBarChart', {'Category':['DimScenario.scenario'],'Y':['Average Daily Closing Stock']}, (646,20,610,336)),
            ('Service and inventory cost under each assumption', 'tableEx', {'Values':['DimScenario.scenario','Simulated Fill Rate','Simulated Lost Units','Average Daily Closing Stock','Assumed Cost Points']}, (24,372,1232,316)),
        ],
        'Replenishment Queue': [
            ('Choose one simulated scenario', 'slicer', {'Values':['DimScenario.scenario']}, (24,20,540,202)),
            ('Choose a store', 'slicer', {'Values':['DimStore.store_id']}, (580,20,285,202)),
            ('Suggested units · selected scenario', 'card', {'Values':['Next order units']}, (881,20,375,202)),
            ('Day 1942 · largest suggested orders first', 'tableEx', {'Values':['DimScenario.scenario','DimStore.store_id','DimProduct.item_id','Target stock','Stock on hand','Inbound stock','Next order units']}, (24,238,1232,450)),
        ],
    }
    order = []
    for title, visuals in pages.items():
        page = hashlib.sha256(title.encode()).hexdigest()[:20]
        order.append(page)
        parent = definition/'pages'/page
        write(parent/'page.json',{'$schema':schema('report/definition/page','2.0.0'),
              'name':page,'displayName':title,'displayOption':'FitToPage','height':720,'width':1280})
        for idx,(heading,kind,roles,position) in enumerate(visuals):
            name = hashlib.sha256((page+heading).encode()).hexdigest()[:20]
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
            x, y, width, height = position
            query = {'queryState':state}
            if title == 'Replenishment Queue' and kind == 'tableEx':
                query['sortDefinition'] = {'sort':[{'field':state['Values']['projections'][-1]['field'],
                                                     'direction':'Descending'}]}
            def literal(value):
                return {'expr':{'Literal':{'Value':value}}}

            panel = {'title':[{'properties':{'show':literal('true'),
                              'text':literal("'" + heading + "'"),
                              'fontColor':{'solid':{'color':literal("'#123C47'")}},
                              'fontSize':literal('14D')}}],
                     'background':[{'properties':{'show':literal('true'),
                                   'color':{'solid':{'color':literal("'#F5F9F9'")}},
                                   'transparency':literal('0D')}}]}
            write(parent/'visuals'/name/'visual.json',{'$schema':schema('report/definition/visualContainer','2.1.0'),
                'name':name,'position':dict(x=x,y=y,z=idx,width=width,height=height,tabOrder=idx),
                'visual':{'visualType':kind,'query':query,'visualContainerObjects':panel}})
    write(definition/'pages/pages.json',{'$schema':schema('report/definition/pagesMetadata'),
          'pageOrder':order,'activePageName':order[0]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('outputs/powerbi'))
    parser.add_argument('--dest',type=Path,default=Path('outputs/desktop'))
    args = parser.parse_args()
    build(args.data,args.dest)
