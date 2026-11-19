# Phase 6 · Power BI Desktop report

From the project root, after running powerbi_export.py with its default output folder, build the project with:

```powershell
python powerbi/build_report.py
```

Open `outputs/desktop/RetailSense.pbip` in Power BI Desktop and refresh. The generator resolves CSV paths on the machine where it runs. After moving the repository, rebuild into a fresh directory with `--dest outputs/desktop-new`. Use a fresh destination to preserve any manual report edits.

| Page | Desktop acceptance check on the default cohort |
|---|---|
| Sales and Assortment | Category and department totals reconcile to 216,614 units across both stores. |
| Forecast Performance | The 28-day holdout WAPE for mean_28 is 94.77%, versus 95.29% for Poisson and 106.30% for weekly naive. |
| Inventory Scenarios | Compare six simulated policies and lead-time combinations. The seven-day forecast policy with a three-day buffer has a simulated fill rate of 78.42%. |
| Replenishment Queue | Select one scenario. Match item-store suggested units to next_orders.csv for review day 1942. Open orders count toward the target. |

The fresh run produced the same 23 pipeline artifacts after accounting for CSV row order and rounding decimal values to eight places. Structural checks resolved all 26 visual field references across eight visuals. Harish confirmed that the Desktop refresh, four page checks, slicer check and save/reopen check passed. See the [Phase 7 verification record](../PHASE7.md) for the independent pipeline rebuild.

## Planner dashboard revision

To keep a previously saved Desktop report, generate the revised project in an empty directory:

```powershell
python powerbi/build_report.py --dest outputs/planner-review
```

Open `outputs/planner-review/RetailSense.pbip` and refresh. Sales and Assortment now lets you filter the daily trend by store and category. Forecast Performance plots observed holdout sales alongside the validation-selected forecast, counting each item-store-day once. Inventory Scenarios places fill rate and average stock side by side. In Replenishment Queue, select one scenario and use the descending order table to inspect the largest suggested quantities.

On the unfiltered holdout chart the observed daily points should sum to 3,777 units and the selected forecast to 3,388 units. For the queue use the 135-unit example in [the walkthrough](../PHASE7.md). The earlier Desktop sign-off applies to the original layout. The revised layout requires a fresh visual check.
