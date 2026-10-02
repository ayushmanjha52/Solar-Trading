Task: net energy of one household, 2 half-hours ahead of the last meter reading (the market's gate). Test window 2012-10-01..2013-06-30; units Wh per half hour.

**Feeder, as simulated** (24 households, 314,496 slots)

| Model | MAE | MAE 95% CI | RMSE | Skill vs persistence | Pinball | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 226.4 | 222.2–230.7 | 435.2 | +0.0% |  |  |
| Seasonal naive | 226.5 | 219.3–233.2 | 422.1 | -0.1% |  |  |
| Weekly naive | 241.7 | 234.6–248.9 | 439.6 | -6.8% |  |  |
| Seasonal naive + residual quantiles | 226.5 | 219.3–233.2 | 422.1 | -0.1% | 87.5 | 79.1% |
| XGBoost point | 166.6 | 162.5–170.6 | 293.8 | +26.4% |  |  |
| XGBoost + calibrated quantiles | 159.1 | 154.5–163.5 | 308.1 | +29.7% | 54.0 | 78.1% |
| LSTM quantile | 180.3 | 175.8–184.8 | 349.9 | +20.4% | 60.5 | 80.7% |
| XGBoost + calibrated quantiles + target-slot weather (ORACLE) | 158.9 | 154.3–163.3 | 307.2 | +29.8% | 53.8 | 78.0% |

**PV households, sun up** (124 households, 838,212 slots)

| Model | MAE | MAE 95% CI | RMSE | Skill vs persistence | Pinball | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 232.9 | 229.5–236.9 | 395.5 | +0.0% |  |  |
| Seasonal naive | 278.9 | 270.9–288.6 | 473.2 | -19.7% |  |  |
| Weekly naive | 293.5 | 285.8–303.0 | 489.8 | -26.0% |  |  |
| Seasonal naive + residual quantiles | 278.9 | 270.9–288.6 | 473.2 | -19.7% | 103.4 | 81.2% |
| XGBoost point | 180.3 | 176.6–184.1 | 300.8 | +22.6% |  |  |
| XGBoost + calibrated quantiles | 172.9 | 168.8–177.4 | 314.8 | +25.8% | 58.6 | 77.1% |
| LSTM quantile | 184.1 | 180.0–188.5 | 332.2 | +20.9% | 62.9 | 80.1% |
| XGBoost + calibrated quantiles + target-slot weather (ORACLE) | 171.7 | 167.6–176.2 | 313.4 | +26.3% | 58.1 | 77.0% |

Market agents use: **XGBoost + calibrated quantiles** (lowest validation pinball on the feeder).