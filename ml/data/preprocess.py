"""Raw Ausgrid CSVs -> tidy half-hourly panel on a UTC grid.

    python -m ml.data.preprocess

Outputs, in data/processed/:
  panel.parquet        one row per customer x half-hour period
  customers.parquet    one row per customer: capacity, location, quality metrics and flags
  quality_report.json  every check this script ran, with its numbers

Time handling. Read this before changing anything below.

Ausgrid labels each value with the clock time at which the half hour ENDS, in
Sydney local time, which observes daylight saving (Ausgrid data notes, Aug
2014). Every file still has exactly 48 columns per day, so on the six
transition days in the dataset the columns do not match real time:

  spring forward  the columns ending 2:30 and 3:00 are clock times that never
                  happened. Ausgrid fills them with exact zeros. We drop them.
                  Keeping them would teach a forecaster a fake zero-load hour.
  fall back       02:00-03:00 happens twice. Ausgrid sums both passes into one
                  column (values are ~2x their neighbours). We split each value
                  in half across the two real periods and mark them `imputed`.

Downstream code sees only `ts_utc`, the START of each period in UTC, and `slot`,
the 1..48 settlement period index in AEST (UTC+10, no daylight saving).
"""

import json

import numpy as np
import pandas as pd

from ml import config
from ml.data import solar

RAW_TZ = "Australia/Sydney"
DATE_FORMATS = {"2010-2011": "%d-%b-%y", "2011-2012": "%d/%m/%Y", "2012-2013": "%d/%m/%Y"}
CHANNELS = ("GC", "CL", "GG")
N_CUSTOMERS = 300

# Column labels as they appear in the files: the END of each half hour.
INTERVAL_LABELS = [f"{(30 * k // 60) % 24}:{30 * k % 60:02d}" for k in range(1, 49)]

GRID_START = pd.Timestamp("2010-07-01 00:00", tz=config.LOCAL_TZ).tz_convert("UTC")
GRID_END = pd.Timestamp("2013-07-01 00:00", tz=config.LOCAL_TZ).tz_convert("UTC")
N_PERIODS = int((GRID_END - GRID_START) / config.PERIOD)
PERIOD_NS = int(config.PERIOD.total_seconds() * 1e9)

# Ausgrid data notes (Aug 2014), p.2: per-customer annual kWh, 300-home sample.
# Reproducing these is the check that the parser reads the files the way
# Ausgrid meant them. Consumption is GC + CL; GC alone falls ~900 kWh short.
PUBLISHED = {
    "2010-2011": {"cons_mean": 6980, "cons_median": 6362, "gen_mean": 2119, "gen_median": 1764},
    "2011-2012": {"cons_mean": 6596, "cons_median": 6017, "gen_mean": 2083, "gen_median": 1708},
    "2012-2013": {"cons_mean": 6387, "cons_median": 5862, "gen_mean": 2181, "gen_median": 1814},
}

# Per-customer quality thresholds. These flag; they do not delete. Downstream
# milestones decide which flags exclude a household.
NIGHT_ELEVATION_DEG = -3.0     # sun below this for the whole period counts as night
NIGHT_GEN_SHARE_MAX = 0.01     # >1% of annual generation at night is a meter or clock fault
OVER_CAPACITY_RATIO_MAX = 1.2  # 30-min mean output above 1.2x nameplate is implausible
YIELD_RANGE = (600, 1800)      # kWh/kWp/yr; Sydney rooftop PV typically ~1,200-1,400
CENTROID_OFFSET_MAX_MIN = 60   # generation centred >1 h from solar noon: clock fault or extreme azimuth
ZERO_GEN_DAY_SHARE_MAX = 0.05  # >5% of days with no generation at all: inverter outage


