# Demand uncertainty and planner assistant

A large order may already cover demand. This experiment ranks each simulated order by how many units could still be uncovered at the 90th percentile of sales over the weekly review interval plus supplier lead time. The existing order policy remains the benchmark.

From a checkout with the Phase 5 outputs, run the following in your project Python environment:

```powershell
python planner_risk.py
python powerbi/build_report.py --risk outputs/planner-risk/FactRisk.csv --dest outputs/risk-review
```

Open `outputs/risk-review/RetailSense.pbip`, refresh and choose one scenario on Replenishment Queue. P90 appears at individual store-item grain. Exposure is max(0, P90 demand minus simulated stock, inbound units and the suggested order). Summed exposure helps prioritise items. It does not estimate a portfolio-wide 90th percentile. Receipt timing within the window, lost demand and supplier variability can change actual service.

## Model experiment

Two models predict 14-day and 21-day cumulative sales separately. The benchmark takes the empirical 90th percentile of eight prior non-overlapping sales windows. Gradient boosting learns quantiles using recent demand level, volatility and zero-sales frequency. Training labels must end by the forecast origin. Each horizon selects the model with lowest average validation pinball loss at origins 1829, 1857 and 1885, then scores the frozen choice at 1913. Read backtest.csv for loss and observed coverage. A 90th percentile target alone does not guarantee 90% coverage. The final fit uses observed history through day 1941.

## Ask the local agent

Use an already installed tool-capable Ollama model running on the same computer. Substitute its local name below.

```powershell
python planner_agent.py --model YOUR_LOCAL_MODEL "Which five orders have the most uncovered units in TX_1 under forecast_cover_L7_B3? Explain the first calculation."
```

The model can request ranked order evidence or holdout calibration results and follow up using those results. The program prints the tool arguments and exact rows alongside generated text for verification. The agent reads two fixed CSV exports and has no purchasing tools. A follow-up question to practise is “How often did observed demand fall below the selected upper estimate on the holdout for each lead time?”

The automated fixture checks the model comparison, a known exposure calculation and the agent loop with scripted model replies. The real-data pilot below verifies model performance and the evidence lookup. Live language-model responses and the revised Desktop screen still require acceptance checks.

## M5 pilot results

The 120 item-store series were evaluated at origin 1913. The three preceding validation origins selected the boosted quantile model at both horizons. Pinball loss scores the 90th-percentile estimate and weights underestimates more heavily. Lower is better. Coverage is the fraction of series whose observed total fell at or below the forecast bound.

| Horizon | Baseline holdout loss | Boosted holdout loss | Baseline coverage | Boosted coverage |
|---|---:|---:|---:|---:|
| 14 days | 2.564 | 2.303 | 82.50% | 86.67% |
| 21 days | 4.642 | 4.293 | 78.33% | 85.83% |

Both selected bounds fell short of the nominal 90% coverage on this single holdout. The pilot reconciled all 720 scenario rows. In TX_1 under forecast_cover_L7_B3, the highest-ranked item FOODS_3_444 had 284 units of estimated upper demand against 99 simulated on hand, zero inbound and 135 suggested. Its 50 uncovered units flag it for review. This quantity is conditional on the scenario assumptions.

All ten automated tests passed on the Windows project runtime. The risk report was generated locally. The order evidence above came from the agent's read-only lookup function. Live language generation and rendering of this revised report are pending.
