# Reproduce the Phase 2 cohort

Run from the repository root after the README setup. Extract calendar.csv, sell_prices.csv and sales_train_evaluation.csv from the M5 Forecasting Accuracy download into data/raw/m5.

```powershell
.\.venv\Scripts\python.exe prepare_m5.py --raw data/raw/m5 --output outputs/m5-cohort
```

Membership uses total sales through d_1829. Within each store, series with positive historical sales are ordered by units and item ID, then divided into three equal-count bands (up to a one-series difference). A stable hash with seed 42 selects 20 per band. This gives slower sellers equal representation in the sample. An item may fall into different bands in different stores.

cohort.csv records membership and historical units. fact_sales.csv includes the entire sales history for these series, including future evaluation days. Forecasters must slice it at each forecast origin. manifest.json retains source hashes, cohort settings and reconciliation totals. Repeat the preparation command with a fresh output directory and compare membership_sha256. Two independent runs on the supplied archive produced identical manifests. The full sales input contains 30,490 series and 66,927,173 units. The 120 selected series cover 232,920 daily records and 216,614 units. All 41,986 selected records without a weekly price have zero observed sales. Membership SHA-256 is `a7a854d8cce35ce7ea8bdacba0ca03a473c1bc65bf1c95a6e42952293b23240f`.
