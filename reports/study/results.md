Feeder of 24 households, 2012-10-01 to 2013-03-31. Forecasts: XGBoost + calibrated quantiles (out of sample).
Grid-only bill for the feeder over the period: ₹593,786.

**1. Strategies** (saving = households together vs billing the same meters with no market)

| Volume rule | Price rule | Saving ₹ | ± sd | ₹ / household / year | Share of oracle | Traded kWh | Over-committed kWh | Price ₹ (sd) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Seasonal naive | truthful | 12,889 | 0 | 1,077 | 43% | 5,536 | 4,305 | 5.75 (0.00) |
| Seasonal naive | shaded | 12,889 | 0 | 1,077 | 43% | 5,536 | 4,305 | 5.75 (0.00) |
| Seasonal naive | random | 12,262 | 67 | 1,025 | 41% | 5,528 | 4,421 | 6.41 (0.38) |
| Forecast P50 | truthful | 21,372 | 0 | 1,786 | 71% | 5,605 | 2,351 | 5.75 (0.00) |
| Forecast P50 | shaded | 21,372 | 0 | 1,786 | 71% | 5,605 | 2,351 | 5.75 (0.00) |
| Forecast P50 | random | 20,868 | 41 | 1,744 | 69% | 5,598 | 2,436 | 6.37 (0.37) |
| Newsvendor quantile | truthful | 21,372 | 0 | 1,786 | 71% | 5,605 | 2,351 | 5.75 (0.00) |
| Newsvendor quantile | shaded | 21,372 | 0 | 1,786 | 71% | 5,605 | 2,351 | 5.75 (0.00) |
| Newsvendor quantile | random | 23,128 | 33 | 1,933 | 77% | 6,263 | 2,866 | 6.26 (0.39) |
| Perfect foresight (oracle) | truthful | 30,254 | 0 | 2,528 | 100% | 5,508 | 0 | 5.75 (0.00) |
| Perfect foresight (oracle) | shaded | 30,254 | 0 | 2,528 | 100% | 5,508 | 0 | 5.75 (0.00) |
| Perfect foresight (oracle) | random | 30,226 | 7 | 2,526 | 100% | 5,500 | 0 | 6.42 (0.38) |

**2. Wheeling charge** (truthful pricing)

- Seasonal naive: households stop gaining at ₹2.33/kWh; the market keeps clearing until the band closes at ₹5.50.
- Newsvendor quantile: households stop gaining at ₹5.15/kWh; the market keeps clearing until the band closes at ₹5.50.
- Recovering the cost of losses alone needs about ₹0.012/kWh.

**3. Incentive compatibility** (everyone truthful but one household, which shades its price)

- with PV (mostly sellers), shading 15% of the band: 7 of 10 gain (mean ₹-41.24, best ₹273.00); everyone else changes by ₹29.51; total welfare by ₹-11.73.
- without PV (buyers), shading 15% of the band: 0 of 14 gain (mean ₹-220.99, best ₹0.00); everyone else changes by ₹204.82; total welfare by ₹-16.17.
- with PV (mostly sellers), shading 40% of the band: 8 of 10 gain (mean ₹90.31, best ₹725.77); everyone else changes by ₹-100.28; total welfare by ₹-9.97.
- without PV (buyers), shading 40% of the band: 0 of 14 gain (mean ₹-220.98, best ₹0.00); everyone else changes by ₹204.81; total welfare by ₹-16.17.