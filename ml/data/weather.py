"""Open-Meteo ERA5 reanalysis -> half-hourly weather on the panel's UTC grid.

    python -m ml.data.weather        (after ml.data.preprocess)

One request per ERA5 grid cell (0.25 deg) that contains a customer postcode,
cached as raw JSON. Output: data/processed/weather.parquet keyed by
(cell, ts_utc). Join to customers with `cell_of(lat, lon)`.

Cell selection. Open-Meteo's default (`land`) silently moves coastal requests to
a nearby land cell; the Sydney cell holding 52 homes was served from a point
28 km north. We request `nearest` so every home gets the cell it sits in. Tested
both against the meters (2026-10-02): customer-weighted daily correlation of
generation with irradiance was 0.8733 nearest vs 0.8732 land, so this choice is
for transparency, not accuracy.

Alignment. Open-Meteo reports radiation as the mean over the PRECEDING hour, so
the value stamped T covers [T-1h, T) and is assigned to both half hours inside
it. Temperature and cloud cover are instantaneous at T and are linearly
interpolated to each period's midpoint. `check_alignment` proves this against
the meters: generation must correlate best with irradiance at lag zero.

This is reanalysis: what the weather WAS, reconstructed after the fact. No
household bidding at 23:00 for tomorrow could have known it. Milestone 2 must
not feed same-period ERA5 to a forecaster and call the result a forecast.
"""

import json
import time

import numpy as np
import pandas as pd
import requests

from ml import config
from ml.data import preprocess

ERA5_STEP = 0.25
LAG_RANGE = range(-4, 5)  # half hours


def cell_of(lat, lon) -> pd.Series | str:
    """ERA5 grid cell id for a location, e.g. '-33.75_151.25'."""
    clat = np.round(np.asarray(lat) / ERA5_STEP) * ERA5_STEP
    clon = np.round(np.asarray(lon) / ERA5_STEP) * ERA5_STEP
    ids = [f"{a:.2f}_{b:.2f}" for a, b in zip(np.atleast_1d(clat), np.atleast_1d(clon))]
    return ids[0] if np.ndim(lat) == 0 else pd.Series(ids, index=getattr(lat, "index", None))


def fetch_cell(cell: str) -> dict:
    path = config.WEATHER_DIR / f"era5_nearest_{cell}.json"
    if path.exists():
        return json.loads(path.read_text())
    lat, lon = (float(x) for x in cell.split("_"))
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": (preprocess.GRID_START - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "end_date": (preprocess.GRID_END + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "hourly": ",".join(config.WEATHER_HOURLY_MEAN_VARS + config.WEATHER_HOURLY_INSTANT_VARS),
        "models": "era5",
        "cell_selection": "nearest",
        "timezone": "GMT",
    }
    for attempt in range(6):
        r = requests.get(config.OPEN_METEO_URL, params=params, timeout=120)
        if r.status_code == 429:  # rate limited: back off and retry
            time.sleep(30 * (attempt + 1))
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError(f"Open-Meteo kept rate-limiting cell {cell}")
    data = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    time.sleep(10)  # each 3-year request costs ~80 calls against a 600/min quota
    return data


def to_half_hours(data: dict, grid: pd.DatetimeIndex) -> pd.DataFrame:
    hourly = pd.DataFrame(data["hourly"])
    hourly.index = pd.DatetimeIndex(pd.to_datetime(hourly.pop("time"))).tz_localize("UTC")
    expected = pd.date_range(hourly.index[0], hourly.index[-1], freq="h")
    if not hourly.index.equals(expected):
        raise RuntimeError("Open-Meteo hourly series has gaps")

    out = pd.DataFrame(index=grid)
    hour_end = grid.floor("h") + pd.Timedelta(hours=1)
    for var in config.WEATHER_HOURLY_MEAN_VARS:
        out[var] = hourly[var].reindex(hour_end).to_numpy()
    mid = grid + config.PERIOD / 2
    x = hourly.index.asi8.astype(np.float64)
    for var in config.WEATHER_HOURLY_INSTANT_VARS:
        out[var] = np.interp(mid.asi8.astype(np.float64), x, hourly[var].to_numpy(np.float64))
    if out.isna().any().any():
        raise RuntimeError("weather does not cover the panel grid")
    return out


