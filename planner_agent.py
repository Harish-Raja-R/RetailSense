"""Read-only local planner assistant using Ollama tool calls and saved evidence."""
import argparse
import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd


def evidence(folder, name, args):
    if name == 'backtest' and not args:
        table = pd.read_csv(folder/'backtest.csv')
        return table.loc[table.selected].to_dict('records')
    if name != 'inspect_orders' or set(args) - {'scenario', 'store', 'item'}:
        raise ValueError('Unknown tool or arguments')
    if not isinstance(args.get('scenario'), str):
        raise ValueError('Select one scenario')
    table = pd.read_csv(folder/'FactRisk.csv')
    table = table[table.scenario == args['scenario']]
    for key, column in [('store','store_id'), ('item','item_id')]:
        if key in args:
            table = table[table[column] == args[key]]
    columns = ['scenario','store_id','item_id','risk_model','p90_units','on_hand',
               'on_order','suggested_units','exposure_units']
    return table.sort_values(['exposure_units','suggested_units','store_id','item_id'],
                             ascending=[False,False,True,True])[columns].head(5).to_dict('records')


def ask(folder, question, chat):
    scenarios = sorted(pd.read_csv(folder/'FactRisk.csv', usecols=['scenario']).scenario.unique())
    messages = [{'role':'system','content':
                 'Help a retail planner investigate simulated orders. Use tools for every number. '
                 'Ask which scenario if ambiguous. P90 exposure is a screening estimate after the suggested order. '
                 'Never promise service levels. Available scenarios: ' + ', '.join(scenarios)},
                {'role':'user','content':question}]
    transcript = []
    for _ in range(5):
        reply = chat(messages)
        messages.append(reply)
        if not reply.get('tool_calls'):
            return {'response':reply.get('content',''), 'evidence':transcript}
        for call in reply['tool_calls'][:4]:
            fn = call['function']
            result = evidence(folder, fn['name'], fn['arguments'])
            transcript.append({'tool':fn['name'],'arguments':fn['arguments'],'rows':result})
            messages.append({'role':'tool','tool_name':fn['name'],'content':json.dumps(result)})
    return {'response':'Tool-call limit reached. Review the evidence below.', 'evidence':transcript}


def local_chat(model, messages):
    tools = []
    for name, description, properties, required in [
        ('inspect_orders','Rank exposure or inspect a specific simulated order.',
         ['scenario','store','item'], ['scenario']),
        ('backtest','Get holdout pinball loss and upper-bound coverage for selected models.', [], [])]:
        tools.append({'type':'function','function':{'name':name,'description':description,
                      'parameters':{'type':'object','properties':{k:{'type':'string'} for k in properties},
                                    'required':required}}})
    payload = json.dumps(dict(model=model,messages=messages,tools=tools,stream=False)).encode()
    request = Request('http://127.0.0.1:11434/api/chat', data=payload,
                      headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=120) as response:
        return json.load(response)['message']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question')
    parser.add_argument('--model', required=True, help='Installed tool-capable Ollama model')
    parser.add_argument('--folder', type=Path, default=Path('outputs/planner-risk'))
    args = parser.parse_args()
    try:
        print(json.dumps(ask(args.folder, args.question, lambda msgs: local_chat(args.model, msgs)), indent=2))
    except URLError as error:
        parser.exit(1, f'Local Ollama request failed: {error}\n')
