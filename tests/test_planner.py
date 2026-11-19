import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from planner_agent import ask
from planner_risk import run


class PlannerTest(unittest.TestCase):
    def test_constant_sales_and_evidence_loop(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            membership = b'store_id,item_id,volume_band\nS,I,1\n'
            (base/'cohort.csv').write_bytes(membership)
            (base/'manifest.json').write_text(json.dumps(dict(cutoff=1829,
                membership_sha256=hashlib.sha256(membership).hexdigest())))
            pd.DataFrame(dict(store_id='S',item_id='I',units=2,
                              d=['d_'+str(i) for i in range(1,1942)])).to_csv(base/'fact_sales.csv',index=False)
            queue = [dict(store_id='S',item_id='I',day=1942,lead_days=d,scenario=f's{d}_{i}',
                          on_hand=7,on_order=4,suggested_units=10) for d in [7,14] for i in range(3)]
            pd.DataFrame(queue).to_csv(base/'orders.csv',index=False)
            run(base,base/'orders.csv',base/'out')
            audit = pd.read_csv(base/'out/backtest.csv')
            self.assertEqual(len(audit),16)
            self.assertTrue(np.allclose(audit.pinball,0))
            self.assertEqual(audit.selected.sum(),2)
            def mock_chat(messages):
                if messages[-1]['role'] == 'tool':
                    return {'role':'assistant','content':'Review the returned order.'}
                return {'role':'assistant','tool_calls':[{'function':{'name':'inspect_orders',
                               'arguments':{'scenario':'s7_0'}}}]}
            answer = ask(base/'out','Which order?',mock_chat)
            self.assertEqual(answer['evidence'][0]['rows'][0]['exposure_units'],7)
