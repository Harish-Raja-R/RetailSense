# Reproduce the Phase 2 cohort

Run from the repository root after the README setup. Extract calendar.csv, sell_prices.csv and sales_train_evaluation.csv from the M5 Forecasting Accuracy download into data/m5.

```powershell
.\.venv\Scripts\python.exe retailsense.py prepare --raw data/m5 --output outputs/m5-prepared
.\.venv\Scripts\python.exe cohort.py --prepared outputs/m5-prepared --output outputs/m5-cohort
```

Membership uses total sales through d_1829. Within each store, series with positive historical sales are ordered by units and item ID, then divided into three equal-count bands (up to a one-series difference). A stable hash with seed 42 selects 20 per band. This gives slower sellers equal representation in the sample. An item may fall into different bands in different stores.

cohort.csv records membership and historical units. fact_sales.csv includes the entire sales history for these series, including future evaluation days. Forecasters must slice it at each forecast origin. manifest.json retains source hashes, cohort settings and reconciliation totals. Repeat the second command with a fresh output directory and compare membership_sha256. Full M5 execution is pending access to the three inputs.