def check_alignment(weather: pd.DataFrame, customers: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Correlate clean-household generation per kWp with their cell's irradiance at each lag."""
    panel = pd.read_parquet(config.PANEL_PARQUET, columns=["customer", "ts_utc", "gen_kwh"])
    clean = customers.loc[customers["clean"]].copy()
    clean["cell"] = cell_of(clean["lat"], clean["lon"])
    panel = panel[panel["customer"].isin(clean["customer"])]
    panel = panel.merge(clean[["customer", "cell", "capacity_kwp"]], on="customer")
    panel["gen_per_kwp"] = panel["gen_kwh"] / panel["capacity_kwp"]
    by_cell = panel.groupby(["cell", "ts_utc"])["gen_per_kwp"].mean()

    ghi = weather.set_index(["cell", "ts_utc"])["shortwave_radiation"]
    rows = []
    for lag in LAG_RANGE:
        shifted = ghi.groupby(level="cell").shift(lag)
        both = pd.concat([by_cell, shifted], axis=1, join="inner").dropna()
        rows.append({"lag_half_hours": lag, "corr": both.corr().iloc[0, 1]})
    lags = pd.DataFrame(rows)
    best = int(lags.loc[lags["corr"].idxmax(), "lag_half_hours"])
    if best != 0:
        raise preprocess.DataCheckFailed(
            f"generation correlates best with irradiance shifted {best} half hours; alignment is wrong")

    # Timing-free skill: how much of day-to-day PV variation does ERA5 explain?
    day = by_cell.reset_index()
    day["date"] = day["ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.date
    daily_gen = day.groupby(["cell", "date"])["gen_per_kwp"].sum()
    w = weather.assign(date=weather["ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.date)
    daily_ghi = w.groupby(["cell", "date"])["shortwave_radiation"].sum()
    daily = pd.concat([daily_gen, daily_ghi], axis=1, join="inner").dropna()
    report["weather_alignment"] = {
        "best_lag_half_hours": best,
        "corr_by_lag": {int(r.lag_half_hours): round(r.corr, 4) for r in lags.itertuples()},
        "daily_gen_vs_ghi_corr": round(float(daily.corr().iloc[0, 1]), 4),
    }
    return lags


def main() -> None:
    customers = pd.read_parquet(config.CUSTOMERS_PARQUET)
    cells = sorted(set(cell_of(customers["lat"], customers["lon"])))
    grid = preprocess.grid_index()
    frames, cell_meta = [], []
    for cell in cells:
        data = fetch_cell(cell)
        lat, lon = (float(x) for x in cell.split("_"))
        if abs(data["latitude"] - lat) > 0.01 or abs(data["longitude"] - lon) > 0.01:
            raise preprocess.DataCheckFailed(f"asked for cell {cell}, Open-Meteo served "
                                             f"{data['latitude']}, {data['longitude']}")
        frames.append(to_half_hours(data, grid).assign(cell=cell))
        cell_meta.append({"cell": cell, "era5_lat": data["latitude"], "era5_lon": data["longitude"]})
        print(f"weather  {cell}  -> ERA5 point {data['latitude']:.3f}, {data['longitude']:.3f}")
    weather = pd.concat(frames).rename_axis("ts_utc").reset_index()
    weather = weather[["cell", "ts_utc"] + config.WEATHER_HOURLY_MEAN_VARS + config.WEATHER_HOURLY_INSTANT_VARS]
    weather.to_parquet(config.WEATHER_PARQUET, index=False)

    report = json.loads(config.QUALITY_JSON.read_text())
    lags = check_alignment(weather, customers, report)
    report["weather_cells"] = cell_meta
    config.QUALITY_JSON.write_text(json.dumps(report, indent=2, default=str))
    lags.to_parquet(config.DATA_PROCESSED / "weather_lag_check.parquet", index=False)
    a = report["weather_alignment"]
    print(f"check    generation vs irradiance peaks at lag {a['best_lag_half_hours']} "
          f"(r = {a['corr_by_lag'][0]}); daily totals r = {a['daily_gen_vs_ghi_corr']}")
    print(f"wrote    {config.WEATHER_PARQUET.relative_to(config.ROOT)}  {len(weather):,} rows, {len(cells)} cells")


if __name__ == "__main__":
    main()
