# Power BI reporting model

From the repository root run `python powerbi_export.py` after Phases 2–4. The nine import tables and verification counts are in `outputs/powerbi`. Use a fresh destination for another export with `--output`.

In Power BI Desktop choose Get data → Text/CSV for each of the nine CSVs. Keep their filename stems as table names. In Transform data, set identifiers to text, day keys and unit counts to whole numbers, price, forecast and forecast-error fields to decimal numbers, date to Date, and flags to True/False. Keep the fractional mean_daily and forecast values. In Model view create the following active, single-direction, one-to-many relationships from each dimension to the listed facts. Remove any extra automatically inferred relationships.

| Dimension key (one) | Matching column on the many side | Related facts |
|---|---|---|
| DimDate.day_key | day_key | All four facts |
| DimStore.store_id | store_id | All four facts |
| DimProduct.item_id | item_id | All four facts |
| DimModel.model | model | FactForecast |
| DimScenario.scenario | scenario | FactInventory, FactOrder |

Mark DimDate as the date table using its date column. The active date represents sale, forecast target, simulation, or order review day according to the fact. Forecast origin and order arrival are separate day numbers. Volume band belongs to the item–store forecast observation. A product can occupy different bands across stores.

| Fact | Grain of one row |
|---|---|
| FactSales | Item, store, sales day |
| FactForecast | Item, store, model, forecast origin, target day |
| FactInventory | Item, store, scenario, simulation day |
| FactOrder | Item, store, scenario, review day |

Create each expression in measures.dax using New measure. Format WAPE and fill rate as percentages. Use dimension fields for slicers and chart axes. Choose one model for forecast cards and one scenario for inventory cards. Filter split to holdout for final forecast comparisons. On the replenishment queue, select review day 1942. Opening or closing inventory is a snapshot; average daily portfolio stock first sums across selected products on each day.

## Reconciliation checks in Desktop

With all stores and products selected, Units Sold should equal 216,614. Filter DimModel to mean_28 and split to holdout. WAPE should display 94.77% and MAE 1.065. For forecast_cover_L14_B0, fill rate should display 69.90%, average daily closing stock 983.29, simulated lost units 1,137, and assumed cost 1,687.64 points. For orders, compare the filtered total with the same scenario in outputs/inventory/next_orders.csv.

The exporter reads back all nine CSVs and checks key uniqueness, relationship coverage and totals in DuckDB against earlier phases. DAX execution and visual filter interactions require a Desktop run.
