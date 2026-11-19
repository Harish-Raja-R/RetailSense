# RetailSense

Retail demand forecasting, inventory intelligence and replenishment analysis.

## Planner AI experiment

[Demand uncertainty and local planner assistant](PLANNER.md) adds a quantile forecasting experiment, an evidence-backed agent and a risk-ranked Power BI queue.

## Current milestone

Harish verified all four pages in Power BI Desktop. Phase 7 reproduced the pipeline and report project from the pinned GitHub source. Start with the [three-minute interview walkthrough and clean setup](PHASE7.md). See [cohort preparation](PHASE2.md) and the [Desktop verification guide](powerbi/PHASE6.md).

## Reproduce the forecast comparison

After setup, run these commands in the project directory. Use a fresh output directory for each run.

```powershell
.\.venv\Scripts\python.exe prepare_m5.py --raw data/raw/m5 --output outputs/m5-cohort
.\.venv\Scripts\python.exe forecast.py --cohort outputs/m5-cohort --output outputs/forecast
```

The 120 item-store series come from CA_1 and TX_1. At each origin the weekly naive model repeats the last seven observations and the trailing mean repeats the last 28-day average. The pooled Poisson model learns from completed 28-day windows using recent sales levels, the target weekday's historical average and the forecast horizon. Its regularization strength was fixed at 0.01. All three receive history ending on the origin day.

| Model | Pooled validation WAPE | Holdout WAPE | Holdout MAE |
|---|---:|---:|---:|
| Trailing 28-day mean | 84.74% | 94.77% | 1.065 |
| Poisson regression | 86.94% | 95.29% | 1.071 |
| Weekly seasonal naive | 98.16% | 106.30% | 1.195 |

Three validation windows selected the trailing mean before evaluation on days 1914 through 1941. Across 3,360 held-out daily observations, recorded sales totalled 3,777 units and the selected forecast totalled 3,388 units. Errors in opposite directions cancel in that net difference of 389 units. WAPE instead sums absolute errors before dividing by total observed sales. These results describe one cohort and one holdout window.

Local exports include daily predictions and results by volume band, horizon and origin. Bias is forecast minus actual, averaged over item-store days. WAPE is blank for groups with zero actual sales. Test coverage includes a future-sales perturbation and an exact weekly-baseline alignment check.

## Inventory simulation

Run `python inventory.py` after the forecast comparison. Outputs are written to `outputs/inventory`. The simulator treats historical sales as a demand proxy. Each series starts on day 1886 with 14 days of assumed stock at its trailing sales rate and zero inbound units. A 28-day warm-up precedes the scored replay on days 1914 through 1941. Receipts arrive before the weekly review. Orders use sales observed through the previous day. Unfilled units are lost. Lead times are constant, deliveries arrive in full, and orders are rounded up to whole units.

The fixed policy targets 14 days of cover. The forecast policy targets the seven-day review interval plus supplier lead time, with zero or three additional days of buffer. Both subtract on-hand and outstanding units. At seven-day lead time, the unbuffered policies are mathematically identical. Scenario cost is expressed in illustrative points: 0.02 per closing-stock unit per day plus 1 per lost unit. Holding costs, supplier constraints and unavailable demand during historical stockouts are uncertain.

| Lead days | Policy | Buffer days | Simulated fill rate | Average closing units across cohort | Cost points |
|---:|---|---:|---:|---:|---:|
| 7 | Fixed / forecast | 0 | 71.35% | 735.61 | 1493.94 |
| 7 | Forecast | 3 | 78.42% | 1073.21 | 1416.00 |
| 14 | Fixed | 0 | 54.06% | 509.57 | 2020.36 |
| 14 | Forecast | 0 | 69.90% | 983.29 | 1687.64 |
| 14 | Forecast | 3 | 74.16% | 1282.93 | 1694.44 |

The next-order export records a counterfactual review on day 1942. Filter to one scenario before summing suggested units. Each row gives the trailing mean, target, assumed on-hand stock, open orders and suggested quantity. No purchasing transactions are executed.

## Setup on Windows

Install 64-bit Python 3.12, then open PowerShell in this directory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe retailsense.py fixture --raw data/synthetic
.\.venv\Scripts\python.exe retailsense.py prepare --raw data/synthetic --output outputs/synthetic-run-001
```

Use a fresh output directory for every run. Fixture generation refuses to replace
existing data files. Real M5 inputs belong in a separate directory containing
`sales_train_evaluation.csv`, `calendar.csv` and `sell_prices.csv`.

```powershell
.\.venv\Scripts\python.exe retailsense.py prepare --raw data/m5 --output outputs/m5-run-001
```

The source label remains `user_supplied_m5_unverified_source` until provenance is
independently verified. Source hashes identify the bytes used in a run. They do
not establish authenticity. The marker `SYNTHETIC.json` identifies generated data.

## Data contract

Sales keys are item, store and M5 day. Calendar keys are M5 day. Prices have one
row per item, store and week. Missing, negative, fractional or nonfinite sales fail
validation. Calendar matches are required. Price gaps remain null and are counted.
Zero sales remain observed zeros. Count and unit totals must reconcile after joins.

The SQL unpivot explicitly includes nulls. Otherwise missing sales could disappear
before validation, producing a falsely clean dataset. Prices join by week because
M5 prices are weekly, while sales are daily.

## Planned experiment

Select 120 series from CA_1 and TX_1 across three volume bands using only data
through d_1829. Save the selection seed and membership. Compare weekly seasonal
naive, trailing 28-day mean and pooled Poisson regression with 28-day forecasts.
Validation origins are d_1829, d_1857 and d_1885. Freeze selection before evaluating
d_1914 through d_1941 from origin d_1913. Report WAPE, MAE and signed bias.

Inventory experiments will use sales as a demand proxy, explicit assumed stock and
lead times, and shared starting conditions. Daily conservation and delayed arrivals
must pass tests. Evaluate lead times of 7 and 14 days. Simulated outcomes must remain
labelled throughout the report.

## Seven-day delivery sequence

1. Runtime, synthetic fixture and ingestion tests.
2. Real-data checks, DuckDB transformations and fixed cohort.
3. Time splits, baselines, regression and leakage tests.
4. Inventory simulation, assumptions and order recommendations.
5. Frozen evaluation, manifests and dimensional exports.
6. Four Power BI pages, DAX and SQL reconciliation.
7. Clean reproduction and interview walkthrough.

The four report pages will cover Sales and Assortment, Forecast Performance,
Inventory Scenarios and Replenishment Queue. Dimensions will include Date,
Product, Store, Model and Scenario. Facts will retain explicit grains and forecast
origins to prevent duplicated actuals across model alternatives.

## Reference and originality

The reference project informed the initial audit and experiment discussion.
RetailSense implementation is independently authored. Reference metrics have not
been reproduced or claimed as RetailSense outcomes.

- https://github.com/SiddhantK543/Retail-Replenishment-Lab
- https://www.kaggle.com/competitions/m5-forecasting-accuracy/data

Review source terms before distributing M5 rows or a report with embedded data.
The repository excludes raw data, generated outputs, credentials and environments.

## Known limits

The foundation loads the full wide input before transformation. Full M5 resource
usage has not been benchmarked. Output export is not transactionally published
across multiple files, so a failed write can leave a partial new run directory.
Only a completed command with a manifest should be treated as a successful run.
Dependency pins describe the tested environment, without constituting a security
or license audit of every transitive dependency.