class DataCheckFailed(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise DataCheckFailed(message)


# --- Reading ---------------------------------------------------------------

def read_year(fy: str) -> pd.DataFrame:
    path = config.AUSGRID_DIR / f"Solar home {fy}.csv"
    df = pd.read_csv(path, skiprows=1, dtype={"Row Quality": str})
    check(list(df.columns[5:53]) == INTERVAL_LABELS, f"{fy}: unexpected interval columns")
    df = df.rename(columns={
        "Customer": "customer",
        "Generator Capacity": "capacity_kwp",
        "Postcode": "postcode",
        "Consumption Category": "channel",
    })
    df["date"] = pd.to_datetime(df["date"], format=DATE_FORMATS[fy])
    first, last = pd.Timestamp(f"{fy[:4]}-07-01"), pd.Timestamp(f"{fy[5:]}-06-30")
    check(df["date"].min() == first and df["date"].max() == last,
          f"{fy}: dates span {df['date'].min()}..{df['date'].max()}, expected {first.date()}..{last.date()}")
    check(set(df["channel"]) <= set(CHANNELS), f"{fy}: unknown channels {set(df['channel']) - set(CHANNELS)}")
    df["fy"] = fy
    return df


def read_all() -> pd.DataFrame:
    raw = pd.concat([read_year(fy) for fy in DATE_FORMATS], ignore_index=True)
    check(set(raw["customer"]) == set(range(1, N_CUSTOMERS + 1)), "customer ids are not exactly 1..300")
    check(not raw.duplicated(["customer", "channel", "date"]).any(), "duplicate customer/channel/date rows")
    check(not raw[INTERVAL_LABELS].isna().any().any(), "blank interval cells")
    check((raw[INTERVAL_LABELS] >= 0).all().all(), "negative interval values")
    return raw


# --- Clock time -> UTC grid -------------------------------------------------

def clock_to_grid(dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Map each (local date, column k) to positions on the UTC half-hour grid.

    Returns two int arrays of shape (len(dates), 48):
      first[d, k]   grid position of that period, or -1 if the clock time never happened
      second[d, k]  grid position of the repeat, if the clock time happened twice, else -1
    """
    offsets = np.arange(48) * np.timedelta64(30, "m")
    naive = pd.DatetimeIndex((dates.values[:, None] + offsets[None, :]).ravel())
    as_dst = naive.tz_localize(RAW_TZ, ambiguous=np.ones(len(naive), bool), nonexistent="NaT")
    as_std = naive.tz_localize(RAW_TZ, ambiguous=np.zeros(len(naive), bool), nonexistent="NaT")

    def grid_pos(ix: pd.DatetimeIndex) -> np.ndarray:
        pos = (ix.asi8 - GRID_START.value) // PERIOD_NS
        pos[ix.isna()] = -1
        return pos.reshape(len(dates), 48)

    first, second = grid_pos(as_dst), grid_pos(as_std)
    second[second == first] = -1
    return first, second


def build_grid(raw: pd.DataFrame, report: dict) -> dict[str, np.ndarray]:
    """Scatter raw rows onto (customer, period) arrays, one per channel."""
    dates = pd.DatetimeIndex(np.sort(raw["date"].unique()))
    first, second = clock_to_grid(dates)

    # The mapping must tile the UTC grid exactly: every period once, none twice.
    covered = np.concatenate([first[first >= 0], second[second >= 0]])
    check(len(covered) == N_PERIODS and np.array_equal(np.sort(covered), np.arange(N_PERIODS)),
          "clock->UTC mapping does not tile the grid exactly")

    spring_days = dates[(first < 0).any(axis=1)]
    fall_days = dates[(second >= 0).any(axis=1)]
    check(len(spring_days) == 3 and len(fall_days) == 3, "expected 3 spring-forward and 3 fall-back days")
    check(all(d.dayofweek == 6 and d.month == 10 for d in spring_days), f"odd spring days {spring_days}")
    check(all(d.dayofweek == 6 and d.month == 4 for d in fall_days), f"odd fall days {fall_days}")
    phantom_cols = sorted({INTERVAL_LABELS[k] for k in np.nonzero((first < 0).any(axis=0))[0]})
    doubled_cols = sorted({INTERVAL_LABELS[k] for k in np.nonzero((second >= 0).any(axis=0))[0]})

    date_pos = dates.get_indexer(raw["date"])
    values = raw[INTERVAL_LABELS].to_numpy(np.float64)
    channel = raw["channel"].to_numpy()
    cust = raw["customer"].to_numpy() - 1

    grid = {}
    raw_totals = {}
    for ch in CHANNELS:
        m = channel == ch
        A, B, V = first[date_pos[m]], second[date_pos[m]], values[m]
        C = np.broadcast_to(cust[m][:, None], A.shape)
        phantom, twice = A < 0, B >= 0
        check(np.all(V[phantom] == 0),
              f"{ch}: spring-forward phantom cells are not all zero; the DST assumption is wrong")
        V = np.where(twice, V / 2, V)
        out = np.full((N_CUSTOMERS, N_PERIODS), np.nan, np.float32)
        keep = ~phantom
        out[C[keep], A[keep]] = V[keep]
        out[C[twice], B[twice]] = V[twice]
        grid[ch] = out
        raw_totals[ch] = float(values[m].sum())
        check(np.isclose(np.nansum(out, dtype=np.float64), raw_totals[ch], rtol=1e-6),
              f"{ch}: energy not conserved through the time conversion")

    # Fall-back columns should hold two half-hours of energy each.
    gc_rows = (channel == "GC")
    doubled_k = [INTERVAL_LABELS.index(c) for c in doubled_cols]
    neighbour_k = [min(doubled_k) - 1, max(doubled_k) + 1]
    on_fall = np.isin(raw["date"].to_numpy(), fall_days.values) & gc_rows
    ratio = values[on_fall][:, doubled_k].mean() / values[on_fall][:, neighbour_k].mean()
    check(1.6 < ratio < 2.4, f"fall-back columns are {ratio:.2f}x their neighbours, expected ~2x")

    imputed = np.zeros(N_PERIODS, bool)
    imputed[first[second >= 0]] = True
    imputed[second[second >= 0]] = True

    report["dst"] = {
        "raw_time_base": "Sydney clock time incl. daylight saving (per Ausgrid notes; verified below)",
        "spring_forward_days": [str(d.date()) for d in spring_days],
        "spring_forward_phantom_columns": phantom_cols,
        "fall_back_days": [str(d.date()) for d in fall_days],
        "fall_back_doubled_columns": doubled_cols,
        "fall_back_ratio_to_neighbours": round(float(ratio), 3),
        "imputed_periods": int(imputed.sum()),
    }
    report["energy_kwh_raw"] = {ch: round(v, 1) for ch, v in raw_totals.items()}
    grid["imputed"] = imputed
    return grid


# --- Checks against Ausgrid's own numbers ----------------------------------

def check_published_stats(raw: pd.DataFrame, report: dict) -> None:
    totals = raw.groupby(["fy", "customer", "channel"])[INTERVAL_LABELS].sum().sum(axis=1).unstack("channel")
    totals = totals.fillna(0.0)
    out = {}
    for fy, pub in PUBLISHED.items():
        t = totals.loc[fy]
        cons, gen = t["GC"] + t["CL"], t["GG"]
        ours = {"cons_mean": cons.mean(), "cons_median": cons.median(),
                "gen_mean": gen.mean(), "gen_median": gen.median()}
        for k, v in ours.items():
            check(abs(v - pub[k]) <= 1.0, f"{fy} {k}: ours {v:.1f} vs Ausgrid {pub[k]}")
        out[fy] = {k: {"ours": round(v, 1), "ausgrid": pub[k]} for k, v in ours.items()}
    report["published_stats"] = out


# --- Per-customer metadata and quality -------------------------------------

def customer_table(raw: pd.DataFrame, report: dict) -> pd.DataFrame:
    meta = raw.groupby("customer").agg(
        capacity_kwp=("capacity_kwp", "first"),
        capacity_nunique=("capacity_kwp", "nunique"),
        postcode=("postcode", "first"),
        postcode_nunique=("postcode", "nunique"),
        has_cl=("channel", lambda s: (s == "CL").any()),
    )
    check((meta["capacity_nunique"] == 1).all(), "a customer's capacity changes between years")
    check((meta["postcode_nunique"] == 1).all(), "a customer's postcode changes between years")
    meta = meta.drop(columns=["capacity_nunique", "postcode_nunique"])

    pc = pd.read_csv(config.POSTCODES_CSV, comment="#").set_index("postcode")
    missing = set(meta["postcode"]) - set(pc.index)
    check(not missing, f"postcodes without coordinates: {sorted(missing)}")
    meta["lat"] = meta["postcode"].map(pc["lat"])
    meta["lon"] = meta["postcode"].map(pc["lng"])
    meta["postcode_area_km2"] = meta["postcode"].map(pc["area_km2"])
    report["postcodes"] = {
        "n_unique": int(meta["postcode"].nunique()),
        "median_area_km2": round(float(meta["postcode_area_km2"].median()), 1),
        "max_area_km2": round(float(meta["postcode_area_km2"].max()), 1),
    }
    return meta


def grid_index() -> pd.DatetimeIndex:
    return pd.date_range(GRID_START, periods=N_PERIODS, freq=config.PERIOD)


def quality_metrics(meta: pd.DataFrame, gen: np.ndarray, report: dict) -> pd.DataFrame:
    ts = grid_index()
    ts_local = ts.tz_convert(config.LOCAL_TZ)
    minute_local = (ts_local.hour * 60 + ts_local.minute).to_numpy() + 15  # period midpoint
    day = ts_local.normalize().tz_localize(None)
    day_codes, days = pd.factorize(day)
    fy_of_period = np.where(ts_local.month >= 7, ts_local.year, ts_local.year - 1)

    rows = []
    night_kwh = total_kwh = 0.0
    for (lat, lon), group in meta.groupby(["lat", "lon"]):
        # Night means the sun stays below the threshold for the whole period.
        el_max = np.maximum.reduce([
            solar.elevation_deg(ts + f * config.PERIOD, lat, lon) for f in (0, 0.5, 1)
        ])
        night = el_max < NIGHT_ELEVATION_DEG
        noon_local = solar.solar_noon_utc_minutes(days, lon) + 600  # AEST minutes
        noon_per_period = noon_local[day_codes]
        for cid in group.index:
            g = gen[cid - 1]
            ok = ~np.isnan(g)
            total = g[ok].sum()
            night_kwh += g[ok & night].sum()
            total_kwh += total
            daily = np.bincount(day_codes[ok], weights=g[ok], minlength=len(days))
            observed_days = np.bincount(day_codes[ok], minlength=len(days)) > 0
            yields = {
                fy: g[ok & (fy_of_period == fy)].sum() / meta.at[cid, "capacity_kwp"]
                for fy in (2010, 2011, 2012)
            }
            rows.append({
                "customer": cid,
                "missing_periods": int((~ok).sum()),
                "night_gen_share": float(g[ok & night].sum() / total) if total > 0 else np.nan,
                "max_gen_ratio": float(np.nanmax(g) / (meta.at[cid, "capacity_kwp"] * 0.5)),
                "yield_min": float(min(yields.values())),
                "yield_max": float(max(yields.values())),
                "centroid_offset_min": float(
                    np.sum(g[ok] * (minute_local[ok] - noon_per_period[ok])) / total
                ) if total > 0 else np.nan,
                "zero_gen_day_share": float(((daily == 0) & observed_days).sum() / observed_days.sum()),
            })
    q = pd.DataFrame(rows).set_index("customer").sort_index()
    q["flag_night_gen"] = q["night_gen_share"] > NIGHT_GEN_SHARE_MAX
    q["flag_over_capacity"] = q["max_gen_ratio"] > OVER_CAPACITY_RATIO_MAX
    q["flag_yield"] = (q["yield_min"] < YIELD_RANGE[0]) | (q["yield_max"] > YIELD_RANGE[1])
    q["flag_clock"] = q["centroid_offset_min"].abs() > CENTROID_OFFSET_MAX_MIN
    q["flag_outage"] = q["zero_gen_day_share"] > ZERO_GEN_DAY_SHARE_MAX
    flags = [c for c in q.columns if c.startswith("flag_")]
    q["clean"] = ~q[flags].any(axis=1)
    report["quality"] = {
        "thresholds": {
            "night_elevation_deg": NIGHT_ELEVATION_DEG,
            "night_gen_share_max": NIGHT_GEN_SHARE_MAX,
            "over_capacity_ratio_max": OVER_CAPACITY_RATIO_MAX,
            "yield_range_kwh_per_kwp": YIELD_RANGE,
            "centroid_offset_max_min": CENTROID_OFFSET_MAX_MIN,
            "zero_gen_day_share_max": ZERO_GEN_DAY_SHARE_MAX,
        },
        "flag_counts": {c: int(q[c].sum()) for c in flags},
        "clean_customers": int(q["clean"].sum()),
        "missing_customer_periods": int(q["missing_periods"].sum()),
        "population_night_gen_share": round(float(night_kwh / total_kwh), 6),
    }
    return meta.join(q)


def check_time_base(meta: pd.DataFrame, gen: np.ndarray, report: dict) -> pd.DataFrame:
    """Population generation centroid per month vs solar noon, before and after the DST fix.

    If the panel were still in clock time, summer months would sit ~60 min after
    solar noon. After conversion every month must sit within 15 min of it.
    """
    ts = grid_index()
    ts_local = ts.tz_convert(config.LOCAL_TZ)
    ts_clock = ts.tz_convert(RAW_TZ)
    mean_gen = np.nanmean(gen, axis=0)
    lon = float(meta["lon"].mean())
    month = ts_local.tz_localize(None).to_period("M")
    noon = solar.solar_noon_utc_minutes(ts_local.normalize().tz_localize(None), lon) + 600
    df = pd.DataFrame({
        "month": month,
        "w": mean_gen,
        "aest_min": (ts_local.hour * 60 + ts_local.minute).to_numpy() + 15,
        "clock_min": (ts_clock.hour * 60 + ts_clock.minute).to_numpy() + 15,
        "noon_min": noon,
    })
    for col in ("aest_min", "clock_min", "noon_min"):
        df[col] = df[col] * df["w"]
    monthly = df.groupby("month")[["w", "aest_min", "clock_min", "noon_min"]].sum()
    out = pd.DataFrame({
        "solar_noon_aest": monthly["noon_min"] / monthly["w"],
        "centroid_aest": monthly["aest_min"] / monthly["w"],
        "centroid_clock": monthly["clock_min"] / monthly["w"],
    })
    out["residual_aest_min"] = out["centroid_aest"] - out["solar_noon_aest"]
    out["residual_clock_min"] = out["centroid_clock"] - out["solar_noon_aest"]
    worst = out["residual_aest_min"].abs().max()
    check(worst < 15, f"generation centroid is {worst:.1f} min from solar noon in some month; time base is wrong")
    report["time_base"] = {
        "max_abs_residual_after_fix_min": round(float(worst), 1),
        "summer_residual_in_clock_time_min": round(float(
            out.loc[out.index.month.isin([12, 1, 2]), "residual_clock_min"].mean()), 1),
        "winter_residual_in_clock_time_min": round(float(
            out.loc[out.index.month.isin([6, 7, 8]), "residual_clock_min"].mean()), 1),
    }
    return out


# --- Assemble ---------------------------------------------------------------

def to_panel(grid: dict[str, np.ndarray]) -> pd.DataFrame:
    gc, cl, gg = grid["GC"], grid["CL"].copy(), grid["GG"]
    # A day with a GC row but no CL row means no controlled-load consumption
    # was registered. This is the convention under which Ausgrid's published
    # consumption figures reproduce.
    cl[np.isnan(cl) & ~np.isnan(gc)] = 0.0
    ts = grid_index()
    slot = ((ts.tz_convert(config.LOCAL_TZ).hour * 60 + ts.tz_convert(config.LOCAL_TZ).minute) // 30 + 1).to_numpy()
    n = N_PERIODS
    return pd.DataFrame({
        "customer": np.repeat(np.arange(1, N_CUSTOMERS + 1, dtype=np.int16), n),
        "ts_utc": np.tile(ts.values, N_CUSTOMERS),
        "slot": np.tile(slot.astype(np.int8), N_CUSTOMERS),
        "load_kwh": (gc + cl).ravel(),
        "gen_kwh": gg.ravel(),
        "gc_kwh": gc.ravel(),
        "cl_kwh": cl.ravel(),
        "imputed": np.tile(grid["imputed"], N_CUSTOMERS),
    }).assign(ts_utc=lambda d: pd.DatetimeIndex(d["ts_utc"]).tz_localize("UTC"))


def main() -> None:
    report: dict = {"source": config.AUSGRID_URL, "sha256": config.AUSGRID_SHA256}
    raw = read_all()
    print(f"read     {len(raw):,} rows")
    check_published_stats(raw, report)
    print("check    annual totals reproduce Ausgrid's published means and medians")
    meta = customer_table(raw, report)
    grid = build_grid(raw, report)
    print(f"check    DST: dropped phantom columns {report['dst']['spring_forward_phantom_columns']} on "
          f"{report['dst']['spring_forward_days']}; split doubled columns on {report['dst']['fall_back_days']}")
    del raw

    timebase = check_time_base(meta, grid["GG"], report)
    print(f"check    time base: max |centroid - solar noon| = {report['time_base']['max_abs_residual_after_fix_min']} min "
          f"(clock time would give {report['time_base']['summer_residual_in_clock_time_min']} min in summer)")
    customers = quality_metrics(meta, grid["GG"], report)
    print(f"quality  {report['quality']['flag_counts']}  clean={report['quality']['clean_customers']}")

    panel = to_panel(grid)
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(config.PANEL_PARQUET, index=False)
    customers.reset_index().to_parquet(config.CUSTOMERS_PARQUET, index=False)
    timebase.assign(month=timebase.index.astype(str)).to_parquet(
        config.DATA_PROCESSED / "timebase_check.parquet", index=False)
    report["panel"] = {"rows": len(panel), "customers": N_CUSTOMERS, "periods": N_PERIODS,
                       "start_utc": str(GRID_START), "end_utc_exclusive": str(GRID_END)}
    config.QUALITY_JSON.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote    {config.PANEL_PARQUET.relative_to(config.ROOT)}  {len(panel):,} rows")


if __name__ == "__main__":
    main()
