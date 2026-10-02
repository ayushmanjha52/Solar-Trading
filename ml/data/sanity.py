"""Milestone 1 sanity figure: is the panel physically plausible, and is its clock right?

    python -m ml.data.sanity        (after preprocess and weather)

A bell curve of generation peaking "around midday" would survive a one-hour
clock error, a half-hour labelling error, or misaligned weather. So the figure
shows the evidence that rules those out, not just the bell curve:
  A  three years of generation by settlement slot, with the computed horizon
  B  mean generation and consumption by slot
  C  generation centroid minus solar noon, before and after the DST conversion
  D  correlation of generation with ERA5 irradiance at each time lag
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

from ml import config
from ml.data import preprocess, solar

# Substation mimic palette. One meaning per colour; alarm and armed are reserved.
PANEL_BASE = "#12161B"
PANEL_RAISED = "#1C232B"
ETCH = "#2A3440"
LABEL = "#E8EDF2"
MUTED = "#6E7A87"
EXPORT = "#F2A93B"  # generation
IMPORT = "#3FB8AF"  # consumption

FONTS_COMMIT = "9710da1eacb3be272583c3224dcb70f9da6eadbb"
FONT_URLS = {
    "IBMPlexMono-Regular.ttf": f"ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Medium.ttf": f"ofl/ibmplexmono/IBMPlexMono-Medium.ttf",
    "IBMPlexSans.ttf": "ofl/ibmplexsans/IBMPlexSans%5Bwdth,wght%5D.ttf",
}
OUT = config.FIGURES / "sanity_milestone1.png"


def load_fonts() -> tuple[str, str]:
    """IBM Plex if obtainable, else DejaVu. Returns (sans, mono) family names."""
    font_dir = config.DATA_RAW / "fonts"
    try:
        for name, path in FONT_URLS.items():
            dest = font_dir / name
            if not dest.exists():
                url = f"https://raw.githubusercontent.com/google/fonts/{FONTS_COMMIT}/{path}"
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                font_dir.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
            font_manager.fontManager.addfont(str(dest))
        return "IBM Plex Sans", "IBM Plex Mono"
    except (requests.RequestException, OSError, RuntimeError):
        return "DejaVu Sans", "DejaVu Sans Mono"


def per_customer_arrays(customers: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    panel = pd.read_parquet(config.PANEL_PARQUET, columns=["customer", "gen_kwh", "load_kwh"])
    n = preprocess.N_PERIODS
    cust = panel["customer"].to_numpy().reshape(preprocess.N_CUSTOMERS, n)
    assert (cust == np.arange(1, preprocess.N_CUSTOMERS + 1)[:, None]).all(), "panel is not customer-major"
    gen = panel["gen_kwh"].to_numpy().reshape(preprocess.N_CUSTOMERS, n)
    load = panel["load_kwh"].to_numpy().reshape(preprocess.N_CUSTOMERS, n)
    keep = customers.set_index("customer").loc[np.arange(1, preprocess.N_CUSTOMERS + 1), "clean"].to_numpy()
    return gen[keep], load[keep]


def style_axes(ax, mono: str) -> None:
    ax.set_facecolor(PANEL_RAISED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(ETCH)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=3, width=0.8)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(mono)
    ax.grid(color=ETCH, linewidth=0.6)
    ax.set_axisbelow(True)


def panel_title(ax, letter: str, title: str, subtitle: str, sans: str, mono: str) -> None:
    """Title above a subtitle, both anchored to the axes' top-left corner in points."""
    sub_lines = subtitle.count("\n") + 1
    title_y = 8 + 12 * sub_lines + 4
    common = {"xycoords": "axes fraction", "textcoords": "offset points", "va": "bottom"}
    ax.annotate(letter, (0, 1), xytext=(0, title_y), color=MUTED, fontsize=9, fontfamily=mono, **common)
    ax.annotate(title, (0, 1), xytext=(14, title_y), color=LABEL, fontsize=11, fontfamily=sans, **common)
    ax.annotate(subtitle, (0, 1), xytext=(0, 8), color=MUTED, fontsize=8.5, fontfamily=sans,
                linespacing=1.4, **common)


