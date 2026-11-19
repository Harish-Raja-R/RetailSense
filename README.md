# RetailSense

Retail demand forecasting, inventory intelligence and replenishment analysis.

## Current milestone

The ingestion foundation is implemented. It generates an explicitly synthetic fixture,
validates M5-shaped CSV inputs, transforms wide daily sales into a daily SQL fact table,
and exports a source manifest with SHA-256 hashes. Forecasting, inventory simulation
and the Power BI report are planned next. There are no measured M5 results yet.

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