def main() -> None:
    sans, mono = load_fonts()
    customers = pd.read_parquet(config.CUSTOMERS_PARQUET)
    clean = customers[customers["clean"]]
    report = json.loads(config.QUALITY_JSON.read_text(encoding="utf-8"))
    timebase = pd.read_parquet(config.DATA_PROCESSED / "timebase_check.parquet")
    lags = pd.read_parquet(config.DATA_PROCESSED / "weather_lag_check.parquet")

    gen, load = per_customer_arrays(customers)
    kwp = clean.sort_values("customer")["capacity_kwp"].to_numpy()[:, None]
    n_days = preprocess.N_PERIODS // 48
    gen_per_kwp = np.nanmean(gen / kwp, axis=0).reshape(n_days, 48)  # AEST day x slot
    gen_profile = np.nanmean(gen.reshape(len(gen), n_days, 48), axis=(0, 1))
    load_profile = np.nanmean(load.reshape(len(load), n_days, 48), axis=(0, 1))

    # The claims the figure makes, checked rather than eyeballed.
    peak_slot = int(np.argmax(gen_profile)) + 1
    assert peak_slot in (24, 25), f"mean generation peaks in slot {peak_slot}, not at solar noon"
    night_share = report["quality"]["population_night_gen_share"]
    assert night_share < 0.001, f"{night_share:.4%} of generation falls at night"

    days = pd.date_range("2010-07-01", periods=n_days, freq="D")
    lat, lon = clean["lat"].mean(), clean["lon"].mean()
    fine_minutes = np.arange(0, 24 * 60, 5)
    fine_ts = (days.tz_localize(config.LOCAL_TZ).values[:, None]
               + (fine_minutes * np.timedelta64(1, "m"))[None, :]).ravel()
    elev = solar.elevation_deg(pd.DatetimeIndex(fine_ts).tz_localize("UTC"), lat, lon).reshape(n_days, -1)

    plt.rcParams.update({"font.family": sans, "text.color": LABEL})
    fig = plt.figure(figsize=(14, 9.6), facecolor=PANEL_BASE)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.55, wspace=0.26,
                          left=0.055, right=0.975, top=0.86, bottom=0.10)
    fig.text(0.055, 0.955, "Milestone 1: is the panel plausible, and is its clock right?",
             fontsize=15, color=LABEL, fontfamily=sans)
    fig.text(0.055, 0.925,
             f"{len(clean)} of 300 Ausgrid households that pass every quality check, 1 Jul 2010 to 30 Jun 2013, "
             "half-hourly. Slots 01-48 are settlement periods in AEST (UTC+10, no daylight saving).",
             fontsize=9.5, color=MUTED, fontfamily=sans)

    # A: heatmap of generation by day and slot, with the horizon overlaid.
    ax = fig.add_subplot(gs[0, :])
    cmap = LinearSegmentedColormap.from_list("export", [PANEL_RAISED, EXPORT])
    im = ax.imshow(gen_per_kwp.T, aspect="auto", origin="lower", cmap=cmap, interpolation="nearest",
                   extent=[0, n_days, 0.5, 48.5], vmin=0)
    ax.contour(np.arange(n_days) + 0.5, fine_minutes / 30 + 0.5, elev.T, levels=[0], colors=[LABEL],
               linewidths=0.8, alpha=0.75)
    style_axes(ax, mono)
    ax.grid(False)
    month_starts = [i for i, d in enumerate(days) if d.day == 1 and d.month in (1, 4, 7, 10)]
    ax.set_xticks(month_starts, [days[i].strftime("%b %Y") for i in month_starts])
    ax.set_yticks([1, 13, 25, 37, 48], ["01  00:00", "13  06:00", "25  12:00", "37  18:00", "48  23:30"])
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_fontfamily(mono)
    ax.set_xlim(0, n_days)
    panel_title(ax, "A", "Generation by day and settlement slot",
                "Mean kWh per kWp per half hour. White line: sun on the horizon, computed from solar geometry "
                "at the households' mean location. No step at the daylight-saving changes in Oct and Apr.",
                sans, mono)
    cb = fig.colorbar(im, ax=ax, pad=0.008, fraction=0.025)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUTED, labelsize=8, length=2)
    for t in cb.ax.get_yticklabels():
        t.set_fontfamily(mono)
    cb.set_label("kWh/kWp", color=MUTED, fontsize=8.5, fontfamily=mono)

    # B: mean diurnal profiles.
    ax = fig.add_subplot(gs[1, 0])
    slots = np.arange(1, 49)
    ax.plot(slots, gen_profile, color=EXPORT, linewidth=2)
    ax.plot(slots, load_profile, color=IMPORT, linewidth=2)
    style_axes(ax, mono)
    ax.set_xticks([1, 13, 25, 37, 48], ["01", "13", "25", "37", "48"])
    ax.set_xlim(1, 48)
    ax.set_ylim(0, max(gen_profile.max(), load_profile.max()) * 1.3)
    ax.set_xlabel("slot", color=MUTED, fontsize=8.5, fontfamily=mono)
    ax.set_ylabel("kWh per household", color=MUTED, fontsize=8.5, fontfamily=mono)
    ax.annotate("Generation", (peak_slot, gen_profile[peak_slot - 1]), xytext=(0, 6),
                textcoords="offset points", ha="center", color=LABEL, fontsize=9)
    evening = int(np.argmax(load_profile[30:])) + 31
    ax.annotate("Consumption", (evening, load_profile[evening - 1]), xytext=(0, 6),
                textcoords="offset points", ha="center", color=LABEL, fontsize=9)
    panel_title(ax, "B", "Mean profile by slot",
                f"Generation peaks in slot {peak_slot}. Night (sun below -3°)\ncarries "
                f"{night_share:.3%} of all generation.", sans, mono)
    ax.legend(handles=[plt.Line2D([], [], color=EXPORT, lw=2, label="generation"),
                       plt.Line2D([], [], color=IMPORT, lw=2, label="consumption")],
              loc="upper left", frameon=False, labelcolor=MUTED, prop={"family": mono, "size": 8})

    # C: time-base check.
    ax = fig.add_subplot(gs[1, 1])
    x = np.arange(len(timebase))
    ax.axhspan(-15, 15, color=ETCH, alpha=0.6, linewidth=0)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.plot(x, timebase["residual_clock_min"], color=MUTED, linewidth=2, marker="o", markersize=3.5)
    ax.plot(x, timebase["residual_aest_min"], color=LABEL, linewidth=2, marker="o", markersize=3.5)
    style_axes(ax, mono)
    jan = [i for i, m in enumerate(timebase["month"]) if m.endswith("-01") or m.endswith("-07")]
    ax.set_xticks(jan, [pd.Period(timebase["month"][i]).strftime("%b %y") for i in jan])
    ax.set_ylim(-30, 90)
    ax.set_ylabel("minutes from solar noon", color=MUTED, fontsize=8.5, fontfamily=mono)
    ax.text(x[len(x) // 2], 74, "as published (AEST/AEDT clock)", color=MUTED, fontsize=8.5, ha="center")
    ax.text(x[18], -25, "after conversion (AEST)", color=LABEL, fontsize=8.5, ha="center")
    tb = report["time_base"]
    panel_title(ax, "C", "Clock check",
                f"Generation centroid minus solar noon, by month. Clock time\nruns {tb['summer_residual_in_clock_time_min']:.0f} min late in "
                f"summer; converted, worst month is {tb['max_abs_residual_after_fix_min']} min (band ±15).",
                sans, mono)

    # D: weather alignment.
    ax = fig.add_subplot(gs[1, 2])
    ax.plot(lags["lag_half_hours"], lags["corr"], color=LABEL, linewidth=2, marker="o", markersize=5)
    style_axes(ax, mono)
    ax.set_xticks(lags["lag_half_hours"])
    ax.set_xlabel("irradiance shifted by (half hours)", color=MUTED, fontsize=8.5, fontfamily=mono)
    ax.set_ylabel("correlation with generation", color=MUTED, fontsize=8.5, fontfamily=mono)
    r0 = float(lags.loc[lags["lag_half_hours"] == 0, "corr"].iloc[0])
    ax.set_ylim(None, r0 + 0.25 * (r0 - lags["corr"].min()))
    ax.annotate(f"r = {r0:.3f} at lag 0", (0, r0), xytext=(0, 9), textcoords="offset points",
                ha="center", color=LABEL, fontsize=9, fontfamily=mono)
    wa = report["weather_alignment"]
    panel_title(ax, "D", "Weather alignment",
                f"Generation vs ERA5 irradiance of the household's cell.\nPeaks at lag 0. Daily totals: "
                f"r = {wa['daily_gen_vs_ghi_corr']:.2f}.", sans, mono)

    fig.text(0.055, 0.025,
             "Simulation-backed project. Data: Ausgrid Solar Home Electricity Data (archive copy, sha256 "
             f"{config.AUSGRID_SHA256[:12]}…); ERA5 reanalysis via Open-Meteo. Meters in the app are simulated; "
             "these readings are real.",
             fontsize=8, color=MUTED, fontfamily=sans)

    config.FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, facecolor=PANEL_BASE)
    print(f"check    mean generation peaks in slot {peak_slot}; night share {night_share:.4%}")
    print(f"wrote    {OUT.relative_to(config.ROOT)}  (fonts: {sans}, {mono})")


if __name__ == "__main__":
    main()
